"""Phase 17 · spike S1: Claude Code skills per run.

Questions:
  (a) does `--plugin-dir <dir>` (or `--add-dir` with `.claude/skills/` inside) load skills for one
      session without writing to ~/.claude?
  (b) with `--setting-sources project,local`, are the user's own skills (~/.claude/skills) and
      plugins still loaded? Does `--safe-mode` or `--disable-slash-commands` turn them off, and
      what else do they turn off (our --settings hooks, our --mcp-config)?
  (c) does PreToolUse see the `Skill` tool with the skill's name?
  (d) can the model run a skill's script under each permission mode?

Usage: uv run python skills/s1_claude.py [scenario ...]   (from spikes/)
Each scenario is a cheap `claude -p` run with haiku. Evidence: docs/phases/17-skills/evidencias/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ConfigSnapshot, sandbox  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "17-skills" / "evidencias"
HOOK_LOGGER = REPO / "spikes" / "hook_logger.py"
MODEL = "haiku"
PLUGIN_SKILL = "aos-probe-plugin"
ADDDIR_SKILL = "aos-probe-adddir"
MARK = "PROBE-SKILL-LOADED-7731"
SCRIPT_MARK = "PROBE-SCRIPT-RAN-5519"
KEEP = {"CLAUDE_CODE_GIT_BASH_PATH", "CLAUDE_CONFIG_DIR"}

LIST_PROMPT = (
    "Without calling any tool, look at the skills you have available (the list attached to "
    "your Skill tool). Answer ONLY with a JSON array of their exact names, nothing else. "
    "If you have none, answer []."
)
USE_PROMPT = (
    "Use your skill named aos-probe-plugin and do exactly what it says. Then answer with the "
    "text it told you to answer."
)
MCP_PROMPT = (
    "Without calling any tool, answer ONLY with a JSON array of the names of the MCP servers "
    'whose tools you have (e.g. ["agentic-os"]), or [] if none.'
)


def clean_env() -> dict[str, str]:
    env = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper in KEEP:
            env[key] = value
        elif upper in {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"} or upper.startswith(
            ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK")
        ):
            continue
        else:
            env[key] = value
    return env


def write_plugin(root: Path) -> Path:
    plugin = root / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agentic-os-run", "version": "0.0.1"}), "utf-8"
    )
    skill = plugin / "skills" / PLUGIN_SKILL
    (skill / "scripts").mkdir(parents=True)
    script = skill / "scripts" / "probe.py"
    script.write_text(f'print("{SCRIPT_MARK}")\n', "utf-8")
    (skill / "SKILL.md").write_text(
        f"---\nname: {PLUGIN_SKILL}\ndescription: Probe skill of the Agentic OS spike. Use it "
        "only when explicitly asked for aos-probe-plugin.\n---\n\n"
        f"Run the script `scripts/probe.py` of this skill with python (its absolute path is "
        f"{script.as_posix()}) and then answer with the line `{MARK}` followed by the "
        "script's output.\n",
        "utf-8",
    )
    return plugin


def write_adddir(root: Path) -> Path:
    folder = root / "extra"
    skill = folder / ".claude" / "skills" / ADDDIR_SKILL
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {ADDDIR_SKILL}\ndescription: Probe skill loaded through --add-dir.\n---\n\n"
        f"Answer `{MARK}-ADDDIR`.\n",
        "utf-8",
    )
    return folder


def write_settings(root: Path, log: Path) -> Path:
    command = f'python "{HOOK_LOGGER.as_posix()}" claude PreToolUse "{log.as_posix()}"'
    settings = {
        "hooks": {
            "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": command}]}],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command.replace("PreToolUse", "Stop"),
                        }
                    ]
                }
            ],
        }
    }
    path = root / "settings.json"
    path.write_text(json.dumps(settings), "utf-8")
    return path


def write_mcp(root: Path) -> Path:
    # A server that does not exist: we only check whether Claude *declares* it (it shows as
    # failed, but its name is configured). The real MCP is checked in the e2e of block 3.
    path = root / "mcp.json"
    path.write_text(
        json.dumps(
            {"mcpServers": {"agentic-os": {"type": "http", "url": "http://127.0.0.1:9/r/mcp"}}}
        ),
        "utf-8",
    )
    return path


def run(name: str, prompt: str, extra: list[str], root: Path, permission: str = "default"):
    argv = [
        "claude",
        "-p",
        prompt,
        "--model",
        MODEL,
        "--output-format",
        "json",
        "--setting-sources",
        "project,local",
        "--permission-mode",
        permission,
        *extra,
    ]
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=root,
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        shell=os.name == "nt",
    )
    took = round(time.monotonic() - started, 1)
    answer = result.stdout.strip()
    try:
        data = json.loads(answer)
        answer = data.get("result", answer)
        cost = data.get("total_cost_usd")
    except json.JSONDecodeError:
        cost = None
    return {
        "scenario": name,
        "argv": [a if len(a) < 120 else a[:117] + "..." for a in argv[3:]],
        "exit": result.returncode,
        "seconds": took,
        "cost_usd": cost,
        "answer": answer[:1500],
        "stderr": result.stderr.strip()[:800],
    }


def scenarios(root: Path, log: Path) -> dict[str, tuple[str, list[str], str]]:
    plugin = write_plugin(root)
    extra = write_adddir(root)
    settings = write_settings(root, log)
    mcp = write_mcp(root)
    ours = ["--settings", str(settings), "--mcp-config", str(mcp), "--strict-mcp-config"]
    return {
        # (b) what the current launch (ADR 0004) sees, with nothing of ours
        "baseline": (LIST_PROMPT, ours, "default"),
        # (a) one plugin for this session
        "plugin_dir": (LIST_PROMPT, [*ours, "--plugin-dir", str(plugin)], "default"),
        # (a) a skills folder through --add-dir
        "add_dir": (LIST_PROMPT, [*ours, "--add-dir", str(extra)], "default"),
        # (b) isolation candidates
        "safe_mode": (LIST_PROMPT, [*ours, "--plugin-dir", str(plugin), "--safe-mode"], "default"),
        "safe_mode_mcp": (MCP_PROMPT, [*ours, "--safe-mode"], "default"),
        "disable_slash": (
            LIST_PROMPT,
            [*ours, "--plugin-dir", str(plugin), "--disable-slash-commands"],
            "default",
        ),
        # (c) + (d) the model loads the skill and runs its script
        "use_bypass": (USE_PROMPT, [*ours, "--plugin-dir", str(plugin)], "bypassPermissions"),
        "use_accept_edits": (USE_PROMPT, [*ours, "--plugin-dir", str(plugin)], "acceptEdits"),
        "use_safe_mode": (
            USE_PROMPT,
            [*ours, "--plugin-dir", str(plugin), "--safe-mode"],
            "bypassPermissions",
        ),
    }


def skills_tree() -> dict[str, tuple[int, int]]:
    """Files of the user's skills and plugin registry, with size and mtime."""
    home = Path.home() / ".claude"
    tree = {}
    for base in (home / "skills", home / "plugins" / "installed_plugins.json"):
        paths = [base] if base.is_file() else list(base.rglob("*")) if base.exists() else []
        for path in paths:
            if path.is_file():
                stat = path.stat()
                tree[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return tree


def main() -> None:
    wanted = set(sys.argv[1:])
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    root = sandbox("s1-claude-skills")
    log = root / "hooks.jsonl"
    before = ConfigSnapshot.take()
    tree_before = skills_tree()
    results = []
    for name, (prompt, extra, permission) in scenarios(root, log).items():
        if wanted and name not in wanted:
            continue
        mark = log.stat().st_size if log.exists() else 0
        outcome = run(name, prompt, extra, root, permission)
        hooks = []
        if log.exists():
            with log.open(encoding="utf-8") as fh:
                fh.seek(mark)
                for line in fh:
                    entry = json.loads(line)
                    payload = entry.get("payload") or {}
                    hooks.append(
                        {
                            "event": entry["event"],
                            "tool": payload.get("tool_name"),
                            "input": json.dumps(payload.get("tool_input"), ensure_ascii=False)[:300]
                            if payload.get("tool_input") is not None
                            else None,
                        }
                    )
        outcome["hooks"] = hooks
        results.append(outcome)
        print(json.dumps(outcome, ensure_ascii=False, indent=1))
    changes = before.diff(ConfigSnapshot.take())
    tree_after = skills_tree()
    changes += [
        f"skills/plugins changed: {path}"
        for path in sorted(set(tree_before) | set(tree_after))
        if tree_before.get(path) != tree_after.get(path)
    ]
    report = {"sandbox": str(root), "config_changes": changes, "results": results}
    out = EVIDENCE / f"s1-claude-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print("config changes:", changes or "none")
    print("evidence:", out)


if __name__ == "__main__":
    main()
