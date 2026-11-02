"""Tests for scripts/check-public.py (phase 25, ADR 0031)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-public.py"
spec = importlib.util.spec_from_file_location("check_public", SCRIPT)
assert spec and spec.loader
check_public = importlib.util.module_from_spec(spec)
sys.modules["check_public"] = check_public  # dataclasses look their module up here
spec.loader.exec_module(check_public)

IDENTITY = "Pub Lic <pub@example.com>"
FAKE_TOKEN = "ghp_" + "a" * 36


def git(
    repo: Path, *args: str, name: str = "Pub Lic", email: str = "pub@example.com"
) -> None:
    env = {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(repo),
        "PATH": os.environ["PATH"],
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / ".public-check.local").write_text(
        "# comment\nSecretUser\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def commit(
    repo: Path, files: dict[str, bytes | str], message: str = "change", **ident: str
) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_bytes(content)
        git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message, **ident)


def run(repo: Path, *args: str) -> int:
    return check_public.main(["--root", str(repo), *args])


def test_clean_tree_passes(repo: Path, capsys) -> None:
    assert run(repo) == 0
    assert "0 hallazgos" in capsys.readouterr().err


def test_personal_pattern_is_a_case_insensitive_substring(repo: Path, capsys) -> None:
    commit(repo, {"notes.txt": "path C:\\Users\\xsecretuserx\\data\n"})
    assert run(repo) == 1
    assert "notes.txt: dato personal" in capsys.readouterr().out


def test_personal_pattern_is_found_in_binaries_and_file_names(
    repo: Path, capsys
) -> None:
    commit(repo, {"img.png": b"\x89PNG\0\0tEXt SECRETUSER\0", "SecretUser.txt": "x"})
    assert run(repo) == 1
    out = capsys.readouterr().out
    assert "img.png: dato personal" in out
    assert "SecretUser.txt: dato personal en el nombre del fichero" in out


def test_personal_patterns_ignore_the_allowlist(repo: Path) -> None:
    (repo / "scripts").mkdir()
    (repo / "scripts/public-allowlist.txt").write_text(
        "notes.txt\tgithub-token\tfake\n", encoding="utf-8"
    )
    commit(repo, {"notes.txt": "SecretUser"})
    assert run(repo) == 1


def test_secret_patterns_and_allowlist(repo: Path, capsys) -> None:
    commit(repo, {"a.py": f"t = '{FAKE_TOKEN}'\n", "b.py": f"\n\nt = '{FAKE_TOKEN}'\n"})
    assert run(repo) == 1
    out = capsys.readouterr().out
    assert "a.py:1: posible secreto (github-token)" in out
    assert "b.py:3: posible secreto (github-token)" in out

    commit(
        repo,
        {
            "scripts/public-allowlist.txt": "# known\na.py\tgithub-token\tfake token in a test\n"
            "b.py\tgithub-token\tsame\n"
        },
    )
    assert run(repo) == 0


def test_allowlist_needs_a_reason_and_a_known_pattern(repo: Path) -> None:
    commit(repo, {"scripts/public-allowlist.txt": "a.py\tgithub-token\t\n"})
    with pytest.raises(SystemExit):
        run(repo)
    commit(repo, {"scripts/public-allowlist.txt": "a.py\tnope\treason\n"})
    with pytest.raises(SystemExit):
        run(repo)


def test_forbidden_files(repo: Path, capsys) -> None:
    commit(repo, {".env": "A=1", "data/app.db": b"\0", "spikes/out/raw.log": "x"})
    assert run(repo) == 1
    out = capsys.readouterr().out
    for name in (".env", "data/app.db", "spikes/out/raw.log"):
        assert f"{name}: fichero que no debe publicarse" in out


def test_binaries_skip_secret_patterns(repo: Path) -> None:
    commit(repo, {"blob.bin": b"\0" + FAKE_TOKEN.encode()})
    assert run(repo) == 0


def test_missing_personal_file_warns(repo: Path, capsys) -> None:
    (repo / ".public-check.local").unlink()
    assert run(repo) == 0
    assert "falta .public-check.local" in capsys.readouterr().err


def test_history_finds_removed_content_identities_and_messages(
    repo: Path, capsys
) -> None:
    commit(repo, {"old.txt": "secretuser was here"})
    git(repo, "rm", "-q", "old.txt")
    git(repo, "commit", "-q", "-m", "remove")
    assert run(repo) == 0  # the tree is clean
    assert run(repo, "--history") == 1
    assert "old.txt (blob" in capsys.readouterr().out

    commit(repo, {"x.txt": "1"}, message="fix for SecretUser")
    git(repo, "tag", "-a", "v1", "-m", "tag by secretuser")
    commit(repo, {"y.txt": "2"}, email="SecretUser@example.com")
    run(repo, "--history")
    out = capsys.readouterr().out
    assert out.count("mensaje de") == 2
    assert "SecretUser@example.com" in out


def test_history_expected_identity(repo: Path, capsys) -> None:
    assert run(repo, "--history", "--expect-identity", IDENTITY) == 0
    commit(repo, {"z.txt": "1"}, email="you@example.com")
    assert run(repo, "--history", "--expect-identity", IDENTITY) == 1
    assert "you@example.com" in capsys.readouterr().out


def test_history_sees_every_name_of_a_reused_blob(repo: Path, capsys) -> None:
    # The same content under a second name (a rename, or two equal files) must not hide it.
    commit(repo, {"notes.txt": "same"})
    git(repo, "mv", "notes.txt", "SecretUser.txt")
    git(repo, "commit", "-q", "-m", "rename")
    commit(repo, {"empty.txt": "", ".env": ""})
    git(repo, "rm", "-q", "SecretUser.txt", ".env")
    git(repo, "commit", "-q", "-m", "clean")
    assert run(repo) == 0
    assert run(repo, "--history") == 1
    out = capsys.readouterr().out
    assert "SecretUser.txt: dato personal en el nombre del fichero" in out
    assert ".env: fichero que no debe publicarse" in out


def test_history_exception_must_cover_every_path(repo: Path) -> None:
    commit(
        repo,
        {
            "scripts/public-allowlist.txt": "a.py\tgithub-token\tfake\n",
            "a.py": FAKE_TOKEN,
        },
    )
    assert run(repo, "--history") == 0
    commit(
        repo, {"b.py": FAKE_TOKEN}
    )  # the same blob, now also under a path not allowed
    assert run(repo, "--history") == 1


def test_utf16_and_local_files(repo: Path, capsys) -> None:
    commit(repo, {"app.exe": b"MZ\0\0" + "C:\\Users\\SECRETUSER".encode("utf-16-le")})
    commit(repo, {".public-strip-blobs.local": "abc"})
    assert run(repo) == 1
    out = capsys.readouterr().out
    assert "app.exe: dato personal" in out
    assert ".public-strip-blobs.local: fichero que no debe publicarse" in out
