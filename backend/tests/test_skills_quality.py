"""Does the right skill come up? (phase 17, block 11; CA5) A corpus of 20 skills (with families of
near-twins: three «cloud-*», three «video-*») and 40 tasks in Spanish and English, through the
product's own selection: with the real `multilingual-e5-small` (the model the phase 14 quality
test downloads) the expected skill is in the top three in at least 90 % of the tasks; without a
model, in at least 90 % of the tasks written in the skill's language (the cross-language ones
need the model; approved after spike S4)."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_knowledge_quality import CACHE, e5_files  # noqa: F401 - the model, a fixture

from agentic_os.services.localmodels import catalog, store
from agentic_os.services.skills import selection as sel

CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "skills" / "corpus.json").read_text("utf-8")
)
LANG = {s["name"]: s["lang"] for s in CORPUS["skills"]}
assert CACHE


def _library(client: TestClient) -> None:
    for skill in CORPUS["skills"]:
        response = client.post(
            "/api/skills",
            json={"scope": "general", "name": skill["name"], "description": skill["description"]},
        )
        assert response.status_code == 201, response.text


def _hit_rate(client: TestClient, tasks: list[dict], ranker) -> tuple[float, list[str]]:
    misses = []
    with client.app.state.sessionmaker() as db:
        skills = sel.visible(db, None, [])
        modes = sel.modes(db, skills, None, None)
        for task in tasks:
            chosen = sel.select_skills(
                skills,
                modes,
                task["text"],
                limit=3,
                embed_query=ranker.embed_query,
                model=ranker.model,
                floor=ranker.floor,
            )
            names = [o.skill.name for o in chosen.candidates]
            if not set(names) & set(task["expected"]):
                misses.append(f"{task['text'][:60]} → {names}")
    return 1 - len(misses) / len(tasks), misses


def test_without_a_model_the_skill_of_the_same_language_comes_up(client: TestClient):
    _library(client)
    same = [t for t in CORPUS["tasks"] if all(LANG[e] == t["lang"] for e in t["expected"])]
    assert len(same) >= 20
    rate, misses = _hit_rate(client, same, client.app.state.run_manager.skill_ranker())
    assert rate >= 0.9, misses


def test_with_the_meaning_model_the_skill_comes_up_in_any_language(
    client: TestClient,
    e5_files: Path,  # noqa: F811
):
    entry = catalog.entry("e5-small")
    data_dir = Path(client.app.state.settings.data_dir)
    shutil.copytree(e5_files, store.downloaded_folder(data_dir, entry), dirs_exist_ok=True)
    _library(client)
    ranker = client.app.state.run_manager.skill_ranker()
    assert ranker.model == "e5-small" and ranker.floor == pytest.approx(0.83)
    with client.app.state.sessionmaker() as db:
        assert all(s.vector_model == "e5-small" for s in sel.visible(db, None, []))
    rate, misses = _hit_rate(client, CORPUS["tasks"], ranker)
    assert rate >= 0.9, misses
