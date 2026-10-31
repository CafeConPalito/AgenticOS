"""Appearance settings (phase 20, block 3; phase 22): the chosen theme and the custom themes."""

import json

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
    assert body == {"theme": "navy", "custom": [], "legacy_follow": None}


def test_saves_a_custom_theme(client: TestClient):
    saved = client.put(URL, json={"theme": "mi-tema", "custom": [warm_copy()]})
    assert saved.status_code == 200
    again = client.get(URL).json()
    assert again["theme"] == "mi-tema"
    assert again["custom"][0]["format"] == "agentic-os.theme"
    assert again["custom"][0]["version"] == 2
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
        {"custom": [warm_copy(font_family="Arial; } body { color: red")]},  # not a font name
        {"custom": [warm_copy(font_family=" Arial")]},
        {"custom": [warm_copy(font_family="x" * 81)]},
        {"custom": [warm_copy(version=3)]},
        {"surprise": True},
        {"mode": "system"},  # «Seguir al sistema» is gone (phase 22)
        {"legacy_follow": {"light_theme": "light", "dark_theme": "navy"}},  # read only
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


def test_a_theme_from_scratch_with_a_system_font(client: TestClient):
    scratch = warm_copy(extends=None, font_family="Cascadia Code", font=None)
    del scratch["extends"]
    assert client.put(URL, json={"theme": "mi-tema", "custom": [scratch]}).status_code == 200
    stored = client.get(URL).json()["custom"][0]
    assert stored["extends"] is None
    assert stored["font_family"] == "Cascadia Code"
    accents = warm_copy(font_family="Fuente Ñandú (Pro) 2.0 & Co + Más")
    assert client.put(URL, json={"custom": [accents]}).status_code == 200


def test_a_phase_20_theme_file_still_validates(client: TestClient):
    v1 = {"format": "agentic-os.theme", "version": 1, **warm_copy()}
    assert client.put(URL, json={"custom": [v1]}).status_code == 200
    assert client.get(URL).json()["custom"][0]["version"] == 1


def store(client: TestClient, document: dict) -> None:
    with client.app.state.sessionmaker() as db:
        db.add(AppState(key=APPEARANCE, value=json.dumps(document)))
        db.commit()


def test_a_phase_20_document_following_the_system_keeps_its_themes(client: TestClient):
    store(
        client,
        {
            "mode": "system",
            "theme": "navy",
            "light_theme": "mi-tema",
            "dark_theme": "graphite",
            "custom": [{"format": "agentic-os.theme", "version": 1, **warm_copy()}],
        },
    )
    body = client.get(URL).json()
    assert body["theme"] == "navy"
    assert body["legacy_follow"] == {"light_theme": "mi-tema", "dark_theme": "graphite"}
    assert body["custom"][0]["id"] == "mi-tema"
    # The interface picks the theme on screen and saves the new document: the hint is gone.
    assert client.put(URL, json={"theme": "graphite", "custom": body["custom"]}).status_code == 200
    assert client.get(URL).json()["legacy_follow"] is None


def test_a_phase_20_fixed_document_drops_the_old_fields(client: TestClient):
    store(
        client,
        {
            "mode": "fixed",
            "theme": "warm",
            "light_theme": "light",
            "dark_theme": "navy",
            "custom": [],
        },
    )
    assert client.get(URL).json() == {"theme": "warm", "custom": [], "legacy_follow": None}


def test_a_custom_theme_named_like_a_new_built_in_one_is_kept_with_another_id(client: TestClient):
    # Phase 20 let a person call a theme «Dracula» (id `dracula`); phase 22 ships one.
    store(
        client,
        {
            "mode": "system",
            "theme": "dracula",
            "light_theme": "dracula",
            "dark_theme": "navy",
            "custom": [
                warm_copy(id="dracula", name="Dracula"),
                warm_copy(id="dracula-2", name="Otro"),
                warm_copy(id="hijo", name="Hijo", extends="dracula"),
            ],
        },
    )
    body = client.get(URL).json()
    assert [t["id"] for t in body["custom"]] == ["dracula-3", "dracula-2", "hijo"]
    assert body["custom"][0]["name"] == "Dracula"
    assert body["custom"][2]["extends"] == "dracula-3"
    assert body["theme"] == "dracula-3"
    assert body["legacy_follow"] == {"light_theme": "dracula-3", "dark_theme": "navy"}
