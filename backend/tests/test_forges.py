"""Pull requests on GitHub and GitLab, SSH keys and tokens (phase 12, block 6)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from gitrepos import commit_file, make_repo, sh
from test_git_api import make_project, repo_ids
from test_integration import make_project as make_db_project
from test_integration import work_on
from test_scheduler import db_factory  # noqa: F401 - pytest fixture

from agentic_os.models import InboxItem
from agentic_os.services import forges, integration, pulls
from agentic_os.services.forges import github, gitlab, remoteurl
from agentic_os.services.forges.base import NewPull
from agentic_os.services.gitx import credentials, ssh
from agentic_os.services.gitx.errors import GitxError


# ------------------------------------------------------------------------------ remote urls
@pytest.mark.parametrize(
    ("url", "host", "path"),
    [
        ("https://github.com/ana/shop.git", "github.com", "ana/shop"),
        ("https://user@github.com/ana/shop", "github.com", "ana/shop"),
        ("git@github.com:ana/shop.git", "github.com", "ana/shop"),
        ("ssh://git@gitlab.com:2222/team/sub/shop.git", "gitlab.com", "team/sub/shop"),
        ("https://git.empresa.es/equipo/shop.git", "git.empresa.es", "equipo/shop"),
    ],
)
def test_remote_urls_are_taken_apart(url: str, host: str, path: str):
    parsed = remoteurl.parse(url)
    assert parsed is not None and (parsed.host, parsed.path) == (host, path)


def test_the_host_decides_the_forge_unless_it_is_chosen():
    assert remoteurl.kind_of("github.com") == "github"
    assert remoteurl.kind_of("gitlab.com") == "gitlab"
    assert remoteurl.kind_of("git.empresa.es") is None
    assert remoteurl.kind_of("git.empresa.es", "gitlab") == "gitlab"
    assert remoteurl.parse("not a url") is None


# ------------------------------------------------------------------------------ github
def api_pull(number: int = 7, **extra) -> dict:
    return {
        "number": number,
        "title": "T-1: Login",
        "state": "open",
        "draft": False,
        "user": {"login": "ana"},
        "head": {"ref": "agentic/T-1", "sha": "abc"},
        "base": {"ref": "main"},
        "html_url": f"https://github.com/ana/shop/pull/{number}",
        "created_at": "2026-10-17T10:00:00Z",
        "updated_at": "2026-10-17T11:00:00Z",
        "mergeable": True,
        "body": "texto",
        **extra,
    }


def github_client(calls: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        merged = api_pull(8, merged_at="2026-10-17T12:00:00Z")
        if request.method == "GET" and path.endswith("/pulls"):
            return httpx.Response(200, json=[api_pull(), merged])
        if request.method == "GET" and path.endswith("/pulls/7"):
            return httpx.Response(200, json=api_pull())
        if path.endswith("/check-runs"):
            runs = [
                {"name": "tests", "status": "completed", "conclusion": "success"},
                {"name": "lint", "status": "in_progress", "conclusion": None},
            ]
            return httpx.Response(200, json={"check_runs": runs})
        if path.endswith("/reviews"):
            return httpx.Response(200, json=[{"user": {"login": "luis"}, "state": "APPROVED"}])
        if path.endswith("/comments"):
            comment = {"user": {"login": "luis"}, "body": "bien", "created_at": None}
            return httpx.Response(200, json=[comment])
        if request.method == "POST":
            return httpx.Response(201, json=api_pull(9))
        return httpx.Response(200, json={})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_github_lists_reads_and_acts_on_pull_requests():
    calls: list[httpx.Request] = []
    forge = github.GitHub(github_client(calls), "github.com", "ana/shop", "tok")

    listed = forge.list("all")
    assert [(p.number, p.state) for p in listed] == [(7, "open"), (8, "merged")]
    assert calls[0].headers["authorization"] == "Bearer tok"
    assert str(calls[0].url).startswith("https://api.github.com/repos/ana/shop/pulls?")

    detail = forge.get(7)
    assert detail.body == "texto" and detail.checks_state == "pending"  # one check still runs
    assert [c.state for c in detail.checks] == ["success", "pending"]
    assert detail.reviews[0].state == "approved" and detail.comments[0].body == "bien"

    new = NewPull(title="T", body="b", head="agentic/T-1", base="main", draft=True)
    assert forge.create(new).number == 9
    sent = json.loads(next(c for c in calls if c.method == "POST").content)
    assert sent == {"title": "T", "body": "b", "head": "agentic/T-1", "base": "main", "draft": True}

    forge.merge(7, "squash")
    merge = next(c for c in calls if c.url.path.endswith("/merge"))
    assert json.loads(merge.content) == {"merge_method": "squash"}
    forge.close(7)
    forge.reopen(7)
    forge.update_branch(7)
    patches = [json.loads(c.content) for c in calls if c.method == "PATCH"]
    assert patches == [{"state": "closed"}, {"state": "open"}]
    assert any(c.url.path.endswith("/update-branch") for c in calls)


def test_github_enterprise_uses_its_own_api_host():
    assert github.api_base("github.com") == "https://api.github.com"
    assert github.api_base("git.empresa.es") == "https://git.empresa.es/api/v3"


@pytest.mark.parametrize(
    ("status", "headers", "code"),
    [
        (401, {}, "auth_failed"),
        (403, {}, "auth_failed"),
        (403, {"x-ratelimit-remaining": "0"}, "rate_limited"),
        (429, {}, "rate_limited"),
        (404, {}, "not_found"),
        (422, {}, "conflict"),
        (405, {}, "conflict"),
        (500, {}, "forge_failed"),
    ],
)
def test_api_failures_become_stable_codes(status: int, headers: dict, code: str):
    transport = httpx.MockTransport(
        lambda _r: httpx.Response(status, headers=headers, json={"message": "no"})
    )
    with pytest.raises(GitxError) as error:
        github.GitHub(httpx.Client(transport=transport), "github.com", "ana/shop", "tok").get(1)
    assert error.value.code == code


def test_a_network_failure_is_reported():
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    client = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(GitxError) as error:
        github.GitHub(client, "github.com", "ana/shop", "tok").list()
    assert error.value.code == "network"


# ------------------------------------------------------------------------------ gitlab
def test_gitlab_merge_requests_are_pull_requests():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        mr = {
            "iid": 3,
            "title": "Draft: T-1: Login",
            "state": "opened",
            "draft": True,
            "author": {"username": "ana"},
            "source_branch": "agentic/T-1",
            "target_branch": "main",
            "web_url": "https://gitlab.com/team/sub/shop/-/merge_requests/3",
            "description": "texto",
            "detailed_merge_status": "can_be_merged",
            "head_pipeline": {"status": "failed", "web_url": "https://gitlab.com/p/1"},
        }
        path = request.url.path
        if path.endswith("/approvals"):
            return httpx.Response(200, json={"approved_by": [{"user": {"username": "luis"}}]})
        if path.endswith("/notes"):
            notes = [
                {"author": {"username": "luis"}, "body": "ok", "system": False},
                {"author": {"username": "bot"}, "body": "changed", "system": True},
            ]
            return httpx.Response(200, json=notes)
        if request.method == "GET" and path.endswith("/merge_requests"):
            return httpx.Response(200, json=[mr])
        return httpx.Response(200, json=mr)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    forge = gitlab.GitLab(client, "gitlab.com", "team/sub/shop", "tok")
    (item,) = forge.list("open")
    assert (item.number, item.title, item.state, item.draft) == (3, "T-1: Login", "open", True)
    assert item.mergeable is True
    assert "/projects/team%2Fsub%2Fshop/merge_requests" in str(calls[0].url)
    assert "state=opened" in str(calls[0].url)

    detail = forge.get(3)
    assert detail.checks_state == "failure" and detail.reviews[0].state == "approved"
    assert [c.body for c in detail.comments] == ["ok"]  # system notes are not comments

    forge.create(NewPull(title="T", head="a", base="main", draft=True))
    created = json.loads(next(c for c in calls if c.method == "POST").content)
    assert created["title"] == "Draft: T" and created["source_branch"] == "a"
    forge.merge(3, "rebase")  # GitLab: rebase first, then merge
    assert [c.url.path.rsplit("/", 1)[-1] for c in calls[-2:]] == ["rebase", "merge"]
    forge.close(3)
    assert json.loads(calls[-1].content) == {"state_event": "close"}


# ------------------------------------------------------------------------------ credentials
@pytest.fixture
def credential_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """git's own `store` helper on a temporary file, in place of the person's real helpers."""
    store = tmp_path / "credentials"
    empty = tmp_path / "empty-gitconfig"
    empty.write_text("", "utf-8")
    settings = {
        # Neither the system nor the user's own git configuration (Git Credential Manager…).
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": f"store --file={store.as_posix()}",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    return store


def test_a_pasted_token_goes_into_gits_store_and_comes_back(credential_store: Path):
    assert credentials.token_for("github.com") is None
    credentials.store("github.com", "ghp_secret")
    assert credentials.token_for("github.com") == "ghp_secret"
    assert credentials.token_for("gitlab.com") is None
    assert credentials.has_token("github.com")
    with pytest.raises(GitxError):
        credentials.store("github.com", "bad\ntoken")


# ------------------------------------------------------------------------------ ssh keys
def test_keys_are_listed_generated_and_never_overwritten(tmp_path: Path):
    folder = tmp_path / ".ssh"
    assert ssh.keys(folder) == []
    key = ssh.generate("id_test", "ana@example.com", folder=folder)
    assert key.type == "ssh-ed25519" and key.comment == "ana@example.com"
    assert key.fingerprint.startswith("SHA256:") and not key.orphan
    assert key.public.startswith("ssh-ed25519 ")
    assert [k.name for k in ssh.keys(folder)] == ["id_test"]

    with pytest.raises(GitxError) as taken:
        ssh.generate("id_test", "otra@example.com", folder=folder)
    assert taken.value.code == "key_exists"
    assert (folder / "id_test.pub").read_text().strip() == key.public  # untouched
    with pytest.raises(GitxError) as bad:
        ssh.generate("../escape", "a@b", folder=folder)
    assert bad.value.code == "invalid_name"

    (folder / "id_test").unlink()
    assert ssh.keys(folder)[0].orphan  # the private half is gone


def test_connection_test_refuses_a_hostile_host():
    with pytest.raises(GitxError):
        ssh.test("-oProxyCommand=calc")


# ------------------------------------------------------------------------------ the API
@pytest.fixture
def mocked(monkeypatch: pytest.MonkeyPatch, credential_store: Path):
    calls: list[httpx.Request] = []
    monkeypatch.setattr(forges, "new_client", lambda: github_client(calls))
    credentials.store("github.com", "tok")
    return calls


def with_remote(path: Path, tmp_path: Path, name: str = "remote") -> Path:
    """`origin` is a GitHub address; pushes to it really go to a local bare repository."""
    bare = tmp_path / f"{name}.git"
    sh(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    address = f"git@github.com:ana/{path.name}.git"
    sh(path, "remote", "add", "origin", address)
    sh(path, "config", f"url.{bare.as_posix()}.pushInsteadOf", address)
    sh(path, "push", "-q", "-u", "origin", "main")
    return bare


@pytest.fixture
def web(client: TestClient, tmp_path: Path) -> tuple[str, Path]:
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    with_remote(path, tmp_path)
    sh(path, "checkout", "-q", "-b", "agentic/T-1")
    commit_file(path, "login.py", "x\n", message="login")
    sh(path, "checkout", "-q", "main")
    project = make_project(client, path)
    return repo_ids(client, project)[path.name], path


def test_forge_info_says_where_the_remote_is_and_whether_there_is_a_token(
    client: TestClient, web, mocked
):
    repo, _ = web
    info = client.get(f"/api/repos/{repo}/forge").json()
    assert info == {"kind": "github", "host": "github.com", "remote": "origin", "has_token": True}


def test_pull_requests_through_the_api(client: TestClient, tmp_path: Path, web, mocked):
    repo, _path = web
    listed = client.get(f"/api/repos/{repo}/pulls?state=all")
    assert listed.status_code == 200 and [p["number"] for p in listed.json()] == [7, 8]
    assert client.get(f"/api/repos/{repo}/pulls/7").json()["checks_state"] == "pending"

    created = client.post(
        f"/api/repos/{repo}/pulls",
        json={"title": "T-1: Login", "head": "agentic/T-1", "base": "main"},
    )
    assert created.status_code == 201 and created.json()["number"] == 9
    # The branch was pushed first (to the bare repository standing in for GitHub).
    assert sh(tmp_path / "remote.git", "rev-parse", "--verify", "agentic/T-1")

    merged = client.post(f"/api/repos/{repo}/pulls/7/merge", json={"method": "squash"})
    assert merged.status_code == 204
    assert client.post(f"/api/repos/{repo}/pulls/7/close").status_code == 204
    assert client.post(f"/api/repos/{repo}/pulls/7/reopen").status_code == 204
    assert client.post(f"/api/repos/{repo}/pulls/7/update-branch").status_code == 204


def test_without_a_token_the_error_says_so(client: TestClient, web, credential_store):
    repo, _ = web
    response = client.get(f"/api/repos/{repo}/pulls")
    assert response.status_code == 401 and response.json()["detail"]["code"] == "auth_failed"


def test_a_remote_that_is_not_a_known_host_asks_to_choose_the_forge(
    client: TestClient, web, mocked
):
    repo, path = web
    sh(path, "remote", "set-url", "origin", "https://git.empresa.es/equipo/shop.git")
    response = client.get(f"/api/repos/{repo}/pulls")
    assert response.status_code == 422 and response.json()["detail"]["code"] == "forge_unknown"
    assert client.patch(f"/api/repos/{repo}", json={"forge": "github"}).status_code == 200
    assert client.get(f"/api/repos/{repo}/forge").json()["kind"] == "github"


def test_ssh_keys_and_tokens_through_the_api(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, credential_store
):
    monkeypatch.setattr(ssh, "ssh_dir", lambda: tmp_path / ".ssh")
    assert client.get("/api/git/ssh-keys").json() == []
    made = client.post("/api/git/ssh-keys", json={"name": "id_app", "email": "a@b.es"})
    assert made.status_code == 201 and made.json()["name"] == "id_app"
    assert [k["name"] for k in client.get("/api/git/ssh-keys").json()] == ["id_app"]
    again = client.post("/api/git/ssh-keys", json={"name": "id_app", "email": "a@b.es"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "key_exists"

    assert client.get("/api/git/forge-token?host=gitlab.com").json() == {"has_token": False}
    saved = client.post("/api/git/forge-token", json={"host": "gitlab.com", "token": "glpat"})
    assert saved.status_code == 204
    assert client.get("/api/git/forge-token?host=gitlab.com").json() == {"has_token": True}


# ------------------------------------------------------------------------------ from a task
def test_a_task_opens_a_pull_request_per_repository_and_links_them(
    db_factory,  # noqa: F811
    tmp_path: Path,
    monkeypatch,
    credential_store,
):
    credentials.store("github.com", "tok")
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            bodies.append(json.loads(request.content))
            n = len([b for b in bodies if "head" in b])
            return httpx.Response(201, json=api_pull(n, html_url=f"https://x/pull/{n}"))
        if request.method == "PATCH":
            bodies.append(json.loads(request.content))
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(forges, "new_client", lambda: httpx.Client(transport=transport))
    folder = tmp_path / "shop"
    for name in ("backend", "frontend"):
        with_remote(make_repo(folder / name, files={"a.txt": "base\n"}), tmp_path, name)
    with db_factory() as db:
        project = make_db_project(db, folder)
        task = work_on(db, project, {"backend/n.py": "n\n", "frontend/m.py": "m\n"})

        results = pulls.create_for_task(db, task, project, draft=True)

        assert [(r.name, r.status) for r in results] == [
            ("backend", "created"),
            ("frontend", "created"),
        ]
        creates = [b for b in bodies if "head" in b]
        assert [b["title"] for b in creates] == [f"{task.code}: Login"] * 2
        assert all(b["draft"] for b in creates)
        assert "Relacionados" in creates[1]["body"] and "https://x/pull/1" in creates[1]["body"]
        # The first one could not know the second yet: its description was completed afterwards.
        assert any("https://x/pull/2" in b.get("body", "") for b in bodies if "head" not in b)
        assert sh(tmp_path / "backend.git", "rev-parse", "--verify", task.branch or "")


def test_on_approve_pull_request_reports_what_could_not_be_opened(
    db_factory,  # noqa: F811
    tmp_path: Path,
    credential_store,
):
    web = make_repo(tmp_path / "web", files={"a.txt": "base\n"})  # no remote at all
    with db_factory() as db:
        project = make_db_project(db, web, on_approve="pull_request")
        task = work_on(db, project, {"login.py": "login\n"})
        integration.after_approval(db, task, project)
        (item,) = db.query(InboxItem).all()
        assert item.title == f"No se pudo abrir el pull request de {task.code}"
        assert "web" in item.detail
