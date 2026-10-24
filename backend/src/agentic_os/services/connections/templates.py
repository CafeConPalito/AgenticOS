"""Ready-made connections for the servers people use most (phase 18).

A template only fills in the form: nothing is installed or run until the person saves the
connection and tests it. Packages are pinned to the version they were checked with (spec G: the
code does not change without the person knowing).
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_os.services.connections import format as fmt
from agentic_os.services.connections import secrets
from agentic_os.services.connections.errors import ConnectionError_


@dataclass(frozen=True)
class Field:
    key: str  # the form field and, for a secret, the secret's key
    label: str
    where: str  # «env», «header», «arg» or «url»
    secret: bool = False
    required: bool = True
    name: str = ""  # the environment variable or header it goes to
    placeholder: str = ""  # the text with `{value}` where the value goes
    help: str = ""
    help_url: str = ""
    kind: str = "text"  # «text», «path» or «secret» (what the form shows)


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    description: str
    transport: str
    command: str = ""
    args: tuple[str, ...] = ()
    url: str = ""
    auth: str = "none"
    icon: str = ""
    requires: tuple[str, ...] = ()  # programs that have to be installed
    fields: tuple[Field, ...] = ()
    official: bool = False
    docs_url: str = ""


TEMPLATES: tuple[Template, ...] = (
    Template(
        id="github",
        name="GitHub",
        description="Repositorios, incidencias y pull requests de GitHub (servidor oficial).",
        transport="http",
        url="https://api.githubcopilot.com/mcp/",
        icon="github",
        official=True,
        docs_url="https://github.com/github/github-mcp-server",
        fields=(
            Field(
                key="GITHUB_TOKEN",
                label="Token personal de GitHub",
                where="header",
                name="Authorization",
                placeholder="Bearer {value}",
                secret=True,
                kind="secret",
                help="Crea un token con los permisos que quieras darle al agente.",
                help_url="https://github.com/settings/personal-access-tokens/new",
            ),
        ),
    ),
    Template(
        id="playwright",
        name="Playwright (navegador)",
        description="Un navegador que el agente controla: abrir páginas, hacer clic y leerlas.",
        transport="stdio",
        command="npx",
        args=("-y", "@playwright/mcp@0.0.83"),
        icon="globe",
        requires=("npx",),
        official=True,
        docs_url="https://github.com/microsoft/playwright-mcp",
    ),
    Template(
        id="postgres",
        name="PostgreSQL",
        description="Consultar una base de datos PostgreSQL (solo lectura).",
        transport="stdio",
        command="npx",
        args=("-y", "@modelcontextprotocol/server-postgres@0.6.2", "${secret:DATABASE_URL}"),
        icon="database",
        requires=("npx",),
        fields=(
            Field(
                key="DATABASE_URL",
                label="Cadena de conexión",
                where="arg",
                secret=True,
                kind="secret",
                help="postgresql://usuario:contraseña@servidor:5432/base",
            ),
        ),
    ),
    Template(
        id="sqlite",
        name="SQLite",
        description="Consultar y modificar un fichero de base de datos SQLite.",
        transport="stdio",
        command="uvx",
        args=("mcp-server-sqlite==2025.4.25", "--db-path", "{db_path}"),
        icon="database",
        requires=("uvx",),
        fields=(
            Field(
                key="db_path",
                label="Fichero de la base de datos",
                where="arg",
                kind="path",
                help="La ruta del fichero .db o .sqlite.",
            ),
        ),
    ),
    Template(
        id="filesystem",
        name="Ficheros",
        description="Leer y escribir ficheros de una carpeta concreta.",
        transport="stdio",
        command="npx",
        args=("-y", "@modelcontextprotocol/server-filesystem@2.0.0", "{folder}"),
        icon="folder",
        requires=("npx",),
        fields=(
            Field(
                key="folder",
                label="Carpeta permitida",
                where="arg",
                kind="path",
                help="El servidor no puede salir de esta carpeta.",
            ),
        ),
    ),
    Template(
        id="fetch",
        name="Fetch (páginas web)",
        description="Descargar una página web y devolverla como texto.",
        transport="stdio",
        command="uvx",
        args=("mcp-server-fetch==2026.10.19",),
        icon="globe",
        requires=("uvx",),
    ),
    Template(
        id="context7",
        name="Context7 (documentación)",
        description="Documentación actualizada de librerías y frameworks.",
        transport="stdio",
        command="npx",
        args=("-y", "@upstash/context7-mcp@4.4.4"),
        icon="book",
        requires=("npx",),
        docs_url="https://github.com/upstash/context7",
    ),
    Template(
        id="linear",
        name="Linear",
        description="Incidencias y proyectos de Linear. Se conecta con tu cuenta (OAuth).",
        transport="http",
        url="https://mcp.linear.app/mcp",
        auth="oauth",
        icon="linear",
        official=True,
        docs_url="https://linear.app/docs/mcp",
    ),
    Template(
        id="notion",
        name="Notion",
        description="Páginas y bases de datos de Notion. Se conecta con tu cuenta (OAuth).",
        transport="http",
        url="https://mcp.notion.com/mcp",
        auth="oauth",
        icon="notion",
        official=True,
        docs_url="https://developers.notion.com/docs/mcp",
    ),
)
BY_ID = {t.id: t for t in TEMPLATES}


def get(template_id: str) -> Template:
    template = BY_ID.get(template_id)
    if template is None:
        raise ConnectionError_(
            "template_unknown", f"No hay ninguna plantilla «{template_id}».", template=template_id
        )
    return template


def build(template_id: str, values: dict[str, str] | None = None, name: str = "") -> fmt.Draft:
    """The draft a template makes with the values of its form. Secret values go to
    `Draft.secrets`; the rest into the command, the variables or the headers."""
    template = get(template_id)
    values = {k: (v or "").strip() for k, v in (values or {}).items()}
    draft = fmt.Draft(
        name=name or template.id,
        transport=template.transport,
        command=template.command,
        args=list(template.args),
        url=template.url,
        description=template.description,
        icon=template.icon,
        auth=template.auth,
    )
    for item in template.fields:
        value = values.get(item.key, "")
        if not value and item.required and not item.secret:
            raise ConnectionError_(
                "field_required",
                f"Falta «{item.label}».",
                field=item.key,
            )
        shown = f"${{secret:{item.key}}}" if item.secret else value
        text = item.placeholder.replace("{value}", shown) if item.placeholder else shown
        if item.secret and value:
            secrets.check_key(item.key)
            draft.secrets[item.key] = value
        if item.where == "env":
            draft.env[item.name or item.key] = text
        elif item.where == "header":
            draft.headers[item.name or item.key] = text
        elif item.where == "url":
            draft.url = draft.url.replace("{" + item.key + "}", text)
        elif item.where == "arg":
            draft.args = [
                text if a in (f"{{{item.key}}}", f"${{secret:{item.key}}}") else a
                for a in draft.args
            ]
    return draft


def card(template: Template) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "transport": template.transport,
        "auth": template.auth,
        "icon": template.icon,
        "requires": list(template.requires),
        "official": template.official,
        "docs_url": template.docs_url,
        "command": " ".join([template.command, *template.args]).strip(),
        "url": template.url,
        "fields": [
            {
                "key": f.key,
                "label": f.label,
                "secret": f.secret,
                "required": f.required,
                "kind": f.kind,
                "help": f.help,
                "help_url": f.help_url,
            }
            for f in template.fields
        ],
    }
