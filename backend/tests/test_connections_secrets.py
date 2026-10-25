"""The secrets of the MCP connections (phase 18, block 1): the credential store with its
pieces, the placeholders, and the hiding of the secret values in a run's output (CA3)."""

import asyncio
import json
from pathlib import Path

import pytest

from agentic_os.services.connections import secrets
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.connections.redact import MASK, Redactor
from agentic_os.services.runs import session as session_module
from agentic_os.services.runs.launcher import LaunchSpec


# -- the store ----------------------------------------------------------------------------------
def test_a_secret_is_saved_read_and_deleted(credential_store):
    secrets.put("c1", "TOKEN", "ghp_abc123")
    assert secrets.get("c1", "TOKEN") == "ghp_abc123"
    assert secrets.has("c1", "TOKEN") and not secrets.has("c1", "OTHER")
    assert secrets.status("c1", ["TOKEN", "OTHER"]) == {"TOKEN": True, "OTHER": False}
    secrets.delete("c1", "TOKEN")
    assert secrets.get("c1", "TOKEN") is None
    assert not credential_store.entries  # no piece is left behind


@pytest.mark.parametrize("size", [0, 1, 999, 1_000, 1_001, 4_000, 9_000])
def test_a_long_value_is_cut_into_pieces_the_system_store_accepts(credential_store, size):
    value = "".join(chr(97 + i % 26) for i in range(size))
    secrets.put("c1", "JWT", value)
    assert secrets.get("c1", "JWT") == value
    assert all(len(v) <= 1_280 for v in credential_store.entries.values())  # Windows limit (S5)
    secrets.delete("c1", "JWT")
    assert not credential_store.entries


def test_a_unicode_value_survives(credential_store):
    secrets.put("c1", "K", "tókén-ñ-日本-🔑")
    assert secrets.get("c1", "K") == "tókén-ñ-日本-🔑"


def test_a_shorter_value_leaves_no_old_pieces(credential_store):
    secrets.put("c1", "K", "x" * 3_500)
    secrets.put("c1", "K", "y" * 10)
    assert secrets.get("c1", "K") == "y" * 10
    assert len(credential_store.entries) == 2  # the head and one piece


def test_secrets_of_two_connections_do_not_mix():
    secrets.put("c1", "TOKEN", "one")
    secrets.put("c2", "TOKEN", "two")
    assert secrets.get("c1", "TOKEN") == "one" and secrets.get("c2", "TOKEN") == "two"
    secrets.delete_all("c1", ["TOKEN"])
    assert secrets.get("c2", "TOKEN") == "two"


def test_a_bad_key_is_refused_in_words():
    with pytest.raises(ConnectionError_) as error:
        secrets.put("c1", "con espacio", "x")
    assert error.value.code == "secret_key_invalid" and "no es válido" in error.value.message


def test_a_store_that_fails_says_so_in_words():
    class Broken:
        def get(self, service, name):
            raise RuntimeError("no backend")

        set = delete = get

    previous = secrets.use(secrets.KeyringStore())
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        keyring.set_keyring(FailKeyring())
        with pytest.raises(ConnectionError_) as error:
            secrets.put("c1", "TOKEN", "x")
        assert error.value.code == "secrets_unavailable" and error.value.status == 503
        assert "${env:NOMBRE}" in error.value.message
    finally:
        secrets.use(previous)


# -- placeholders -------------------------------------------------------------------------------
def test_placeholders_are_found_and_resolved(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "from-the-system")
    secrets.put("c1", "TOKEN", "from-the-store")
    text = "Bearer ${secret:TOKEN} and ${env:MY_TOKEN} and ${secret:TOKEN}"
    assert secrets.placeholders(text) == [
        ("secret", "TOKEN"),
        ("env", "MY_TOKEN"),
        ("secret", "TOKEN"),
    ]
    assert secrets.secret_keys_in(text, "x ${secret:OTHER}") == ["TOKEN", "OTHER"]
    seen: set[str] = set()
    resolved = secrets.resolve_text(text, "c1", "github", seen)
    assert resolved == "Bearer from-the-store and from-the-system and from-the-store"
    assert seen == {"from-the-store", "from-the-system"}


