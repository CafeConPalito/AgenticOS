"""Topics of the graph (phase 15, block 3): coherent, stable and named after their documents."""

import random

from agentic_os.services.knowledge import topics

TITLES = {
    "celery": "Desarrollo con Celery",
    "retries": "Guía de reintentos en Celery",
    "queues": "Colas y enrutamiento en Celery",
    "redis": "Redis como broker y caché",
    "docker": "Docker: imágenes y contenedores",
    "compose": "Docker Compose para desarrollo",
    "multistage": "Imágenes pequeñas con multi-stage",
    "paella": "Paella valenciana",
}
DERIVED = [
    ("retries", "celery"),
    ("queues", "celery"),
    ("compose", "docker"),
    ("multistage", "docker"),
]
RELATED = [
    ("celery", "queues", 0.46),
    ("celery", "retries", 0.38),
    ("queues", "retries", 0.30),
    ("queues", "redis", 0.20),
    ("docker", "compose", 0.45),
    ("docker", "multistage", 0.40),
    ("compose", "multistage", 0.30),
    ("celery", "compose", 0.21),  # a weak bridge between the two topics
]


def compute(ids=None, derived=DERIVED, related=RELATED):
    return topics.compute(ids or sorted(TITLES), TITLES, derived, related)


def test_documents_about_the_same_thing_share_a_topic():
    found = {frozenset(t.doc_ids) for t in compute() if not t.loose}
    assert frozenset({"celery", "retries", "queues", "redis"}) in found
    assert frozenset({"docker", "compose", "multistage"}) in found


def test_a_document_without_links_is_loose_not_a_topic_of_its_own():
    *grouped, loose = compute()
    assert loose.loose and loose.name == "Sueltos" and loose.doc_ids == ["paella"]
    assert not any(t.loose for t in grouped)


def test_topics_are_ordered_by_size_and_named_after_their_documents():
    found = compute()
    assert [len(t.doc_ids) for t in found[:2]] == [4, 3]
    celery, docker = found[:2]
    assert celery.name.startswith("Desarrollo con Celery")  # its most linked document
    assert docker.name.startswith("Docker")
    assert len(celery.central) == 3 and celery.central[0] == "celery"
    assert celery.name != docker.name


def test_topics_know_their_neighbours():
    celery, docker, _ = compute()
    assert celery.neighbors == [docker.id] and docker.neighbors == [celery.id]


def test_the_same_documents_always_give_the_same_topics():
    base = [(t.name, t.doc_ids) for t in compute()]
    for seed in range(5):
        ids = sorted(TITLES)
        random.Random(seed).shuffle(ids)
        related = random.Random(seed).sample(RELATED, len(RELATED))
        derived = random.Random(seed).sample(DERIVED, len(DERIVED))
        assert [(t.name, t.doc_ids) for t in compute(ids, derived, related)] == base


def test_links_to_documents_that_are_not_there_are_ignored():
    found = compute(["celery", "queues"], DERIVED, RELATED)
    assert [t.doc_ids for t in found] == [["celery", "queues"]]


def test_no_documents_no_topics():
    assert topics.compute([], {}, [], []) == []
