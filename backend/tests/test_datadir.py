"""The data folder (phase 08): its pointer, its size and moving it."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.config import default_data_dir, read_pointer
from agentic_os.errors import ApiError
from agentic_os.services import datadir


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("AGENTIC_OS_DATA_DIR", raising=False)
    folder = tmp_path / "appdata" / "AgenticOS"
    folder.mkdir(parents=True)
    return folder


def make_data(folder: Path) -> None:
    """A data folder like the app's: database with a run, session logs and backend logs."""
    (folder / "runs" / "r1").mkdir(parents=True)
    log = folder / "runs" / "r1.log"
    log.write_text("terminal", "utf-8")
    (folder / "logs").mkdir()
    (folder / "logs" / "backend.log").write_text("log", "utf-8")
    with sqlite3.connect(folder / "agentic-os.db") as db:
        db.execute("CREATE TABLE runs (id TEXT, log_path TEXT)")
        db.execute("INSERT INTO runs VALUES ('r1', ?), ('r2', '')", (str(log),))
    db.close()


# ---------------------------------------------------------------- pointer
def test_without_a_pointer_the_data_is_in_the_home_folder(home: Path):
    assert default_data_dir() == home
    assert read_pointer() == {}


def test_the_pointer_tells_where_the_data_is(home: Path, tmp_path: Path):
    datadir.write_pointer({"data_dir": str(tmp_path / "elsewhere")})
    assert default_data_dir() == tmp_path / "elsewhere"


def test_a_broken_pointer_is_ignored(home: Path):
    (home / "location.json").write_text("{not json", "utf-8")
    assert default_data_dir() == home


# ---------------------------------------------------------------- size
def test_disk_usage_by_kind(tmp_path: Path):
    make_data(tmp_path)
    usage = datadir.disk_usage(tmp_path)
    assert usage.sessions == len("terminal")
    assert usage.logs == len("log")
    assert usage.database > 0
    assert usage.total == usage.database + usage.sessions + usage.logs


# ---------------------------------------------------------------- request
@pytest.mark.parametrize(
    ("target", "code"),
    [
        ("relative/folder", "path_not_absolute"),
        ("{data}", "same_data_dir"),
        ("{data}/inside", "data_dir_nested"),
        ("{full}", "folder_not_empty"),
    ],
)
def test_bad_targets_are_refused(home: Path, tmp_path: Path, target: str, code: str):
    full = tmp_path / "full"
    full.mkdir()
    (full / "x.txt").write_text("x", "utf-8")
    target = target.format(data=home, full=full)
    with pytest.raises(ApiError) as error:
        datadir.request_move(home, target)
    assert error.value.code == code
    assert "pending_move" not in read_pointer()


def test_an_environment_override_cannot_be_moved(home: Path, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_OS_DATA_DIR", str(home))
    with pytest.raises(ApiError) as error:
        datadir.request_move(home, str(tmp_path / "new"))
    assert error.value.code == "data_dir_fixed"


def test_a_move_is_recorded_for_the_next_start(home: Path, tmp_path: Path):
    target = datadir.request_move(home, str(tmp_path / "new" / "AgenticOS"))
    assert target.is_dir() and not any(target.iterdir())
    assert read_pointer()["pending_move"] == {"from": str(home), "to": str(target)}


# ---------------------------------------------------------------- applying
def test_moving_out_of_the_home_folder(home: Path, tmp_path: Path):
    make_data(home)
    target = datadir.request_move(home, str(tmp_path / "D" / "AgenticOS"))

    assert datadir.apply_pending_move() is True

    assert default_data_dir() == target
    assert sorted(p.name for p in target.iterdir()) == ["agentic-os.db", "logs", "runs"]
    assert sorted(p.name for p in home.iterdir()) == ["location.json"]  # only the pointer
    with sqlite3.connect(target / "agentic-os.db") as db:
        paths = dict(db.execute("SELECT id, log_path FROM runs"))
    db.close()
    assert paths == {"r1": str(target / "runs" / "r1.log"), "r2": ""}
    assert read_pointer().get("pending_move") is None


def test_moving_back_to_the_home_folder(home: Path, tmp_path: Path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    make_data(elsewhere)
    datadir.write_pointer({"data_dir": str(elsewhere)})
    datadir.request_move(elsewhere, str(home))

    assert datadir.apply_pending_move() is True

    assert default_data_dir() == home
    assert (home / "agentic-os.db").exists() and not elsewhere.exists()


def test_a_failed_move_leaves_the_data_where_it_was(home: Path, tmp_path, monkeypatch):
    make_data(home)
    target = datadir.request_move(home, str(tmp_path / "new"))

    def broken(*args):
        raise RuntimeError("the copied database is damaged")

    monkeypatch.setattr(datadir, "_check_and_rewrite", broken)
    assert datadir.apply_pending_move() is False

    assert default_data_dir() == home
    assert (home / "agentic-os.db").exists()
    assert not any(target.iterdir())  # the partial copy is gone
    pointer = read_pointer()
    assert pointer["pending_move"] is None
    assert "damaged" in pointer["last_error"]


def test_nothing_pending_does_nothing(home: Path):
    assert datadir.apply_pending_move() is False


# ---------------------------------------------------------------- API
def test_api_shows_the_folder_and_its_size(client: TestClient, settings):
    (Path(settings.data_dir) / "runs").mkdir(exist_ok=True)
    (Path(settings.data_dir) / "runs" / "r1.log").write_text("terminal", "utf-8")
    data = client.get("/api/settings/data-dir", params={"refresh": True}).json()
    assert data["path"] == str(settings.data_dir)
    assert data["sessions_bytes"] == len("terminal")
    assert data["total_bytes"] >= data["database_bytes"] > 0


def test_api_move_restarts_the_backend(client: TestClient, home: Path, tmp_path: Path):
    restarts: list[bool] = []
    client.app.state.request_restart = lambda: restarts.append(True)
    response = client.post("/api/settings/data-dir/move", json={"to": str(tmp_path / "new")})
    assert response.status_code == 202, response.text
    assert response.json() == {"to": str(tmp_path / "new"), "restarting": True}
    assert restarts == [True]
    assert json.loads((home / "location.json").read_text("utf-8"))["pending_move"]


def test_api_move_waits_for_the_runs(client: TestClient, home: Path, tmp_path, monkeypatch):
    monkeypatch.setattr(client.app.state.run_manager, "live_ids", lambda: ["r1"])
    response = client.post("/api/settings/data-dir/move", json={"to": str(tmp_path / "new")})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "runs_active"


def test_moving_back_home_where_an_old_logs_folder_was_left(home: Path, tmp_path: Path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    make_data(elsewhere)
    (home / "logs").mkdir()
    (home / "logs" / "old.log").write_text("locked once", "utf-8")
    datadir.write_pointer({"data_dir": str(elsewhere)})
    datadir.request_move(elsewhere, str(home))

    assert datadir.apply_pending_move() is True

    assert sorted(p.name for p in (home / "logs").iterdir()) == ["backend.log", "old.log"]
    assert default_data_dir() == home
