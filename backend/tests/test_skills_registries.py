"""The registry explorer (phase 17, block 6) against fake sources (httpx.MockTransport) shaped
like the real answers of spike S3: CA16 (most used, search, the preview at a fixed revision,
installing it at a level), CA17 (updates with their diff, never applied by themselves, the
person's edits kept) and CA18 (unopened scripts, offline, a failing source)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agentic_os.services.skills.registries.service import RegistryService

MD = "---\nname: {name}\ndescription: {description}\nlicense: MIT\n---\n\n{body}\n"
RANKING = (
    "rank,skill,skill_key,platform,vendor,source_skillssh,slug_clawhub,url,repo_url,install,"
    "match,description,description_zh,installs_skillssh,downloads_clawhub,downloads_skillhub_cn,"
    "wis,popularity,momentum,buzz,maintenance,trust,coverage,anomaly,category,flags\n"
    "1,code-review,ss:mattpocock/skills/code-review,skills.sh,mattpocock,mattpocock/skills,,"
    "https://www.skills.sh/mattpocock/skills/code-review,,,,Review a branch.,,785110,,,,,,,,,,,"
    "dev,\n"
    "2,self-improving,ch:pskoett/self-improving,clawhub,pskoett,,pskoett/self-improving,"
    "https://clawhub.ai/x,,,,Learns from errors.,,,487953,,,,,,,,,,ai,\n"
)


class FakeWeb:
    """The registries as the tests want them; `down` makes a host fail, `offline` all."""

    def __init__(self) -> None:
        self.review_body = "Revisa los cambios de la rama."
        self.down: set[str] = set()
        self.offline = False
        self.calls: list[str] = []

    def skill_files(self) -> list[dict]:
        return [
            {
                "path": "SKILL.md",
                "contents": MD.format(
                    name="code-review", description="Review a branch.", body=self.review_body
                ),
            },
            {"path": "scripts/check.sh", "contents": "#!/bin/sh\necho ok\n"},
            {"path": "metadata.json", "contents": "{}"},
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(f"{url.host}{url.path}")
        if self.offline:
            raise httpx.ConnectError("no network", request=request)
        if url.host in self.down:
            return httpx.Response(500, text="boom")
        path = url.path
        if url.host == "raw.githubusercontent.com" and path.endswith("top-installs.csv"):
            return httpx.Response(200, text=RANKING)
        if url.host == "skills.sh" and path == "/api/search":
            return httpx.Response(
                200,
                json={
                    "skills": [
                        {"id": "o/r/lint", "source": "o/r", "name": "lint", "installs": 10},
                        {
                            "id": "mattpocock/skills/code-review",
                            "source": "mattpocock/skills",
                            "name": "code-review",
                            "installs": 785110,
                        },
                    ]
                },
            )
        if url.host == "skills.sh" and path == "/api/download/mattpocock/skills/code-review":
            return httpx.Response(200, json={"files": self.skill_files()})
        if url.host == "www.skills.sh" and path == "/tele/audit":
            return httpx.Response(200, json={"code-review": {"snyk": {"risk": "medium"}}})
        if url.host == "api.github.com" and path.startswith("/repos/anthropics/skills/commits/"):
            return httpx.Response(200, json={"sha": "a1b2c3d4e5"})
        if url.host == "api.github.com" and path.startswith("/repos/anthropics/skills/git/trees"):
            tree = [
                {"path": "README.md", "type": "blob", "size": 5},
                {"path": "skills/pdf/SKILL.md", "type": "blob", "size": 90},
                {"path": "skills/pdf/forms.md", "type": "blob", "size": 4},
            ]
            return httpx.Response(200, json={"tree": tree})
        if url.host == "raw.githubusercontent.com" and path.startswith("/anthropics/skills/a1b2"):
            if path.endswith("SKILL.md"):
                return httpx.Response(
                    200, text=MD.format(name="pdf", description="Work with PDF files.", body="B")
                )
            return httpx.Response(200, text="FORM")
        if url.host == "clawhub.ai" and path == "/api/v1/skills":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "ownerHandle": "pskoett",
                            "slug": "self-improving",
                            "displayName": "self-improving",
                            "summary": "Learns from errors.",
                            "stats": {"downloads": 487953, "stars": 4004},
                        }
                    ]
                },
            )
        return httpx.Response(404, text="not here")


@pytest.fixture
def web(client: TestClient) -> FakeWeb:
    fake = FakeWeb()
    app = client.app
    app.state.skill_registries = RegistryService(
        Path(app.state.settings.data_dir),
        app.state.skills,
        transport=httpx.MockTransport(fake.handler),
    )
    return fake


def test_most_used_come_from_the_ranking_and_the_listing_sources(client: TestClient, web):
    listing = client.get("/api/skills/registries/popular").json()
    names = [(c["source"], c["name"]) for c in listing["cards"]]
    assert ("skills_sh", "code-review") in names and ("anthropic", "pdf") in names
    assert not any(source == "clawhub" for source, _ in names)  # off by default
    assert "Linkly AI" in listing["attribution"]
    review = next(c for c in listing["cards"] if c["name"] == "code-review")
    assert review["installs"] == 785110 and review["ref"] == "mattpocock/skills/code-review"


def test_search_asks_every_enabled_source_and_sorts_by_use(client: TestClient, web):
    listing = client.get("/api/skills/registries/search", params={"q": "review"}).json()
    assert [c["name"] for c in listing["cards"]][:2] == ["code-review", "lint"]
    assert listing["errors"] == {}


def test_install_reviews_scripts_and_lands_at_the_chosen_level(client: TestClient, web):
    agent = client.post("/api/agents", json={"name": "Dev"}).json()["id"]
    preview = client.post(
        "/api/skills/registries/preview",
        json={"source": "skills_sh", "ref": "mattpocock/skills/code-review"},
    ).json()
    assert preview["executables"] == ["scripts/check.sh"]
    assert preview["license"] == "MIT"
    assert preview["security"] == {"skills_sh": {"snyk": {"risk": "medium"}}}
    assert {f["path"] for f in preview["files"]} == {"SKILL.md", "scripts/check.sh"}
    script = client.get(f"/api/skills/registries/previews/{preview['id']}/files/scripts/check.sh")
    assert script.text.startswith("#!/bin/sh")
    body = {"preview_id": preview["id"], "scope": "agent", "agent_id": agent}
    refused = client.post("/api/skills/registries/install", json=body)
    assert refused.status_code == 409
    assert refused.json()["detail"]["files"] == ["scripts/check.sh"]
    # the source changes meanwhile: what gets installed is what was reviewed
    web.review_body = "OTRA COSA"
    installed = client.post(
        "/api/skills/registries/install", json={**body, "opened_files": ["scripts/check.sh"]}
    )
    assert installed.status_code == 201, installed.text
    skill = installed.json()["skill"]
    assert (skill["scope"], skill["agent_id"], skill["origin"]) == ("agent", agent, "registry")
    assert "Revisa los cambios de la rama." in skill["body"]
    versions = client.get(f"/api/skills/{skill['id']}/versions").json()
    assert versions[0]["author"]["kind"] == "registry"
    assert versions[0]["author"]["label"].startswith("skills.sh · mattpocock/skills@")
    origin = client.get(f"/api/skills/{skill['id']}/origin").json()
    assert (origin["source"], origin["update_available"]) == ("skills_sh", False)
    again = client.get("/api/skills/registries/popular").json()
    marked = next(c for c in again["cards"] if c["name"] == "code-review")
    assert marked["installed_skill_id"] == skill["id"]
    # the preview was used up
    gone = client.post("/api/skills/registries/install", json={**body, "opened_files": []})
    assert gone.status_code == 410


def _install(client: TestClient) -> dict:
    preview = client.post(
        "/api/skills/registries/preview",
        json={"source": "skills_sh", "ref": "mattpocock/skills/code-review"},
    ).json()
    return client.post(
        "/api/skills/registries/install",
        json={
            "preview_id": preview["id"],
            "scope": "general",
            "opened_files": ["scripts/check.sh"],
        },
    ).json()["skill"]


def test_updates_are_offered_with_their_diff_and_keep_the_persons_edits(client: TestClient, web):
    skill = _install(client)
    sid = skill["id"]
    client.post(f"/api/skills/{sid}/versions", json={"description": "Mi descripción."})
    assert client.post("/api/skills/updates/check").json() == {}
    assert client.get(f"/api/skills/{sid}/origin").json()["update_available"] is False
    web.review_body = "Revisa también la seguridad."
    client.post("/api/skills/updates/check")
    assert client.get(f"/api/skills/{sid}/origin").json()["update_available"] is True
    assert client.get(f"/api/skills/{sid}").json()["version"] == 2  # nothing applied by itself
    offer = client.post(f"/api/skills/{sid}/update-preview").json()
    lines = [
        line["text"]
        for f in offer["files"]
        for h in f["diff"]["hunks"]
        for line in h["lines"]
        if line["kind"] == "add"
    ]
    assert "Revisa también la seguridad." in lines
    applied = client.post(
        f"/api/skills/{sid}/update",
        json={"preview_id": offer["preview"]["id"], "opened_files": ["scripts/check.sh"]},
    ).json()
    assert applied["version"] == 3 and "Revisa también la seguridad." in applied["body"]
    history = client.get(f"/api/skills/{sid}/versions").json()
    assert [v["author"]["kind"] for v in history] == ["registry", "user", "registry"]
    assert client.get(f"/api/skills/{sid}/origin").json()["update_available"] is False


def test_a_failing_source_does_not_break_the_others(client: TestClient, web):
    client.put("/api/settings/skills", json={"registries": {"clawhub": True}})
    web.down.add("clawhub.ai")
    listing = client.get("/api/skills/registries/popular").json()
    assert listing["errors"] == {"clawhub": "unavailable"}
    assert any(c["source"] == "anthropic" for c in listing["cards"])


def test_offline_the_explorer_says_so_and_the_library_still_works(client: TestClient, web):
    web.offline = True
    listing = client.get("/api/skills/registries/search", params={"q": "review"}).json()
    assert listing["cards"] == []
    assert set(listing["errors"].values()) == {"offline"}
    response = client.post(
        "/api/skills/registries/preview", json={"source": "anthropic", "ref": "skills/pdf"}
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "registry_offline"
    assert client.get("/api/skills").status_code == 200


def test_sources_can_be_switched_and_a_github_address_lists_its_skills(client: TestClient, web):
    settings = client.put(
        "/api/settings/skills", json={"registries": {"skills_sh": False}, "skillsmp_key": "k"}
    ).json()
    assert settings["registries"] == {
        "skills_sh": False,
        "anthropic": True,
        "skillsmp": False,
        "clawhub": False,
    }
    assert settings["skillsmp_key_set"] is True and "skillsmp_key" not in settings
    web.calls.clear()
    client.get("/api/skills/registries/search", params={"q": "review"})
    assert not any(c.startswith("skills.sh") for c in web.calls)
    listing = client.get(
        "/api/skills/registries/search",
        params={"q": "https://github.com/anthropics/skills/tree/main/skills"},
    ).json()
    assert [(c["source"], c["ref"], c["name"]) for c in listing["cards"]] == [
        ("github", "anthropics/skills/skills/pdf@main", "pdf")
    ]


def test_a_zip_from_clawhub_is_read_like_an_import():
    """The ClawHub source unpacks its zip with the importer's checks (zip bombs, paths)."""
    from agentic_os.services.skills.registries.base import Http
    from agentic_os.services.skills.registries.sources import ClawHubSource

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("SKILL.md", MD.format(name="self-improving", description="d", body="B"))
        z.writestr("_meta.json", "{}")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/download":
            return httpx.Response(200, content=buffer.getvalue())
        return httpx.Response(
            200,
            json={
                "skill": {"slug": "self-improving", "displayName": "x", "isSuspicious": False},
                "latestVersion": {"version": "4.0.5"},
            },
        )

    fetched = ClawHubSource(Http(httpx.MockTransport(handler))).fetch("pskoett/self-improving")
    assert set(fetched.files) == {"SKILL.md"}
    assert fetched.revision == "4.0.5"
    assert fetched.security == {"clawhub": {"suspicious": False}}
    assert json.loads(json.dumps(fetched.security))  # stored as JSON on the origin


def test_a_github_address_with_a_branch_installs_from_that_branch(client: TestClient, web):
    """Code review: the branch of the pasted address travels with the card."""
    listing = client.get(
        "/api/skills/registries/search",
        params={"q": "https://github.com/anthropics/skills/tree/dev/skills"},
    ).json()
    [card] = listing["cards"]
    assert card["ref"] == "anthropics/skills/skills/pdf@dev"
    web.calls.clear()
    preview = client.post(
        "/api/skills/registries/preview", json={"source": "github", "ref": card["ref"]}
    )
    assert preview.status_code == 200, preview.text
    assert "api.github.com/repos/anthropics/skills/commits/dev" in web.calls
