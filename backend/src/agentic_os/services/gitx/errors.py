"""Git failures as stable codes (phase 12, ADR 0017).

The UI translates by `code`; `message` is git's own last line, for whoever reads the log.
"""

from __future__ import annotations

import re

from agentic_os.errors import ApiError

# (code, pattern over git's stderr+stdout), first match wins. git runs with LC_ALL=C, so the
# texts are English.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "auth_failed",
        re.compile(
            r"Authentication failed|could not read (Username|Password)|terminal prompts disabled"
            r"|Permission denied \(publickey|Host key verification failed|HTTP Basic: Access denied"
            r"|The requested URL returned error: 40[13]",
            re.I,
        ),
    ),
    (
        "network",
        re.compile(
            r"Could not resolve host|unable to access|Connection (timed out|refused|reset)"
            r"|Network is unreachable|Failed to connect|early EOF|SSL (certificate|connect)"
            r"|Could not read from remote repository|ssh: connect to host",
            re.I,
        ),
    ),
    (
        "non_fast_forward",
        re.compile(
            r"non-fast-forward|\[rejected\]|fetch first|Updates were rejected"
            r"|Not possible to fast-forward|have diverged",
            re.I,
        ),
    ),
    (
        "conflicts",
        re.compile(r"CONFLICT \(|Automatic merge failed|could not apply|Merge conflict in", re.I),
    ),
    (
        "dirty_worktree",
        re.compile(
            r"would be overwritten by (checkout|merge)|Please commit your changes or stash"
            r"|Your local changes to the following files|You have unstaged changes"
            r"|cannot (pull|rebase|merge) with rebase: You have|untracked working tree files",
            re.I,
        ),
    ),
    (
        "operation_in_progress",
        re.compile(
            r"You are in the middle of|MERGE_HEAD exists|rebase-merge|rebase-apply"
            r"|CHERRY_PICK_HEAD exists|is not possible because you have unmerged files"
            r"|You have not concluded your merge",
            re.I,
        ),
    ),
    (
        "branch_checked_out",
        re.compile(
            r"already checked out at|is already used by worktree|cannot delete branch", re.I
        ),
    ),
    ("branch_exists", re.compile(r"a branch named '.*' already exists", re.I)),
    (
        "identity_missing",
        re.compile(r"Please tell me who you are|unable to auto-detect email", re.I),
    ),
    ("hook_failed", re.compile(r"hook .*(failed|declined)|pre-commit hook|commit-msg hook", re.I)),
    ("lfs_missing", re.compile(r"git-lfs|git: 'lfs' is not a git command|filter-process", re.I)),
    ("not_a_repo", re.compile(r"not a git repository", re.I)),
    (
        "unknown_ref",
        re.compile(
            r"unknown revision|bad revision|not a valid object name|pathspec .* did not match"
            r"|couldn't find remote ref|invalid reference|not a commit",
            re.I,
        ),
    ),
    ("nothing_to_commit", re.compile(r"nothing (added )?to commit|no changes added", re.I)),
    ("patch_failed", re.compile(r"patch does not apply|corrupt patch|patch failed", re.I)),
    ("not_merged", re.compile(r"is not fully merged", re.I)),
]


def classify(text: str) -> str:
    for code, pattern in PATTERNS:
        if pattern.search(text):
            return code
    return "git_failed"


class GitxError(ApiError):
    """A git command failed. `code` is one of PATTERNS' (or `git_failed`); `output` is what git
    printed, for the details panel."""

    def __init__(self, code: str, message: str, output: str = "", status: int = 409) -> None:
        super().__init__(status, code, message)
        self.output = output


def last_line(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def from_output(args: tuple[str, ...], returncode: int, stdout: str, stderr: str) -> GitxError:
    """The error for a failed `git <args>`."""
    text = f"{stderr}\n{stdout}".strip()
    message = last_line(stderr) or last_line(stdout) or f"git {args[0] if args else ''} failed"
    return GitxError(classify(text), f"git {args[0] if args else ''}: {message}", text)
