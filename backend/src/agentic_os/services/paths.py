import os
from pathlib import Path

from agentic_os.errors import ApiError


def normalize(path: str) -> tuple[str, str]:
    """Returns (display path, comparison key). The key folds case and separators on Windows so
    `D:\\Proyectos\\Web` and `d:/proyectos/web` are the same project.

    Relative paths are rejected: they would resolve against the backend's working directory
    (the install folder or System32), not anywhere the user meant."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ApiError(422, "path_not_absolute", "use a full path to the folder", "path")
    resolved = candidate.resolve(strict=False)
    return str(resolved), os.path.normcase(str(resolved))


def ensure_folder(path: str, create: bool) -> None:
    folder = Path(path)
    if folder.exists():
        if not folder.is_dir():
            raise ApiError(422, "not_a_folder", "the path is not a folder", "path")
        if not os.access(folder, os.R_OK | os.W_OK):
            raise ApiError(422, "folder_not_accessible", "the folder is not writable", "path")
        return
    if not create:
        raise ApiError(422, "folder_not_found", "the folder does not exist", "path")
    try:
        folder.mkdir(parents=True)
    except OSError as error:
        raise ApiError(422, "folder_not_creatable", str(error), "path") from error
