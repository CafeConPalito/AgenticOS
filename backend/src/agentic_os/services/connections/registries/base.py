"""What every public registry of MCP servers offers (phase 18, block 8; spike S4), and how an
entry becomes a connection: the list of ways to run it (a package, an image or a remote URL), the
form it needs (variables, headers, arguments) and the exact command that will run.

A source that fails never breaks the others; the HTTP client and its failure codes are the skill
registries' ones.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from agentic_os.services.connections import format as fmt
from agentic_os.services.connections import secrets
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.skills.registries.base import Http, SourceError

__all__ = ["Card", "Detail", "Field", "Http", "Option", "Source", "SourceError", "build_draft"]

REQUIRES = {"npm": ("npx",), "pypi": ("uvx",), "oci": ("docker",), "remote": ()}
_TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.-]*)\}")


@dataclass
class Card:
    """A server as a registry lists it."""

    source: str  # the registry module that can describe it
    ref: str  # its id in that registry
    name: str
    description: str = ""
    author: str = ""
    uses: int | None = None  # installs or downloads, when the registry says
    stars: int | None = None
    updated_at: str | None = None
    category: str = ""
    url: str = ""
    transport: str = ""  # «stdio», «http» or «both»
    verified: bool = False  # published by its own author / verified by the registry
    version: str = ""


@dataclass
class Field:
    """A value the person has to give (or may give) to run the server."""

    key: str  # the form field; for a secret, also its key in the credential store
    label: str
    where: str  # «env», «header», «arg» or «url»
    name: str = ""  # the variable or header it goes to; for «arg», the option's flag
    secret: bool = False
    required: bool = False
    default: str = ""
    description: str = ""
    template: str = "{value}"  # how the value is written (a header may say «Bearer {value}»)


@dataclass
class Option:
    """One way to run a server."""

    kind: str  # «npm», «pypi», «oci» or «remote»
    label: str
    package: str = ""  # the package or image name
    version: str = ""  # as the registry says; «latest» is resolved when it is installed
    transport: str = "stdio"  # of the connection: «stdio», «http» or «sse»
    url: str = ""  # a remote's address (may hold {variables})
    fields: list[Field] = field(default_factory=list)
    args: list[dict] = field(default_factory=list)  # package arguments, in order
    runtime_args: list[str] = field(default_factory=list)
    command: str = ""  # kind «command»: a command the registry gives as it is (a README)
    command_args: list[str] = field(default_factory=list)
    oauth: bool = False

    @property
    def requires(self) -> tuple[str, ...]:
        if self.kind == "command":
            return (Path(self.command).stem,) if self.command else ()
        return REQUIRES.get(self.kind, ())


@dataclass
class Detail:
    card: Card
    options: list[Option] = field(default_factory=list)
    license: str = ""
    repo_url: str = ""
    website: str = ""
    readme: str = ""
    tools: list[dict] = field(default_factory=list)  # the ones the registry declares
    security: dict = field(default_factory=dict)
    note: str = ""  # something to tell the person (hosted by a third party…)
    manifest: dict = field(
        default_factory=dict
    )  # what the registry said, for the diff of an update


class Source(ABC):
    id: str
    title: str
    default_enabled: bool = True
    has_popular: bool = False

    def __init__(self, http: Http) -> None:
        self.http = http

    def popular(self, page: int = 1) -> list[Card]:
        return []

    @abstractmethod
    def search(self, query: str, page: int = 1) -> list[Card]: ...

    @abstractmethod
    def detail(self, ref: str) -> Detail: ...


# -- an option becomes a connection -------------------------------------------------------------
def _value(item: Field, values: dict[str, str]) -> str:
    return (values.get(item.key) or item.default or "").strip()


def build_draft(
    option: Option, name: str, values: dict[str, str], resolved_version: str = ""
) -> tuple[fmt.Draft, str]:
    """The connection `option` makes with the form's `values`. Returns it and the exact version
    it is pinned to (a package that says «latest» gets the real one: `resolved_version`)."""
    version = option.version if option.version and option.version != "latest" else resolved_version
    draft = fmt.Draft(
        name=name, transport=option.transport, auth="oauth" if option.oauth else "none"
    )
    url = option.url
    secret_values: dict[str, str] = {}

    def shown(item: Field) -> str | None:
        value = _value(item, values)
        if not value:
            if item.required and not item.secret:
                raise ConnectionError_("field_required", f"Falta «{item.label}».", field=item.key)
            return f"${{secret:{item.key}}}" if item.secret else None
        if item.secret:
            secrets.check_key(item.key)
            secret_values[item.key] = value
            return f"${{secret:{item.key}}}"
        return value

    positional: list[str] = []
    named: dict[str, list[str]] = {}
    for item in option.fields:
        text = shown(item)
        if text is None:
            continue
        written = item.template.replace("{value}", text)
        if item.where == "env":
            draft.env[item.name or item.key] = written
        elif item.where == "header":
            draft.headers[item.name or item.key] = written
        elif item.where == "url":
            url = url.replace("{" + (item.name or item.key) + "}", written)
        elif item.where == "arg":
            if item.name:
                named.setdefault(item.name, []).append(written)
            else:
                positional.append(written)
    draft.secrets = secret_values
    flags = []
    for argument in option.args:
        if argument.get("name") and argument["name"] in named:
            for value in named.pop(argument["name"]):
                flags += (
                    [argument["name"], value] if not argument.get("flag") else [argument["name"]]
                )
        elif argument.get("value"):  # a fixed argument of the package
            flags += (
                [argument["name"], argument["value"]]
                if argument.get("name")
                else [argument["value"]]
            )
    flags += [a for pair in named.items() for a in (pair[0], *pair[1])] + positional

    if option.kind == "npm":
        pin = f"{option.package}@{version}" if version else option.package
        draft.command, draft.args = "npx", ["-y", pin, *flags]
    elif option.kind == "pypi":
        pin = f"{option.package}=={version}" if version else option.package
        draft.command, draft.args = "uvx", [pin, *flags]
    elif option.kind == "command":
        draft.command, draft.args = option.command, [*option.command_args, *flags]
    elif option.kind == "oci":
        image = (
            f"{option.package}:{version}"
            if version and ":" not in option.package
            else option.package
        )
        env_flags = [a for var in sorted(draft.env) for a in ("-e", var)]
        draft.command = "docker"
        draft.args = ["run", "-i", "--rm", *env_flags, *option.runtime_args, image, *flags]
    else:
        draft.url = url
        left = _TOKEN.findall(url)
        if left:
            raise ConnectionError_(
                "field_required",
                f"Falta «{left[0]}» para la dirección del servidor.",
                field=left[0],
            )
    return draft, version
