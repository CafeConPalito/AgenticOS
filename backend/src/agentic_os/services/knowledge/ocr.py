"""Reading the text of pictures and scanned pages (phase 14, block 4): RapidOCR on ONNX Runtime.

Runs in the knowledge worker. The three models are the ones the catalog pins (shipped inside the
installer); they are handed over by path, so RapidOCR never goes to the network for its own.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

MIN_CONFIDENCE = 0.5  # lines the recognizer is less sure of than this are noise
MAX_CHARS = 20_000  # of one picture: a picture of a whole book page is already plenty

Progress = Callable[[int, int], None]
_engines: dict[tuple, object] = {}


def default_threads() -> int:
    """Half of the cores: the OCR must not take the machine away from the person."""
    return max(1, (os.cpu_count() or 2) // 2)


def engine(models: dict[str, str], threads: int):
    """The engine for these models, created once per worker process."""
    key = (models["det"], models["cls"], models["rec"], threads)
    if key not in _engines:
        from rapidocr import RapidOCR  # heavy (OpenCV): only when there is something to read

        _engines.clear()  # one set of models at a time
        _engines[key] = RapidOCR(
            params={
                "Det.model_path": models["det"],
                "Cls.model_path": models["cls"],
                "Rec.model_path": models["rec"],
                "EngineConfig.onnxruntime.intra_op_num_threads": threads,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            }
        )
    return _engines[key]


def read(ocr, path: Path) -> str:
    """The text of one picture, a line per line, in reading order."""
    result = ocr(str(path))
    if result is None or not result.txts:
        return ""
    scores = result.scores or [1.0] * len(result.txts)
    lines = [t.strip() for t, s in zip(result.txts, scores, strict=False) if s >= MIN_CONFIDENCE]
    return "\n".join(line for line in lines if line)[:MAX_CHARS]


def read_all(
    folder: Path,
    files: dict[int, str],
    models: dict[str, str],
    threads: int,
    progress: Progress | None = None,
) -> tuple[dict[int, str], int]:
    """Reads every picture of `files` ({number: name inside folder}). Returns the text of each
    ({number: text}) and how many could not be read at all."""
    ocr = engine(models, threads or default_threads())
    texts: dict[int, str] = {}
    failed = 0
    for done, (number, name) in enumerate(files.items(), 1):
        try:
            texts[number] = read(ocr, folder / name)
        except Exception:
            texts[number] = ""
            failed += 1
        if progress:
            progress(done, len(files))
    return texts, failed
