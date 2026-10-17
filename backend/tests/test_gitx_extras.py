"""Stash, tags, remotes, submodules, LFS, worktrees, upkeep, settings and cloning, on real
repositories (phase 12, bloque 4)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from gitrepos import commit_file, make_bare, make_repo, sh, write
from test_gitx_jobs import wait

from agentic_os.services.gitx import (
    clone,
    lfs,
    read,
    remote,
    remotes,
    settings,
    stash,
    submodules,
    tags,
    trees,
    upkeep,
)
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.jobs import JobManager
from agentic_os.services.gitx.runner import Repo


def repo_of(path: Path) -> Repo:
    return Repo(str(path))


@pytest.fixture
def web(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "web", files={"a.txt": "base\n"})


# ------------------------------------------------------------------------------- stash
def test_stash_sets_changes_aside_and_brings_them_back(web: Path):
    repo = repo_of(web)
    write(web, "a.txt", "changed\n")
    write(web, "nuevo.txt", "new\n")

    assert stash.push(repo, "mi trabajo")
    assert read.status(repo).clean and (web / "a.txt").read_text("utf-8") == "base\n"
    (entry,) = stash.entries(repo)
    assert entry.ref == "stash@{0}" and "mi trabajo" in entry.message

    assert stash.apply(repo, "stash@{0}").status == "done"
    assert (web / "a.txt").read_text("utf-8") == "changed\n" and (web / "nuevo.txt").exists()
    assert len(stash.entries(repo)) == 1  # apply keeps it

    sh(web, "checkout", "--", "a.txt")
    (web / "nuevo.txt").unlink()
    assert stash.apply(repo, "0", drop=True).status == "done"
    assert stash.entries(repo) == []


def test_nothing_to_stash_and_unknown_stashes(web: Path):
    repo = repo_of(web)
    assert stash.push(repo) is False
    with pytest.raises(GitxError) as unknown:
        stash.apply(repo, "stash@{3}")
    assert unknown.value.code == "unknown_ref"


def test_a_stash_that_does_not_fit_reports_conflicts_and_is_kept(web: Path):
    repo = repo_of(web)
    write(web, "a.txt", "mine\n")
    stash.push(repo)
    commit_file(web, "a.txt", "theirs\n", message="someone else changed it")

    result = stash.apply(repo, "stash@{0}")

    assert result.status == "conflicts" and result.conflicts == ["a.txt"]
    assert len(stash.entries(repo)) == 1  # not dropped


def test_stash_diff_drop_and_branch(web: Path):
    repo = repo_of(web)
    write(web, "a.txt", "changed\n")
    stash.push(repo, "uno")
    write(web, "a.txt", "otra\n")
    stash.push(repo, "dos")
    first, second = stash.entries(repo)
    assert "dos" in first.message and "uno" in second.message
    assert stash.parent_of(repo, first) == sh(web, "rev-parse", "HEAD")

    stash.drop(repo, first.ref)
    assert len(stash.entries(repo)) == 1
    stash.to_branch(repo, "stash@{0}", "desde-stash")
    assert read.status(repo).branch == "desde-stash"
    assert (web / "a.txt").read_text("utf-8") == "changed\n" and stash.entries(repo) == []


# ------------------------------------------------------------------------------- tags
def test_tags_lightweight_and_annotated(web: Path):
    repo = repo_of(web)
    tags.create(repo, "v0.1")
    commit_file(web, "b.txt", "b\n", message="second")
    tags.create(repo, "v1.0", message="primera versión")
    tags.create(repo, "viejo", ref="HEAD~1")

    listed = {t.name: t for t in tags.tags(repo)}

    assert set(listed) == {"v0.1", "v1.0", "viejo"}
    assert listed["v1.0"].annotated and listed["v1.0"].message == "primera versión"
    assert not listed["v0.1"].annotated and listed["v0.1"].sha == listed["viejo"].sha
    assert listed["v1.0"].sha == sh(web, "rev-parse", "HEAD")  # the commit, not the tag object

    with pytest.raises(GitxError) as dup:
        tags.create(repo, "v0.1")
    assert dup.value.code == "tag_exists"
    with pytest.raises(GitxError) as bad:
        tags.create(repo, "con espacio")
    assert bad.value.code == "invalid_ref"
    tags.delete(repo, "viejo")
    assert "viejo" not in {t.name for t in tags.tags(repo)}


def test_pushing_and_deleting_a_tag_on_the_remote(web: Path, tmp_path: Path):
    bare = make_bare(tmp_path / "remote.git")
    sh(web, "remote", "add", "origin", str(bare))
    sh(web, "push", "-q", "-u", "origin", "main")
    repo = repo_of(web)
    tags.create(repo, "v1")
    manager = JobManager()

    pushed = wait(manager, manager.start(repo, "r", "push", tags.push_args("origin", "v1")))
    assert pushed.status == "succeeded" and "v1" in sh(bare, "tag")

    deleted = wait(
        manager, manager.start(repo, "r", "push", tags.delete_remote_args("origin", "v1"))
    )
    assert deleted.status == "succeeded" and sh(bare, "tag") == ""


# ------------------------------------------------------------------------------- remotes
def test_add_rename_change_and_remove_a_remote(web: Path, tmp_path: Path):
    repo = repo_of(web)
    one = make_bare(tmp_path / "one.git")
    two = make_bare(tmp_path / "two.git")

    remotes.add(repo, "origin", str(one))
    remotes.rename(repo, "origin", "upstream")
    remotes.set_url(repo, "upstream", str(two))
    assert [(r.name, r.fetch_url.replace("\\", "/")) for r in remote.remotes(repo)] == [
        ("upstream", str(two).replace("\\", "/"))
    ]
    remotes.remove(repo, "upstream")
    assert remote.remotes(repo) == []


def test_remote_names_and_addresses_are_checked(web: Path):
    repo = repo_of(web)
    for name in ("-evil", "a b", "x;y", ""):
        with pytest.raises(GitxError) as bad:
            remotes.add(repo, name, "https://example.com/x.git")
        assert bad.value.code == "invalid_remote"
    for url in ("--upload-pack=calc", "ext::sh -c touch% pwned", "", "x\ny"):
        with pytest.raises(GitxError) as bad_url:
            remotes.add(repo, "ok", url)
        assert bad_url.value.code == "invalid_url"
    assert remote.remotes(repo) == []


def test_testing_a_connection(web: Path, tmp_path: Path):
    bare = make_bare(tmp_path / "remote.git")
    sh(web, "remote", "add", "origin", str(bare))
    sh(web, "push", "-q", "origin", "main")
    sh(web, "remote", "add", "lost", "http://127.0.0.1:9/none.git")
    repo = repo_of(web)

    good = remotes.test_connection(repo, "origin")
    bad = remotes.test_connection(repo, "lost")

    assert good.ok and good.branches == 1
    assert not bad.ok and bad.error_code == "network"


def test_a_forced_push_with_a_lease_refuses_what_someone_else_pushed(web: Path, tmp_path: Path):
    bare = make_bare(tmp_path / "remote.git")
    sh(web, "remote", "add", "origin", str(bare))
    sh(web, "push", "-q", "-u", "origin", "main")
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", str(bare), str(other))
    sh(other, "config", "user.name", "Otro")
    sh(other, "config", "user.email", "o@example.com")
    sh(other, "config", "core.autocrlf", "false")
    repo = repo_of(web)
    manager = JobManager()

    # Rewrite history locally: a plain push is refused, the forced one goes through.
    sh(web, "commit", "-q", "--amend", "-m", "rewritten")
    refused = wait(manager, manager.start(repo, "r", "push", remote.push_args(repo)))
    assert refused.status == "failed" and refused.error_code == "non_fast_forward"
    assert remotes.would_overwrite(repo, "origin", "main") == [
        f"{sh(bare, 'rev-parse', '--short', 'main')} init"
    ]
    forced = wait(manager, manager.start(repo, "r", "push", remotes.force_push_args(repo)))
    assert forced.status == "succeeded"
    assert sh(bare, "rev-parse", "main") == sh(web, "rev-parse", "main")

    # Someone pushes meanwhile: the lease pins the commit we last saw, so git refuses.
    commit_file(other, "o.txt", "o\n")
    sh(other, "pull", "-q", "--rebase")
    sh(other, "push", "-q")
    sh(web, "commit", "-q", "--amend", "-m", "rewritten again")
    stale = wait(manager, manager.start(repo, "r", "push", remotes.force_push_args(repo)))
    assert stale.status == "failed"
    assert sh(bare, "log", "-1", "--format=%s", "main") != "rewritten again"  # theirs survived


# ------------------------------------------------------------------------------- submodules
def test_submodules_list_update_and_remove(tmp_path: Path):
    library = make_repo(tmp_path / "library", files={"lib.py": "x = 1\n"})
    app = make_repo(tmp_path / "app")
    repo = repo_of(app)

    submodules.add(repo, str(library), "vendor/lib")
    sh(app, "commit", "-q", "-m", "add the library")
    (listed,) = submodules.submodules(repo)
    assert (listed.path, listed.state) == ("vendor/lib", "ok")
    assert listed.url.replace("\\", "/").endswith("library")

    # A clone of the app has the folder empty until the submodule is initialized.
    copy = tmp_path / "copy"
    sh(tmp_path, "clone", "-q", str(app), str(copy))
    assert submodules.submodules(repo_of(copy))[0].state == "not_initialized"
    manager = JobManager()
    done = wait(
        manager,
        manager.start(
            repo_of(copy),
            "r",
            "submodule",
            ["-c", "protocol.file.allow=always", *submodules.update_args()],
        ),
    )
    assert done.status == "succeeded" and (copy / "vendor" / "lib" / "lib.py").exists()
    assert submodules.submodules(repo_of(copy))[0].state == "ok"

    # (This machine's own autocrlf must not make the inner checkout look edited.)
    sh(app / "vendor" / "lib", "config", "core.autocrlf", "false")
    sh(app / "vendor" / "lib", "checkout", "-q", "--", ".")
    # The library moves on: the superproject sees it as modified until it records the new commit.
    commit_file(library, "lib.py", "x = 2\n", message="bump")
    sh(app / "vendor" / "lib", "fetch", "-q")
    sh(app / "vendor" / "lib", "checkout", "-q", "--detach", "origin/main")
    assert submodules.submodules(repo)[0].state == "modified"
    sha = sh(app / "vendor" / "lib", "rev-parse", "HEAD~1")
    submodules.use_commit(repo, "vendor/lib", sha)
    assert sh(app / "vendor" / "lib", "rev-parse", "HEAD") == sha

    submodules.remove(repo, "vendor/lib")
    assert submodules.submodules(repo) == []
    assert not (app / "vendor" / "lib").exists()


def test_submodule_paths_are_checked(web: Path):
    for path in ("", "../out", "-x"):
        with pytest.raises(GitxError) as bad:
            submodules.add(repo_of(web), "https://example.com/x.git", path)
        assert bad.value.code == "invalid_path"
    with pytest.raises(GitxError) as missing:
        submodules.use_commit(repo_of(web), "nada", "HEAD")
    assert missing.value.code == "submodule_not_initialized"


# ------------------------------------------------------------------------------- LFS
def test_lfs_state_and_patterns(web: Path):
    repo = repo_of(web)
    assert lfs.state(repo).used is False and lfs.patterns(repo) == []
    write(web, ".gitattributes", "*.psd filter=lfs diff=lfs merge=lfs -text\n*.txt text\n")

    state = lfs.state(repo)

    assert state.used and state.patterns == ["*.psd"]
    if not shutil.which("git-lfs"):
        pytest.skip("git-lfs is not installed")
    assert state.installed
    lfs.track(repo, "*.bin")
    assert lfs.patterns(repo) == ["*.psd", "*.bin"]
    lfs.untrack(repo, "*.bin")
    assert lfs.patterns(repo) == ["*.psd"]
    with pytest.raises(GitxError) as bad:
        lfs.track(repo, "--evil")
    assert bad.value.code == "invalid_pattern"


def test_lfs_commands_say_when_it_is_missing(web: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lfs, "installed", lambda _repo: False)
    with pytest.raises(GitxError) as missing:
        lfs.track(repo_of(web), "*.bin")
    assert missing.value.code == "lfs_missing"


# ------------------------------------------------------------------------------- worktrees
def test_the_worktrees_of_a_repository(web: Path, tmp_path: Path):
    repo = repo_of(web)
    other = tmp_path / "web.wt" / "T-1"
    sh(web, "worktree", "add", "-q", "-b", "agentic/T-1", str(other))

    listed = trees.worktrees(repo)

    assert [(Path(w.path).name, w.main, w.branch, w.task) for w in listed] == [
        ("web", True, "main", False),
        ("T-1", False, "agentic/T-1", True),
    ]
    with pytest.raises(GitxError) as main:
        trees.remove(repo, str(web))
    assert main.value.code == "bad_worktree"
    with pytest.raises(GitxError) as unknown:
        trees.remove(repo, str(tmp_path / "otro"))
    assert unknown.value.code == "unknown_ref"

    trees.remove(repo, str(other))
    assert len(trees.worktrees(repo)) == 1 and not other.exists()


def test_prune_forgets_a_worktree_whose_folder_is_gone(web: Path, tmp_path: Path):
    repo = repo_of(web)
    other = tmp_path / "gone"
    sh(web, "worktree", "add", "-q", "-b", "temp", str(other))
    shutil.rmtree(other)
    assert any(w.prunable for w in trees.worktrees(repo))

    trees.prune(repo)

    assert len(trees.worktrees(repo)) == 1


# ------------------------------------------------------------------------------- upkeep
def test_clean_shows_what_it_would_delete_and_then_deletes_it(web: Path):
    repo = repo_of(web)
    write(web, "scratch.txt", "x\n")
    write(web, "carpeta/dentro.txt", "y\n")
    write(web, ".gitignore", "*.log\n")
    sh(web, "add", ".gitignore")
    sh(web, "commit", "-q", "-m", "ignore")
    write(web, "debug.log", "z\n")

    plain = upkeep.clean_preview(repo)
    with_ignored = upkeep.clean_preview(repo, ignored=True)

    assert plain.files == ["scratch.txt"] and plain.folders == ["carpeta/"]
    assert "debug.log" in with_ignored.files
    assert (web / "scratch.txt").exists()  # a preview deletes nothing

    upkeep.clean(repo, ["scratch.txt", "carpeta/"])
    assert not (web / "scratch.txt").exists() and not (web / "carpeta").exists()
    assert (web / "debug.log").exists()  # ignored files stay unless asked


def test_gc_fsck_and_size(web: Path):
    repo = repo_of(web)
    manager = JobManager()

    assert wait(manager, manager.start(repo, "r", "gc", upkeep.gc_args())).status == "succeeded"
    assert upkeep.verify(repo).ok
    assert upkeep.size(repo).packed


def test_fsck_reports_a_broken_repository(web: Path):
    objects = web / ".git" / "objects"
    victim = next(p for p in objects.rglob("*") if p.is_file() and len(p.parent.name) == 2)
    victim.chmod(0o666)
    victim.write_bytes(b"garbage")

    result = upkeep.verify(repo_of(web))

    assert not result.ok and result.problems


# ------------------------------------------------------------------------------- settings
def test_settings_by_scope(web: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "gitconfig"
    home.write_text("", "utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home))
    repo = repo_of(web)

    settings.set_value(None, "global", "user.name", "Ana Global")
    settings.set_value(repo, "local", "user.name", "Ana Local")
    settings.set_value(repo, "local", "pull.rebase", "true")

    shown = settings.common(repo)
    assert shown["user.name"] == {"global": "Ana Global", "local": "Ana Local"}
    assert shown["pull.rebase"]["local"] == "true" and shown["pull.rebase"]["global"] is None
    keys = {e.key: e for e in settings.entries(repo, "local")}
    assert keys["user.name"].value == "Ana Local" and keys["user.name"].scope == "local"
    assert settings.common(None)["user.name"] == {"global": "Ana Global"}

    settings.set_value(repo, "local", "user.name", None)
    assert settings.common(repo)["user.name"]["local"] is None
    settings.set_value(repo, "local", "user.name", None)  # unsetting what is not set is fine


def test_settings_that_run_commands_are_refused(web: Path):
    repo = repo_of(web)
    for key in (
        "core.editor",
        "alias.x",
        "core.sshCommand",
        "credential.helper",
        "core.hooksPath",
        "url.https://x/.insteadOf",
        "include.path",
        "diff.external",
        "gpg.program",
    ):
        with pytest.raises(GitxError) as forbidden:
            settings.set_value(repo, "local", key, "calc")
        assert forbidden.value.code in ("forbidden_key", "invalid_key"), key
    for key in ("sin punto", "--system", "a..b"):
        with pytest.raises(GitxError) as invalid:
            settings.set_value(repo, "local", key, "x")
        assert invalid.value.code == "invalid_key"
    with pytest.raises(GitxError) as no_repo:
        settings.set_value(None, "local", "user.name", "x")
    assert no_repo.value.code == "no_repo"


# ------------------------------------------------------------------------------- clone and init
def test_clone_a_repository_with_progress(tmp_path: Path):
    source = make_repo(tmp_path / "source", files={"README.md": "hi\n"})
    parent = tmp_path / "projects"
    parent.mkdir()
    manager = JobManager()

    name = clone.folder_name(str(source))
    destination = clone.target(str(parent), name)
    done = wait(
        manager,
        manager.start(
            repo_of(parent),
            "new",
            "clone",
            clone.clone_args(str(source), destination),
            exclusive=False,
        ),
    )

    assert name == "source" and done.status == "succeeded"
    assert (destination / "README.md").exists()
    with pytest.raises(GitxError) as taken:
        clone.target(str(parent), name)
    assert taken.value.code == "folder_exists"


def test_clone_names_and_destinations_are_checked(tmp_path: Path):
    assert clone.folder_name("https://github.com/x/app.git") == "app"
    assert clone.folder_name("git@github.com:x/app.git") == "app"
    assert clone.folder_name("https://example.com/x/app/") == "app"
    for name in ("", "..", "a/b", "-x", "c:d"):
        with pytest.raises(GitxError) as bad:
            clone.target(str(tmp_path), name)
        assert bad.value.code == "invalid_path"
    with pytest.raises(GitxError) as missing:
        clone.target(str(tmp_path / "no-existe"), "x")
    assert missing.value.code == "folder_not_found"
    with pytest.raises(GitxError) as option:
        clone.clone_args("--upload-pack=calc", tmp_path / "x")
    assert option.value.code == "invalid_url"


def test_init_makes_a_folder_a_repository(tmp_path: Path):
    folder = tmp_path / "new" / "project"

    clone.init(str(folder), "develop")

    assert read.status(repo_of(folder)).branch == "develop"
    with pytest.raises(GitxError) as again:
        clone.init(str(folder))
    assert again.value.code == "repo_exists"
