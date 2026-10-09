"""P4 (context/instructions) and P6 (permissions) for both CLIs, in headless mode.

Each case runs in its own sandbox and checks a marker in the answer or a file on disk.

Usage: uv run python scenarios/context_perms.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config_guard, evidence, run_cli, sandbox  # noqa: E402

CLAUDE = ["claude", "--model", "haiku", "--strict-mcp-config", "--output-format", "json"]
AGY = ["agy", "--model", "gemini-3.8-flash-low", "--output-format", "json"]
WRITE = "Crea el archivo nota.txt con el texto hola. Después responde HECHO."
BASH = "Ejecuta en la terminal el comando: echo spike > salida.txt . Después responde HECHO."


@dataclass
class Case:
    cli: str
    name: str
    argv_extra: list[str]
    prompt: str
    files: dict[str, str] = field(default_factory=dict)
    expect_marker: str | None = None
    expect_file: str | None = None
    expect_file_present: bool = True


CASES = [
    # ---- P4: instructions -------------------------------------------------------------
    Case(
        "claude",
        "p4-append-system-prompt",
        ["--append-system-prompt", "Empieza SIEMPRE tu respuesta con la etiqueta [AOS-SYS]."],
        "Di hola.",
        expect_marker="[AOS-SYS]",
    ),
    Case(
        "claude",
        "p4-claude-md",
        [],
        "Di hola.",
        files={"CLAUDE.md": "Empieza SIEMPRE tu respuesta con la etiqueta [AOS-MD].\n"},
        expect_marker="[AOS-MD]",
    ),
    Case(
        "agy",
        "p4-agents-md",
        [],
        "Di hola.",
        files={"AGENTS.md": "Empieza SIEMPRE tu respuesta con la etiqueta [AOS-AGENTS].\n"},
        expect_marker="[AOS-AGENTS]",
    ),
    Case(
        "agy",
        "p4-gemini-md",
        [],
        "Di hola.",
        files={"GEMINI.md": "Empieza SIEMPRE tu respuesta con la etiqueta [AOS-GEMINI].\n"},
        expect_marker="[AOS-GEMINI]",
    ),
    Case(
        "agy",
        "p4-agents-rules-dir",
        [],
        "Di hola.",
        files={
            ".agents/rules/aos.md": "Empieza SIEMPRE tu respuesta con la etiqueta [AOS-RULE].\n"
        },
        expect_marker="[AOS-RULE]",
    ),
    # ---- P6: permissions --------------------------------------------------------------
    Case(
        "claude", "p6-default-write", [], WRITE, expect_file="nota.txt", expect_file_present=False
    ),
    Case(
        "claude",
        "p6-accept-edits-write",
        ["--permission-mode", "acceptEdits"],
        WRITE,
        expect_file="nota.txt",
    ),
    Case(
        "claude",
        "p6-accept-edits-bash",
        ["--permission-mode", "acceptEdits"],
        BASH,
        expect_file="salida.txt",
        expect_file_present=False,
    ),
    Case(
        "claude",
        "p6-allowed-tools-bash",
        ["--allowedTools", "Bash(echo:*)"],
        BASH,
        expect_file="salida.txt",
    ),
    Case(
        "claude",
        "p6-bypass-disallow-write",
        ["--permission-mode", "bypassPermissions", "--disallowedTools", "Write"],
        WRITE,
        expect_file="nota.txt",
        expect_file_present=False,
    ),
    Case("agy", "p6-default-write", [], WRITE, expect_file="nota.txt", expect_file_present=False),
    Case(
        "agy",
        "p6-mode-accept-edits-write",
        ["--mode", "accept-edits"],
        WRITE,
        expect_file="nota.txt",
    ),
    Case(
        "agy",
        "p6-mode-accept-edits-bash",
        ["--mode", "accept-edits"],
        BASH,
        expect_file="salida.txt",
        expect_file_present=False,
    ),
    Case(
        "agy",
        "p6-skip-permissions-bash",
        ["--dangerously-skip-permissions"],
        BASH,
        expect_file="salida.txt",
    ),
]


# Same Claude permission cases, but ignoring the user's settings (defaultMode, hooks…).
ISOLATED = ["--setting-sources", "project,local"]
CASES += [
    Case(
        c.cli,
        c.name + "-isolated",
        [*ISOLATED, *c.argv_extra],
        c.prompt,
        c.files,
        c.expect_marker,
        c.expect_file,
        c.expect_file_present,
    )
    for c in list(CASES)
    if c.cli == "claude" and c.name.startswith("p6-")
]


def run_case(case: Case) -> dict:
    cwd = sandbox(f"{case.cli}-{case.name}")
    for rel, content in case.files.items():
        target = cwd / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, "utf-8")
    base = CLAUDE if case.cli == "claude" else AGY
    argv = [*base, *case.argv_extra, "-p", case.prompt]
    result = run_cli(argv, cwd)
    out = result.json or {}
    answer = out.get("result") if case.cli == "claude" else out.get("response")
    answer = answer if isinstance(answer, str) else ""
    denials = out.get("permission_denials") or out.get("denied_actions")
    # A run that crashed (auth, rate limit, bad flag…) must never count as "permission denied".
    checks = [result.ok]
    if case.expect_marker:
        checks.append(case.expect_marker in answer)
    if case.expect_file:
        checks.append((cwd / case.expect_file).exists() == case.expect_file_present)
        if not case.expect_file_present:
            checks.append(bool(denials) or bool(answer.strip()))  # the agent did respond
    return {
        "cli": case.cli,
        "case": case.name,
        "ok": all(checks),
        "returncode": result.returncode,
        "argv_extra": " ".join(case.argv_extra) or "(ninguno)",
        "files": ", ".join(case.files) or "-",
        "answer": answer.strip().replace("\n", " ")[:120],
        "file_present": (cwd / case.expect_file).exists() if case.expect_file else None,
        "denials": json.dumps(denials, ensure_ascii=False)[:200] if denials else "",
        "stderr": result.stderr.replace("\n", " ")[:200],
        "cost": out.get("total_cost_usd"),
    }


def main() -> None:
    only = set(sys.argv[1:])
    results = []
    with config_guard("context-perms") as changes:
        for case in CASES:
            if only and case.name not in only and case.cli not in only:
                continue
            result = run_case(case)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False))
    lines = [
        "# Contexto (P4) y permisos (P6)\n",
        "| CLI | Caso | Flags | Archivos | OK | Archivo creado | Respuesta | Denegaciones |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['cli']} | {r['case']} | `{r['argv_extra']}` | {r['files']} | "
            f"{'✅' if r['ok'] else '❌'} | {r['file_present']} | {r['answer']} | "
            f"{r['denials'] or r['stderr'][:80]} |"
        )
    lines.append(f"\nConfiguración global: {changes or 'SIN CAMBIOS'}")
    evidence("p4-p6-context-permissions.md").write_text("\n".join(lines), "utf-8")


if __name__ == "__main__":
    main()
