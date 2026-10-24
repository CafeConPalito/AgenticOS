"""The `SKILL.md` format and the limits of a skill (phase 17, spike S5).

A skill is a set of files with a `SKILL.md` at its root: a YAML header with `name` and
`description` (required) and a Markdown body. Other header fields (`license`, `metadata`,
`allowed-tools`, `disable-model-invocation`…) are kept as they are. The parser is tolerant: real
skills put unquoted colons in their description, which strict YAML rejects.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from agentic_os.services.knowledge.tokens import estimate_tokens
from agentic_os.services.skills.errors import SkillError

SKILL_MD = "SKILL.md"
NAME_MAX = 64
DESCRIPTION_MAX = 1024
MAX_TOKENS = 8_000  # SKILL.md; the largest of the 76 most installed skills has 7 026 (S5)
MAX_FILES = 300  # the 90th percentile has 68 files, the largest 200 (S5)
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
AGY_MAX_BYTES = 24 * 1024  # agy skips a larger SKILL.md (S2): it only goes through use_skill
PATH_MAX = 240

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONT = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S)
TOP_KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:(.*)$")
EXECUTABLE = frozenset(
    {
        ".py",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".psm1",
        ".bat",
        ".cmd",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".mts",
        ".rb",
        ".pl",
        ".php",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".jar",
        ".vbs",
    }
)
_RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", re.I)  # Windows device names


@dataclass
class ParsedSkill:
    name: str
    description: str
    meta: dict[str, Any]  # the whole header, name and description included
    body: str

    @property
    def model_invocable(self) -> bool:
        """`disable-model-invocation: true` means: only when someone asks for it by name."""
        return not bool(self.meta.get("disable-model-invocation"))


@dataclass
class CheckedSkill:
    parsed: ParsedSkill
    files: dict[str, bytes]  # normalised paths, SKILL.md included
    tokens: int
    executables: list[str] = field(default_factory=list)


def is_executable(path: str, data: bytes) -> bool:
    suffix = posixpath.splitext(path.lower())[1]
    return suffix in EXECUTABLE or data.startswith(b"#!")


def _lenient_header(raw: str) -> dict[str, Any]:
    """Top-level `key: value` lines when YAML refuses the header (an unquoted colon in the
    description is the usual cause). Indented lines continue the previous value."""
    meta: dict[str, Any] = {}
    key = None
    for line in raw.splitlines():
        match = TOP_KEY.match(line)
        if match and not line[:1].isspace():
            key = match.group(1)
            meta[key] = match.group(2).strip().strip("\"'")
        elif key and line.strip():
            meta[key] = f"{meta[key]} {line.strip()}".strip()
    return meta


def parse_skill_md(text: str) -> ParsedSkill:
    text = text.lstrip("﻿")
    match = FRONT.match(text)
    if not match:
        raise SkillError(
            "no_header",
            "El SKILL.md no empieza con una cabecera entre líneas «---» con «name» y "
            "«description».",
        )
    raw, body = match.group(1), match.group(2)
    try:
        meta = yaml.safe_load(raw)
    except yaml.YAMLError:
        meta = _lenient_header(raw)
    if not isinstance(meta, dict):
        raise SkillError("bad_header", "La cabecera del SKILL.md no es una lista de campos.")
    name = meta.get("name")
    description = meta.get("description")
    if not isinstance(name, str) or not name.strip():
        raise SkillError("no_name", "Falta el campo «name» en la cabecera del SKILL.md.")
    if description is None or not str(description).strip():
        raise SkillError(
            "no_description",
            "Falta la descripción («description»): es lo que se usa para elegir la skill.",
        )
    return ParsedSkill(name.strip(), " ".join(str(description).split()), meta, body.lstrip("\n"))


def compose_skill_md(meta: dict[str, Any], body: str) -> str:
    """The SKILL.md for `meta` and `body`, with name and description first. Other fields keep
    their values (the YAML is written again, so comments in the header are not kept)."""
    ordered = {k: meta[k] for k in ("name", "description") if k in meta}
    ordered.update({k: v for k, v in meta.items() if k not in ordered})
    header = yaml.safe_dump(
        ordered, allow_unicode=True, sort_keys=False, width=1_000, default_flow_style=False
    )
    return f"---\n{header}---\n\n{body.strip()}\n"


def validate_name(name: str) -> None:
    if len(name) > NAME_MAX or not NAME.match(name):
        raise SkillError(
            "bad_name",
            f"El nombre «{name}» no vale: solo minúsculas, números y guiones (p. ej. "
            f"«revision-de-codigo»), como mucho {NAME_MAX} caracteres.",
            name=name,
        )


def normalize_path(path: str) -> str:
    """A safe relative path with forward slashes, or SkillError."""
    clean = path.replace("\\", "/").strip()
    parts = [p for p in clean.split("/") if p not in ("", ".")]
    if (
        not parts
        or clean.startswith("/")
        or re.match(r"^[A-Za-z]:", clean)
        or any(p == ".." for p in parts)
        or any(_RESERVED.match(p) or p.endswith((" ", ".")) for p in parts)
        or any(ord(c) < 32 or c in '<>:"|?*' for c in clean)
    ):
        raise SkillError(
            "bad_path", f"La ruta «{path}» no es válida dentro de una skill.", path=path
        )
    normal = "/".join(parts)
    if len(normal) > PATH_MAX:
        raise SkillError("bad_path", f"La ruta «{path}» es demasiado larga.", path=path)
    return normal


def check_files(files: dict[str, bytes]) -> CheckedSkill:
    """Validates a whole skill (CA1): paths, limits, a SKILL.md at the root and its header."""
    normal: dict[str, bytes] = {}
    seen: set[str] = set()
    for path, data in files.items():
        key = normalize_path(path)
        if key.lower() == SKILL_MD.lower():
            key = SKILL_MD
        if key.lower() in seen:  # Windows folders ignore case
            raise SkillError("duplicate_path", f"El fichero «{key}» está repetido.", path=key)
        seen.add(key.lower())
        if len(data) > MAX_FILE_BYTES:
            raise SkillError(
                "file_too_large",
                f"El fichero «{key}» pasa de 1 MB.",
                path=key,
                limit=MAX_FILE_BYTES,
            )
        normal[key] = data
    if len(normal) > MAX_FILES:
        raise SkillError(
            "too_many_files",
            f"La skill tiene {len(normal)} ficheros; el máximo es {MAX_FILES}.",
            count=len(normal),
            limit=MAX_FILES,
        )
    total = sum(len(d) for d in normal.values())
    if total > MAX_TOTAL_BYTES:
        raise SkillError(
            "skill_too_large",
            "La skill pasa de 5 MB en total.",
            size=total,
            limit=MAX_TOTAL_BYTES,
        )
    if SKILL_MD not in normal:
        raise SkillError("no_skill_md", "Falta el SKILL.md en la raíz de la skill.")
    try:
        text = normal[SKILL_MD].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillError("not_utf8", "El SKILL.md no está en UTF-8.") from exc
    parsed = parse_skill_md(text)
    validate_name(parsed.name)
    if len(parsed.description) > DESCRIPTION_MAX:
        raise SkillError(
            "long_description",
            f"La descripción pasa de {DESCRIPTION_MAX} caracteres: resúmela en una o dos frases.",
            limit=DESCRIPTION_MAX,
        )
    tokens = estimate_tokens(text)
    if tokens > MAX_TOKENS:
        raise SkillError(
            "skill_md_too_long",
            f"El SKILL.md tiene unos {tokens} tokens; el máximo es {MAX_TOKENS}. Pasa el "
            "detalle a ficheros de apoyo.",
            tokens=tokens,
            limit=MAX_TOKENS,
        )
    executables = sorted(p for p, d in normal.items() if is_executable(p, d))
    return CheckedSkill(parsed, normal, tokens, executables)
