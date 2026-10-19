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
