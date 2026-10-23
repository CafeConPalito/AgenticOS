"""SKILL.md parsing, limits and the content-addressed store (phase 17, block 1; spike S5)."""

from pathlib import Path

import pytest

from agentic_os.services.datadir import disk_usage
from agentic_os.services.skills import format as fmt
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.store import SkillStore, manifest_hashes

GOOD = "---\nname: revision-codigo\ndescription: Revisa los cambios de una rama.\n---\n\n# Pasos\n"


def _skill(md: str = GOOD, **extra: bytes) -> dict[str, bytes]:
    return {"SKILL.md": md.encode("utf-8"), **extra}


def test_a_valid_skill_keeps_extra_header_fields():
    md = (
        "---\nname: revision-codigo\ndescription: Revisa cambios.\nlicense: MIT\n"
        "allowed-tools: Bash Read\nmetadata:\n  author: ana\n---\nCuerpo\n"
    )
    checked = fmt.check_files(_skill(md))
    assert checked.parsed.name == "revision-codigo"
    assert checked.parsed.meta["license"] == "MIT"
    assert checked.parsed.meta["metadata"] == {"author": "ana"}
    assert checked.parsed.body == "Cuerpo\n"
    assert checked.executables == []


def test_bom_crlf_and_an_unquoted_colon_are_tolerated():
    md = (
        "\ufeff---\r\nname: x-skill\r\n"
        "description: Runs checks: formatters and linters.\r\n---\r\nB"
    )
    parsed = fmt.check_files(_skill(md)).parsed
    assert parsed.name == "x-skill"
    assert parsed.description == "Runs checks: formatters and linters."


def test_a_multiline_description_is_one_line():
    md = "---\nname: a-b\ndescription: >\n  Primera línea\n  y segunda.\n---\n"
    assert fmt.check_files(_skill(md)).parsed.description == "Primera línea y segunda."


def test_disable_model_invocation_is_read():
    md = "---\nname: a-b\ndescription: d\ndisable-model-invocation: true\n---\n"
    assert fmt.check_files(_skill(md)).parsed.model_invocable is False
    assert fmt.check_files(_skill()).parsed.model_invocable is True


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"README.md": b"x"}, "no_skill_md"),
        (_skill("sin cabecera"), "no_header"),
        (_skill("---\ndescription: d\n---\n"), "no_name"),
        (_skill("---\nname: a\n---\n"), "no_description"),
        (_skill("---\nname: Revisión Código\ndescription: d\n---\n"), "bad_name"),
        (_skill("---\nname: a\ndescription: " + "x" * 1100 + "\n---\n"), "long_description"),
        (_skill("---\nname: a\ndescription: d\n---\n" + "palabra " * 5000), "skill_md_too_long"),
        (_skill(**{"../fuera.txt": b"x"}), "bad_path"),
        (_skill(**{"C:/Windows/x.txt": b"x"}), "bad_path"),
        (_skill(**{"scripts/con.txt": b"x"}), "bad_path"),
        (_skill(**{"a/x.txt": b"1", "A/X.txt": b"2"}), "duplicate_path"),
        (_skill(**{"big.bin": b"0" * (fmt.MAX_FILE_BYTES + 1)}), "file_too_large"),
        ({**_skill(), **{f"f{i}.md": b"x" for i in range(fmt.MAX_FILES)}}, "too_many_files"),
        (
            {**_skill(), **{f"f{i}.bin": b"0" * 900_000 for i in range(6)}},
            "skill_too_large",
        ),
        ({"SKILL.md": b"\xff\xfe\x00"}, "not_utf8"),
    ],
)
def test_bad_skills_are_refused_with_a_reason(files, code):
    with pytest.raises(SkillError) as error:
        fmt.check_files(files)
    assert error.value.code == code
    assert error.value.message  # in words, for the agent and the log


def test_paths_are_normalised_and_executables_found():
    checked = fmt.check_files(
        _skill(**{"scripts\\run.py": b"print(1)", "./docs/a.md": b"x", "bin/tool": b"#!/bin/sh"})
    )
    assert set(checked.files) == {"SKILL.md", "scripts/run.py", "docs/a.md", "bin/tool"}
    assert checked.executables == ["bin/tool", "scripts/run.py"]


def test_compose_round_trips_and_puts_name_first():
    meta = {"license": "MIT", "description": "Hace: cosas", "name": "a-b"}
    text = fmt.compose_skill_md(meta, "Cuerpo")
    assert text.startswith("---\nname: a-b\n")
    parsed = fmt.parse_skill_md(text)
    assert parsed.meta == meta
    assert parsed.body == "Cuerpo\n"


def test_the_store_shares_identical_files_and_materializes(tmp_path: Path):
    store = SkillStore(tmp_path)
    one = store.put_files({"SKILL.md": b"v1", "scripts/run.py": b"print(1)"})
    two = store.put_files({"SKILL.md": b"v2", "scripts/run.py": b"print(1)"})
    assert one["scripts/run.py"] == two["scripts/run.py"]
    assert one["scripts/run.py"]["executable"] is True
    blobs = [p for p in store.blobs.rglob("*") if p.is_file()]
    assert len(blobs) == 3
    folder = store.materialize(two, tmp_path / "out" / "s")
    assert (folder / "scripts" / "run.py").read_bytes() == b"print(1)"
    assert store.read(two, "SKILL.md") == b"v2"
    assert store.read(two, "otro.md") is None
    with pytest.raises(SkillError):
        store.read(two, "../../etc/passwd")


def test_collect_removes_only_unreferenced_blobs(tmp_path: Path):
    store = SkillStore(tmp_path)
    keep = store.put_files({"SKILL.md": b"keep"})
    drop = store.put_files({"SKILL.md": b"drop"})
    freed = store.collect(manifest_hashes([keep]))
    assert freed == 4
    assert store.has(keep["SKILL.md"]["sha256"])
    assert not store.has(drop["SKILL.md"]["sha256"])


def test_disk_usage_counts_the_skills_folder(tmp_path: Path):
    SkillStore(tmp_path).put(b"0123456789")
    usage = disk_usage(tmp_path)
    assert usage.skills == 10
    assert usage.total >= 10
