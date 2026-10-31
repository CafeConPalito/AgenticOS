"""Appearance (phases 20 and 22): the chosen theme and the person's own themes.

The frontend owns the list of tokens a theme can set; here only their shape is checked
(token names, hex colors, ranges), so a new token needs no backend change.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# The themes that ship with the app; a custom theme cannot take one of these ids.
BUILTIN_THEMES = ("navy", "light", "contrast", "warm", "graphite")
MAX_CUSTOM_THEMES = 50
MAX_COLORS = 160

ThemeId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")]
TokenName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")]
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")]
# A font installed on the system (ADR 0028): safe to write quoted in a CSS font-family.
FontFamily = Annotated[str, StringConstraints(pattern=r"^[\p{L}\p{N}][\p{L}\p{N} ._'&()+-]{0,79}$")]


class ThemeDefinition(BaseModel):
    """`agentic-os.theme` v2 (ADR 0028), which reads v1 too: what a custom theme changes over
    the theme it extends, or over the base token set when it extends none (made from scratch)."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["agentic-os.theme"] = "agentic-os.theme"
    version: Literal[1, 2] = 2
    id: ThemeId
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    base: Literal["light", "dark"]
    extends: ThemeId | None = None
    colors: dict[TokenName, HexColor] = Field(default_factory=dict, max_length=MAX_COLORS)
    font: Literal["ubuntu", "inter", "atkinson", "system"] | None = None
    font_family: FontFamily | None = None  # over `font` when set
    scale: float | None = Field(default=None, ge=0.8, le=1.5)
    density: Literal["compact", "normal", "comfortable"] | None = None
    radius: int | None = Field(default=None, ge=0, le=20)


class LegacyFollow(BaseModel):
    """The two themes of «Seguir al sistema» (phase 20), removed in phase 22."""

    light_theme: ThemeId
    dark_theme: ThemeId


class Appearance(BaseModel):
    """The whole appearance document: read and written in one piece."""

    model_config = ConfigDict(extra="forbid")

    theme: ThemeId = "navy"
    custom: list[ThemeDefinition] = Field(default_factory=list, max_length=MAX_CUSTOM_THEMES)

    @model_validator(mode="after")
    def _references(self) -> "Appearance":
        ids = [theme.id for theme in self.custom]
        if len(set(ids)) != len(ids):
            raise ValueError("custom theme ids must be unique")
        if clash := sorted(set(ids) & set(BUILTIN_THEMES)):
            raise ValueError(f"a custom theme cannot use a built-in id: {', '.join(clash)}")
        known = {*BUILTIN_THEMES, *ids}
        if self.theme not in known:
            raise ValueError("theme refers to an unknown theme")
        for theme in self.custom:
            if theme.extends is not None and (
                theme.extends not in known or theme.extends == theme.id
            ):
                raise ValueError(f"theme {theme.id} extends an unknown theme")
        return self


class StoredAppearance(Appearance):
    """What `GET` answers: the document, plus the themes of «Seguir al sistema» when a phase 20
    document still had it on, for the interface to keep the theme on screen (ADR 0028)."""

    legacy_follow: LegacyFollow | None = None

    @classmethod
    def from_stored(cls, data: Any) -> "StoredAppearance":
        if isinstance(data, dict) and "mode" in data:
            data = dict(data)
            mode = data.pop("mode")
            follow = {key: data.pop(key, None) for key in ("light_theme", "dark_theme")}
            custom = [t for t in data.get("custom", []) if isinstance(t, dict)]
            known = {*BUILTIN_THEMES, *(t.get("id") for t in custom)}
            if mode == "system" and all(value in known for value in follow.values()):
                data["legacy_follow"] = follow
        return cls.model_validate(data)
