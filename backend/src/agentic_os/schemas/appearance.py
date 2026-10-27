"""Appearance (phase 20): the chosen theme and the person's own themes.

The frontend owns the list of tokens a theme can set; here only their shape is checked
(token names, hex colors, ranges), so a new token needs no backend change.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# The themes that ship with the app; a custom theme cannot take one of these ids.
BUILTIN_THEMES = ("navy", "light", "contrast", "warm", "graphite")
MAX_CUSTOM_THEMES = 50
MAX_COLORS = 160

ThemeId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")]
TokenName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")]
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")]


class ThemeDefinition(BaseModel):
    """`agentic-os.theme` v1: what a custom theme changes over the theme it extends."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["agentic-os.theme"] = "agentic-os.theme"
    version: Literal[1] = 1
    id: ThemeId
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    base: Literal["light", "dark"]
    extends: ThemeId
    colors: dict[TokenName, HexColor] = Field(default_factory=dict, max_length=MAX_COLORS)
    font: Literal["ubuntu", "inter", "atkinson", "system"] | None = None
    scale: float | None = Field(default=None, ge=0.8, le=1.5)
    density: Literal["compact", "normal", "comfortable"] | None = None
    radius: int | None = Field(default=None, ge=0, le=20)


class Appearance(BaseModel):
    """The whole appearance document: read and written in one piece."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["fixed", "system"] = "fixed"
    theme: ThemeId = "navy"  # the theme when `mode` is fixed
    light_theme: ThemeId = "light"  # when `mode` is system and Windows is in light mode
    dark_theme: ThemeId = "navy"  # … and in dark mode
    custom: list[ThemeDefinition] = Field(default_factory=list, max_length=MAX_CUSTOM_THEMES)

    @model_validator(mode="after")
    def _references(self) -> "Appearance":
        ids = [theme.id for theme in self.custom]
        if len(set(ids)) != len(ids):
            raise ValueError("custom theme ids must be unique")
        if clash := sorted(set(ids) & set(BUILTIN_THEMES)):
            raise ValueError(f"a custom theme cannot use a built-in id: {', '.join(clash)}")
        known = {*BUILTIN_THEMES, *ids}
        for field in ("theme", "light_theme", "dark_theme"):
            if getattr(self, field) not in known:
                raise ValueError(f"{field} refers to an unknown theme")
        for theme in self.custom:
            if theme.extends not in known or theme.extends == theme.id:
                raise ValueError(f"theme {theme.id} extends an unknown theme")
        return self
