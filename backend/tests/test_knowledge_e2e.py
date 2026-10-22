"""The knowledge library end to end (phase 14): a real backend, the real worker process, every
format. With AGENTIC_OS_E2E_BINARY it is the packaged sidecar that converts, so it catches the
modules and data files missing from the build (the worker is that same executable, started with
`--knowledge-worker`)."""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest
from live_server import BINARY, live_server
from test_scheduler_e2e import Api, settings_for, wait_until

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
NAMES = [
    "manual.pdf",
    "manual_escaneado.pdf",
    "informe.docx",
    "ventas.xlsx",
    "presentacion.pptx",
    "captura_error.png",
    "pagina.html",
    "notas.md",
    "ejemplo.py",
]


def test_every_format_is_converted_by_the_worker_process(tmp_path: Path):
    folder = tmp_path / "docs"
    folder.mkdir()
    for name in NAMES:
        shutil.copy(FIXTURES / name, folder / name)
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        added = api.post(
            "/api/knowledge/docs/files",
            {"scope": "general", "paths": [str(folder / name) for name in NAMES]},
        )
        ids = {item["doc"]["title"]: item["doc"]["id"] for item in added}
        assert set(ids) == set(NAMES)

        def states() -> dict[str, str]:
            return {d["title"]: d["status"] for d in api.get("/api/knowledge/docs")}

        assert wait_until(lambda: set(states().values()) <= {"ready", "failed"}, timeout=180), (
            states()
        )
        assert states() == dict.fromkeys(NAMES, "ready"), api.get("/api/knowledge/docs")

        def markdown(name: str) -> str:
            return api.get(f"/api/knowledge/docs/{ids[name]}/markdown")["markdown"]

        assert markdown("manual.pdf").count("<!-- page: ") == 5
        assert "Básico 100 1 9 €" in markdown("manual.pdf")  # UTF-8 across the worker's pipe
        assert "| Enero | 412 | 18300 |" in markdown("ventas.xlsx")
        assert "kimg:0" in markdown("informe.docx") and "base64" not in markdown("informe.docx")
        assert "Inicio | Precios" not in markdown("pagina.html")
        assert markdown("ejemplo.py").startswith("```python")

        if BINARY:  # the packaged app carries the OCR models: pictures and scans are read
            assert "> Texto de la imagen:" in markdown("informe.docx")
            assert "Emitida" in markdown("informe.docx")
            scanned = markdown("manual_escaneado.pdf")
            assert "ERR_4012" in scanned and "BIENVENIDA25" in scanned and "kimg" not in scanned
            assert "ERR_4012" in markdown("captura_error.png")

        # The worker is a process of its own, and the machine's load can be read.
        system = api.get("/api/knowledge/system")
        assert system["memory"]["total_mb"] > 0 and "gpu" in system
        assert api.get("/api/knowledge/queue")["queued"] == 0

        # Reprocessing goes through the same worker.
        again = api.post(f"/api/knowledge/docs/{ids['notas.md']}/reprocess")
        assert again["status"] in ("queued", "converting", "ready")
        assert wait_until(lambda: states()["notas.md"] == "ready")
        assert httpx.get(
            f"{server.url}/api/knowledge/docs/{ids['notas.md']}", timeout=10
        ).is_success