def test_a_missing_secret_is_named_in_words(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    with pytest.raises(ConnectionError_) as error:
        secrets.resolve_text("${secret:TOKEN}", "c1", "github", set())
    assert error.value.code == "secret_missing"
    assert "«TOKEN»" in error.value.message and "«github»" in error.value.message
    with pytest.raises(ConnectionError_) as error:
        secrets.resolve_text("${env:NOPE}", "c1", "github", set())
    assert "variable del sistema" in error.value.message


def test_text_without_placeholders_is_left_alone():
    assert secrets.resolve_text("plain ${not a placeholder}", "c1", "x", set()) == (
        "plain ${not a placeholder}"
    )


# -- hiding -------------------------------------------------------------------------------------
def test_a_secret_is_hidden():
    redactor = Redactor({"ghp_SECRET_VALUE"})
    assert redactor.feed("token=ghp_SECRET_VALUE ok") + redactor.flush() == f"token={MASK} ok"


def test_a_secret_cut_between_two_pieces_is_hidden():
    redactor = Redactor({"ghp_SECRET_VALUE"})
    out = redactor.feed("token=ghp_SEC")
    out += redactor.feed("RET_VALUE done")
    out += redactor.flush()
    assert out == f"token={MASK} done"
    assert "ghp_" not in out and "SEC" not in out


def test_a_cut_that_turns_out_not_to_be_the_secret_is_released():
    redactor = Redactor({"ghp_SECRET_VALUE"})
    out = redactor.feed("see ghp_SE")
    out += redactor.feed("EN you")  # not the secret
    out += redactor.flush()
    assert out == "see ghp_SEEN you"


def test_the_end_of_the_output_releases_what_was_held():
    redactor = Redactor({"ghp_SECRET_VALUE"})
    assert redactor.feed("ends with ghp_SEC") == "ends with "
    assert redactor.flush() == "ghp_SEC"


def test_the_longer_secret_wins_and_short_values_are_ignored():
    redactor = Redactor({"abcdef", "abcdefghij", "ab"})  # «ab» is too short to hide
    assert redactor.feed("x abcdefghij y ab z") + redactor.flush() == f"x {MASK} y ab z"


def test_every_piece_goes_through_unchanged_without_secrets():
    redactor = Redactor(set())
    assert not redactor.active and redactor.feed("hello") == "hello"


def test_many_small_pieces_never_leak_the_secret():
    secret = "S3cr3t-Value-8841"
    redactor = Redactor({secret})
    text = f"before {secret} middle {secret} after"
    out = "".join(redactor.feed(ch) for ch in text) + redactor.flush()
    assert secret not in out and out.count(MASK) == 2
    assert out == f"before {MASK} middle {MASK} after"


# -- the session --------------------------------------------------------------------------------
class _StubPty:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = list(chunks)
        self.exit_code = 0

    def read(self) -> str:
        return self._chunks.pop(0) if self._chunks else ""

    def is_alive(self) -> bool:
        return False


def _open_log(session: session_module.RunSession) -> None:
    session.log_path.parent.mkdir(parents=True, exist_ok=True)
    session._log = session.log_path.open("a", encoding="utf-8", newline="")  # as start() does


def test_the_session_hides_secrets_in_the_log_the_scrollback_and_the_viewers(tmp_path: Path):
    secret = "ghp_SECRET_VALUE_1234"
    session = session_module.RunSession(
        "r1",
        session_module.Cli.CLAUDE,
        LaunchSpec(["x"], {}, None),
        str(tmp_path),
        tmp_path / "runs" / "r1.log",
        asyncio.new_event_loop(),
        lambda changes: None,
        redactor=Redactor({secret}),
    )
    seen: list[dict] = []
    session._publish = seen.append  # the live viewers
    _open_log(session)
    session._pty = _StubPty(["The token is ghp_SECRET_", "VALUE_1234, bye\r\n"])
    session._read_loop()
    log = (tmp_path / "runs" / "r1.log").read_text(encoding="utf-8")
    scrollback = "".join(session._scrollback)
    viewers = "".join(m["data"] for m in seen if m["type"] == "output")
    for where in (log, scrollback, viewers):
        assert secret not in where and "ghp_SECRET" not in where
        assert f"The token is {MASK}, bye" in where


def test_a_session_without_secrets_is_unchanged(tmp_path: Path):
    session = session_module.RunSession(
        "r2",
        session_module.Cli.CLAUDE,
        LaunchSpec(["x"], {}, None),
        str(tmp_path),
        tmp_path / "runs" / "r2.log",
        asyncio.new_event_loop(),
        lambda changes: None,
    )
    session._publish = lambda message: None
    _open_log(session)
    session._pty = _StubPty(["plain ", "output"])
    session._read_loop()
    assert (tmp_path / "runs" / "r2.log").read_text(encoding="utf-8") == "plain output"


def test_the_credential_store_json_head_is_not_the_value(credential_store):
    secrets.put("c1", "K", "the-value")
    heads = [v for k, v in credential_store.entries.items() if not k[1].endswith("#0")]
    assert all("the-value" not in v for v in heads)
    assert json.loads(heads[0]) == {"n": 1}
