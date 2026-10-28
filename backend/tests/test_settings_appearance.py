"""Appearance settings (phase 20, block 3): the chosen theme and the custom themes."""

from fastapi.testclient import TestClient

from agentic_os.models import APPEARANCE, AppState

URL = "/api/settings/appearance"


def warm_copy(**changes) -> dict:
    theme = {
        "id": "mi-tema",
        "name": "Mi tema",
        "base": "light",
        "extends": "warm",
        "colors": {"background": "#fdf6ec", "primary-action": "#a4441c"},
        "font": "atkinson",
        "scale": 1.1,
        "density": "comfortable",
        "radius": 14,
    }
    return {**theme, **changes}


def test_defaults_to_the_navy_theme(client: TestClient):
    body = client.get(URL).json()
    assert body == {
        "mode": "fixed",
        "theme": "navy",
        "light_theme": "light",
        "dark_theme": "navy",
        "custom": [],
    }


def test_saves_a_custom_theme_and_follows_the_system(client: TestClient):
    document = {
        "mode": "system",
        "theme": "mi-tema",
        "light_theme": "mi-tema",
        "dark_theme": "graphite",
        "custom": [warm_copy()],
    }
    saved = client.put(URL, json=document)
    assert saved.status_code == 200
    again = client.get(URL).json()
    assert again["mode"] == "system"
    assert again["light_theme"] == "mi-tema"
    assert again["custom"][0]["format"] == "agentic-os.theme"
    assert again["custom"][0]["colors"]["primary-action"] == "#a4441c"
    assert again["custom"][0]["font"] == "atkinson"


def test_refuses_bad_documents_and_keeps_what_was_saved(client: TestClient):
    client.put(URL, json={"theme": "light"})
    bad = [
        {"theme": "nope"},  # unknown theme
        {"custom": [warm_copy(id="navy")]},  # takes a built-in id
        {"custom": [warm_copy(), warm_copy()]},  # duplicated id
        {"custom": [warm_copy(extends="ghost")]},  # extends nothing
        {"custom": [warm_copy(colors={"background": "red"})]},  # not a hex color
        {"custom": [warm_copy(colors={"Back Ground": "#ffffff"})]},  # not a token name
        {"custom": [warm_copy(scale=3)]},  # out of range
        {"custom": [warm_copy(radius=-1)]},
        {"custom": [warm_copy(font="comic-sans")]},
        {"custom": [warm_copy(unknown=1)]},  # unknown field
        {"surprise": True},
    ]
    for document in bad:
        response = client.put(URL, json=document)
        assert response.status_code == 422, document
    assert client.get(URL).json()["theme"] == "light"


def test_unreadable_stored_value_falls_back_to_the_defaults(client: TestClient):
    with client.app.state.sessionmaker() as db:
        db.add(AppState(key=APPEARANCE, value='{"theme": "deleted-theme"}'))
        db.commit()
    assert client.get(URL).json()["theme"] == "navy"