@pytest.mark.skipif(not BINARY, reason="only the packaged app carries the models")
def test_the_ocr_models_ship_inside_the_packaged_app(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        models = {m["id"]: m for m in Api(server).get("/api/local-models")["models"]}
        ocr = models["ocr-latin"]
        assert (ocr["state"], ocr["bundled"]) == ("ready", True)  # no download, no internet
        # The rest is downloaded on demand, as always.
        assert (models["e5-small"]["state"], models["e5-small"]["bundled"]) == ("absent", False)
        assert not (tmp_path / "data" / "models").exists()  # nothing was copied to the data folder


def test_search_by_meaning_works_with_the_real_model(tmp_path: Path):
    """The embedding worker (ONNX Runtime + tokenizers) in a real process: in the packaged app,
    the sidecar itself."""
    import tempfile

    from agentic_os.services.localmodels import catalog, store
    from agentic_os.services.localmodels.stage import stage

    entry = catalog.entry("e5-small")
    cache = Path(tempfile.gettempdir()) / "agentic-os-test-models"
    if not stage(cache, [entry], log=lambda _: None):
        pytest.skip("the embedding model cannot be downloaded (no network?)")
    target = tmp_path / "data" / "models" / "e5-small"
    shutil.copytree(store.downloaded_folder(cache, entry), target)
    folder = tmp_path / "docs"
    folder.mkdir()
    texts = {
        "baja.md": "# Cancelación\n\nPara dar de baja el servicio pulse Cancelar suscripción.",
        "copias.md": "# Copias\n\nCada noche se hace una copia de seguridad cifrada.",
        "errores.md": "# Errores\n\nEl código ERR_5103 indica que la firma no está disponible.",
    }
    for name, text in texts.items():
        (folder / name).write_text(text, encoding="utf-8")
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        api.post(
            "/api/knowledge/docs/files",
            {"scope": "general", "paths": [str(folder / name) for name in texts]},
        )
        assert wait_until(
            lambda: {d["status"] for d in api.get("/api/knowledge/docs")} == {"ready"}, timeout=180
        )
        assert {d["embed_model"] for d in api.get("/api/knowledge/docs")} == {"e5-small"}

        def ask(query: str) -> dict:
            return api.post("/api/knowledge/search", {"query": query})

        answer = ask("¿Cómo dejo de pagar el servicio?")
        assert (answer["mode"], answer["model"]) == ("hybrid", "e5-small")
        assert answer["hits"][0]["title"] == "baja.md"
        assert (
            ask("¿Cada cuánto hacen un respaldo de mis datos?")["hits"][0]["title"] == "copias.md"
        )
        assert ask("ERR_5103")["hits"][0]["title"] == "errores.md"


def test_an_agent_uses_a_pdf_of_the_project_to_answer(tmp_path: Path):
    """CA1: a task whose answer is only in a PDF of the project. The agent (the fake CLI, with a
    real MCP client) sees the document in its context, searches it and reads a page."""
    from test_hitl_e2e import setup

    manual = tmp_path / "docs" / "manual.pdf"
    manual.parent.mkdir()
    shutil.copy(FIXTURES / "manual.pdf", manual)
    project_folder = tmp_path / "web-claude"
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, "claude")
        api.post(
            "/api/knowledge/docs/files",
            {"scope": "project", "project_id": project, "paths": [str(manual)]},
        )
        assert wait_until(
            lambda: {d["status"] for d in api.get("/api/knowledge/docs")} == {"ready"}, timeout=120
        )
        title = (
            "cómo darse de baja; CONTEXTO: ctx.txt; BUSCA: dar de baja la suscripción|busca.txt; "
            "LEE: manual||pagina.txt; TERMINA: respondido"
        )
        task = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        done = api.wait_status(task["id"], "done")

        context = (project_folder / "ctx.txt").read_text("utf-8")
        assert "## Conocimiento" in context and "**manual.pdf**" in context
        answer = (project_folder / "busca.txt").read_text("utf-8")
        assert "manual.pdf" in answer and "Cancelación de la suscripción" in answer
        assert "pulse Dar de baja" in answer
        whole = (project_folder / "pagina.txt").read_text("utf-8")
        assert "Cancelación de la suscripción" in whole  # the whole PDF, by pages

        events = api.get(f"/api/runs/{done['last_run_id']}/events")
        names = [e["name"] for e in events if e["kind"] == "mcp"]
        assert "search_knowledge" in names and "read_knowledge" in names
        detail = next(e["detail"] for e in events if e["name"] == "search_knowledge")
        assert "manual.pdf" in detail  # the run says which documents it consulted


def test_an_agent_proposes_knowledge_and_walks_the_graph(tmp_path: Path):
    """Phase 15 (CA1, CA12, CA16): the whole flow with a real run — also with the packaged app.
    The fake CLI proposes a guide based on the project's PDF; the person accepts it from the
    Inbox's data; a second run finds it, draws the map, explores from the PDF and reads the
    context with the topics."""
    from test_hitl_e2e import setup

    manual = tmp_path / "docs" / "manual.pdf"
    manual.parent.mkdir()
    shutil.copy(FIXTURES / "manual.pdf", manual)
    project_folder = tmp_path / "web-claude"
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, "claude")
        api.post(
            "/api/knowledge/docs/files",
            {"scope": "project", "project_id": project, "paths": [str(manual)]},
        )
        assert wait_until(
            lambda: {d["status"] for d in api.get("/api/knowledge/docs")} == {"ready"}, timeout=120
        )
        pdf = api.get("/api/knowledge/docs")[0]
        before = api.get(f"/api/knowledge/docs/{pdf['id']}/markdown")["markdown"]

        title = "propuesta; PROPONE: Guia de bajas|manual|prop.txt; TERMINA: propuesto"
        first = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        api.wait_status(first["id"], "done")
        assert (project_folder / "prop.txt").read_text("utf-8").startswith("Propuesta registrada")

        [proposal] = api.get("/api/knowledge/docs?review=proposed")
        assert proposal["origin"] == "agent" and proposal["sources"][0]["id"] == pdf["id"]
        assert [i for i in api.get("/api/inbox") if i["kind"] == "knowledge"]
        accepted = api.post(f"/api/knowledge/docs/{proposal['id']}/accept", {})
        assert accepted["review"] == "none"
        assert wait_until(
            lambda: api.get(f"/api/knowledge/docs/{proposal['id']}")["status"] == "ready",
            timeout=120,
        )
        assert api.get(f"/api/knowledge/docs/{pdf['id']}/markdown")["markdown"] == before

        title = (
            "recorrido; MAPA: mapa.txt; EXPLORA: manual.pdf|2|explora.txt; "
            "BUSCA: contenido verificado sobre este tema|busca.txt; CONTEXTO: ctx.txt; "
            "TERMINA: recorrido"
        )
        second = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        done = api.wait_status(second["id"], "done")
        assert "Mapa del conocimiento: 2 documentos" in (project_folder / "mapa.txt").read_text(
            "utf-8"
        )
        assert "Guia de bajas" in (project_folder / "explora.txt").read_text("utf-8")
        found = (project_folder / "busca.txt").read_text("utf-8")
        assert "Guia de bajas" in found and "generado por agente" in found
        context = (project_folder / "ctx.txt").read_text("utf-8")
        assert "Temas: " in context and "propose_knowledge" in context

        names = [e["name"] for e in api.get(f"/api/runs/{done['last_run_id']}/events")]
        assert {"knowledge_map", "explore_knowledge", "search_knowledge"} <= set(names)
