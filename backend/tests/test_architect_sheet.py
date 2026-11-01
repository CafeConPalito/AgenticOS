"""The Architect's sheet and its rules (phase 19, block 2; CA3, CA16): only what exists in the
installation gets in, locked fields stay, and a pipeline passes the editor's graph rules."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.models import (
    Agent,
    AgentStatus,
    CliAccount,
    DocStatus,
    KnowledgeDoc,
    KnowledgeScope,
    McpConnection,
    Project,
    Skill,
    SkillReview,
    SourceKind,
    Team,
)
from agentic_os.services.architect import sheet as S
from agentic_os.services.clis import CliInfo, ModelOption


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    upgrade_to_head(engine)
    factory: sessionmaker[Session] = make_sessionmaker(engine)
    with factory() as session:
        yield session
    engine.dispose()


def _cli(cli: str, *models: str) -> CliInfo:
    return CliInfo(id=cli, name=cli, installed=True, models=[ModelOption(id=m) for m in models])


CLIS = [_cli("claude", "sonnet", "opus", "haiku"), _cli("agy", "gemini-3.8-flash-high")]


@pytest.fixture
def world(db: Session) -> dict:
    def add(row):
        db.add(row)
        db.flush()
        return row

    w = {
        "personal": add(CliAccount(cli="claude", label="personal")),
        "trabajo": add(CliAccount(cli="agy", label="trabajo")),
        "team": add(Team(workspace_id=DEFAULT_WORKSPACE, name="Marketing")),
        "dev": add(Agent(workspace_id=DEFAULT_WORKSPACE, name="Dev", role="Desarrollador")),
        "qa": add(Agent(workspace_id=DEFAULT_WORKSPACE, name="QA", role="QA", cli="agy")),
        "draft": add(
            Agent(
                workspace_id=DEFAULT_WORKSPACE,
                name="Borrador",
                role="Otro",
                status=AgentStatus.DRAFT,
            )
        ),
        "seo": add(Skill(workspace_id=DEFAULT_WORKSPACE, name="seo-basico", description="SEO")),
        "proposed": add(
            Skill(
                workspace_id=DEFAULT_WORKSPACE,
                name="sin-aprobar",
                description="x",
                review=SkillReview.PROPOSED,
            )
        ),
        "doc": add(
            KnowledgeDoc(
                workspace_id=DEFAULT_WORKSPACE,
                title="Guía de marca",
                source_kind=SourceKind.FILE,
                path="C:/docs/marca.pdf",
                status=DocStatus.READY,
            )
        ),
        "github": add(
            McpConnection(
                workspace_id=DEFAULT_WORKSPACE,
                name="github",
                tools=[{"name": "get_issue"}, {"name": "create_pull_request"}],
            )
        ),
        "shop": add(
            Project(workspace_id=DEFAULT_WORKSPACE, name="Tienda", path="C:/p", path_key="c:/p")
        ),
    }
    db.add(
        Skill(
            workspace_id=DEFAULT_WORKSPACE,
            name="de-otro-agente",
            description="x",
            scope=KnowledgeScope.AGENT,
            agent_id=w["dev"].id,
        )
    )
    db.flush()
    w["catalog"] = S.Catalog.load(db, CLIS, DEFAULT_WORKSPACE)
    return w


def patch(world: dict, values: dict, sheet: dict | None = None, **kw) -> S.PatchResult:
    return S.apply_patch(world["catalog"], sheet or {}, values, **kw)


# ------------------------------------------------------------------------------- one agent
def test_a_valid_patch_is_stored_with_ids_for_references(world):
    result = patch(
        world,
        {
            "name": "Redactor",
            "role": "Redactor del blog",
            "cli": "claude",
            "account": "personal",
            "model": "sonnet",
            "team": "Marketing",
            "skills": [{"name": "seo-basico", "mode": "always"}],
            "knowledge": ["Guía de marca"],
            "connections": [{"name": "github"}],
            "allowed_tools": ["read", "edit", "read"],
        },
    )
    assert result.refused == {}
    agent = result.sheet["agents"]["main"]
    assert agent["account"] == world["personal"].id
    assert agent["team"] == world["team"].id
    assert agent["skills"] == [
        {"skill_id": world["seo"].id, "name": "seo-basico", "mode": "always"}
    ]
    assert agent["knowledge"] == [{"doc_id": world["doc"].id, "title": "Guía de marca"}]
    assert agent["connections"][0]["connection_id"] == world["github"].id
    assert agent["allowed_tools"] == ["read", "edit"]


@pytest.mark.parametrize(
    ("values", "path", "fragment"),
    [
        ({"cli": "codex"}, "main.cli", "Instalados: agy, claude"),
        ({"cli": "claude", "model": "gpt-5"}, "main.model", "Disponibles: sonnet, opus, haiku"),
        ({"cli": "claude", "account": "trabajo"}, "main.account", "no es una cuenta de claude"),
        ({"team": "Ventas"}, "main.team", "no existe"),
        ({"skills": ["inventada"]}, "main.skills", "draft_skill"),
        ({"skills": ["sin-aprobar"]}, "main.skills", "no existen"),
        ({"skills": ["de-otro-agente"]}, "main.skills", "no existen"),
        ({"knowledge": ["Manual secreto"]}, "main.knowledge", "no existen"),
        ({"connections": ["notion"]}, "main.connections", "suggest_connection"),
        (
            {"connections": [{"name": "github", "tools": ["delete_repo"]}]},
            "main.connections",
            "se configuran en la conexión",
        ),
        ({"permission_mode": "yolo"}, "main.permission_mode", "autonomous"),
        ({"allowed_tools": ["shell"]}, "main.allowed_tools", "desconocidas"),
        ({"max_concurrency": 9}, "main.max_concurrency", "de 1 a 5"),
        ({"color": "rojo"}, "main.color", "#RRGGBB"),
        ({"name": ""}, "main.name", "vacío"),
        ({"salary": 3}, "main.salary", "desconocido"),
    ],
)
def test_what_does_not_exist_or_is_wrong_is_refused_with_a_reason(world, values, path, fragment):
    result = patch(world, values)
    assert fragment in result.refused[path]
    assert path.split(".")[1] not in result.sheet["agents"]["main"]


def test_one_wrong_field_does_not_stop_the_others(world):
    result = patch(world, {"name": "Redactor", "model": "gpt-5", "cli": "claude"})
    assert result.sheet["agents"]["main"]["name"] == "Redactor"
    assert set(result.refused) == {"main.model"}


def test_a_locked_field_is_kept(world):
    sheet = patch(world, {"color": "#FF0000"}).sheet
    result = patch(world, {"color": "#00FF00", "role": "QA"}, sheet, locked={"main.color"})
    assert "request_unlock" in result.refused["main.color"]
    assert result.sheet["agents"]["main"]["color"] == "#FF0000"
    assert result.sheet["agents"]["main"]["role"] == "QA"


def test_changing_the_cli_drops_the_account_and_model_of_the_old_one(world):
    sheet = patch(world, {"cli": "claude", "account": "personal", "model": "opus"}).sheet
    result = patch(world, {"cli": "agy"}, sheet)
    agent = result.sheet["agents"]["main"]
    assert agent["cli"] == "agy"
    assert "account" not in agent and "model" not in agent


def test_a_cli_that_could_not_list_its_models_accepts_any(world, db):
    clis = [CliInfo(id="agy", name="agy", installed=True, models=[], models_error="no session")]
    catalog = S.Catalog.load(db, clis, DEFAULT_WORKSPACE)
    result = S.apply_patch(catalog, {}, {"cli": "agy", "model": "gemini-9"})
    assert result.refused == {}


def test_new_skills_follow_the_library_rules(world):
    good = {"name": "tono-blog", "description": "Tono del blog", "body": "# Tono\n..."}
    assert patch(world, {"new_skills": [good]}).refused == {}
    for bad, fragment in [
        ({**good, "name": "Tono Blog"}, "minúsculas"),
        ({**good, "name": "seo-basico"}, "ya hay una skill"),
        ({**good, "body": ""}, "vacío"),
    ]:
        assert fragment in patch(world, {"new_skills": [bad]}).refused["main.new_skills"]
    assert "como mucho" in patch(world, {"new_skills": [good] * 6}).refused["main.new_skills"]


def test_issues_say_what_is_missing_and_progress_counts_the_sheet(world):
    sheet = patch(world, {"name": "Redactor", "cli": "claude"}).sheet
    agent = sheet["agents"]["main"]
    issues = S.agent_issues(world["catalog"], agent)
    assert {i.field for i in issues} == {"main.role", "main.instructions"}
    assert not S.ready(world["catalog"], sheet)
    assert S.progress(agent) == 18  # 2 of 11
    full = patch(world, {"role": "Redactor", "instructions": "Escribe."}, sheet).sheet
    assert S.ready(world["catalog"], full)


def test_a_repeated_role_is_a_warning_that_does_not_block(world):
    sheet = patch(world, {"name": "Dev 2", "role": "desarrollador", "cli": "claude",
                          "instructions": "x"}).sheet  # fmt: skip
    issues = S.sheet_issues(world["catalog"], sheet)
    assert [(i.code, i.level) for i in issues] == [("duplicate_role", "warning")]
    assert S.ready(world["catalog"], sheet)
    sheet["agents"]["main"]["id"] = world["dev"].id  # improving Dev itself
    assert S.sheet_issues(world["catalog"], sheet) == []


def test_references_deleted_after_they_were_chosen_become_issues(world, db):
    sheet = patch(world, {"name": "R", "role": "R", "cli": "claude", "instructions": "x",
                          "skills": ["seo-basico"]}).sheet  # fmt: skip
    db.delete(world["seo"])
    db.flush()
    catalog = S.Catalog.load(db, CLIS, DEFAULT_WORKSPACE)
    issues = S.sheet_issues(catalog, sheet)
    assert [(i.field, i.code) for i in issues] == [("main.skills", "gone")]


# ------------------------------------------------------------------------ team and pipeline
def _team_sheet(world) -> dict:
    sheet = patch(world, {"name": "Redactor", "role": "Redactor", "cli": "claude",
                          "instructions": "x"}, ref="redactor").sheet  # fmt: skip
    sheet = patch(world, {"name": "Revisor", "role": "Revisor", "cli": "claude",
                          "instructions": "x"}, sheet, ref="revisor").sheet  # fmt: skip
    return S.use_existing_agent(world["catalog"], sheet, "QA").sheet


def test_a_team_is_new_or_existing(world):
    catalog = world["catalog"]
    assert (
        S.set_team(catalog, {}, {"team": "Marketing"}).sheet["team"]["team_id"] == world["team"].id
    )
    assert "ya hay un equipo" in S.set_team(catalog, {}, {"name": "marketing"}).refused["team"]
    assert S.set_team(catalog, {}, {"name": "Contenidos"}).sheet["team"]["name"] == "Contenidos"
    assert "no existe" in S.set_team(catalog, {}, {"team": "Ventas"}).refused["team"]


def test_only_active_agents_can_be_reused(world):
    catalog = world["catalog"]
    assert S.use_existing_agent(catalog, {}, "Dev").sheet["existing_agents"] == [world["dev"].id]
    assert S.use_existing_agent(catalog, {}, "Borrador").refused
    assert S.use_existing_agent(catalog, {}, "Nadie").refused


def test_a_valid_pipeline_mixes_new_and_existing_agents(world):
    sheet = _team_sheet(world)
    result = S.set_pipeline(
        world["catalog"],
        sheet,
        {
            "project": "Tienda",
            "stages": [
                {"name": "Redacción", "agent": "redactor"},
                {"name": "Revisión", "agent": "revisor", "reject_to": 0},
                {"name": "QA", "agent": "QA", "requires_review": True},
            ],
        },
    )
    assert result.refused == {}
    stages = result.sheet["pipeline"]["stages"]
    assert [s["agent"] for s in stages] == ["ref:redactor", "ref:revisor", world["qa"].id]
    assert S.pipeline_issues(result.sheet) == []
    assert S.ready(world["catalog"], result.sheet)


def test_a_stage_with_an_unknown_agent_or_project_is_refused(world):
    sheet = _team_sheet(world)
    bad = {"project": "Tienda", "stages": [{"name": "X", "agent": "fantasma"}]}
    assert (
        "no existe ni está en el equipo"
        in S.set_pipeline(world["catalog"], sheet, bad).refused["pipeline"]
    )
    bad = {"project": "Blog", "stages": [{"name": "X", "agent": "redactor"}]}
    assert "proyecto" in S.set_pipeline(world["catalog"], sheet, bad).refused["pipeline"]
    draft = {"project": "Tienda", "stages": [{"name": "X", "agent": "Borrador"}]}
    assert S.set_pipeline(world["catalog"], sheet, draft).refused


@pytest.mark.parametrize(
    ("links", "stages", "code"),
    [
        # a rejection written as a link: a cycle
        ([{"source": 0, "target": 1}, {"source": 1, "target": 0}], None, "cycle"),
        # an unreachable stage: two starts
        ([{"source": 0, "target": 1}], None, "many_starts"),
        # rejection to a later stage
        (
            None,
            [{"name": "A", "agent": "redactor", "reject_to": 1}, {"name": "B", "agent": "revisor"}],
            "reject_not_backwards",
        ),
    ],
)
def test_the_graph_rules_of_the_editor_apply(world, links, stages, code):
    sheet = _team_sheet(world)
    stages = stages or [
        {"name": "A", "agent": "redactor"},
        {"name": "B", "agent": "revisor"},
        {"name": "C", "agent": "QA"},
    ]
    result = S.set_pipeline(
        world["catalog"], sheet, {"project": "Tienda", "stages": stages, "links": links}
    )
    assert result.refused == {}  # stored: the problems are reported, all at once
    codes = [i.code for i in S.pipeline_issues(result.sheet)]
    assert code in codes
    assert all(i.message for i in S.pipeline_issues(result.sheet))
    assert not S.ready(world["catalog"], result.sheet)


def test_a_link_out_of_range_is_an_issue_not_a_crash(world):
    sheet = _team_sheet(world)
    result = S.set_pipeline(
        world["catalog"],
        sheet,
        {
            "project": "Tienda",
            "stages": [{"name": "A", "agent": "redactor"}],
            "links": [{"source": 0, "target": 5}],
        },
    )
    assert [i.code for i in S.pipeline_issues(result.sheet)] == ["invalid_link"]


def test_a_stage_whose_new_agent_was_removed_is_an_issue(world):
    sheet = _team_sheet(world)
    sheet = S.set_pipeline(
        world["catalog"],
        sheet,
        {"project": "Tienda", "stages": [{"name": "A", "agent": "redactor"}]},
    ).sheet
    del sheet["agents"]["redactor"]
    assert ("pipeline.stages.0", "gone") in {
        (i.field, i.code) for i in S.sheet_issues(world["catalog"], sheet)
    }


def test_the_pipeline_becomes_the_editor_payload_with_the_real_ids(world):
    sheet = _team_sheet(world)
    sheet = S.set_pipeline(
        world["catalog"],
        sheet,
        {
            "project": "Tienda",
            "stages": [{"name": "A", "agent": "redactor"}, {"name": "B", "agent": "QA"}],
        },
    ).sheet
    payload = S.pipeline_write(sheet, {"redactor": "agent-123"})
    assert [s.agent_id for s in payload.stages] == ["agent-123", world["qa"].id]
    assert payload.links is None


def test_a_stage_exit_goes_into_the_payload_and_counts_as_a_change(world):
    """Phase 24: the Architect keeps «Terminar aquí» exits, and a changed one shows in the diff."""
    sheet = _team_sheet(world)
    stages = [
        {"name": "A", "agent": "redactor", "exit_condition": "  Solo pide un borrador  "},
        {"name": "B", "agent": "QA"},
    ]
    sheet = S.set_pipeline(world["catalog"], sheet, {"project": "Tienda", "stages": stages}).sheet
    assert sheet["pipeline"]["stages"][0]["exit_condition"] == "Solo pide un borrador"
    assert sheet["pipeline"]["stages"][1]["exit_condition"] is None
    payload = S.pipeline_write(sheet, {"redactor": "agent-123"})
    assert [s.exit_condition for s in payload.stages] == ["Solo pide un borrador", None]

    before = {"stages": [dict(s, id=f"s{i}") for i, s in enumerate(sheet["pipeline"]["stages"])]}
    after = {"stages": [dict(s) for s in before["stages"]]}
    after["stages"][0]["exit_condition"] = None
    assert S.pipeline_diff(before, after)["changed"] == ["A"]
    assert not S.same_pipeline(before, after)


def test_an_empty_exit_from_the_architect_means_no_exit(world):
    """Code review (phase 24): exit_condition "" is no exit, not an exit without condition."""
    sheet = S.set_pipeline(
        world["catalog"],
        _team_sheet(world),
        {"project": "Tienda", "stages": [{"name": "A", "agent": "QA", "exit_condition": "  "}]},
    ).sheet
    assert sheet["pipeline"]["stages"][0]["exit_condition"] is None
