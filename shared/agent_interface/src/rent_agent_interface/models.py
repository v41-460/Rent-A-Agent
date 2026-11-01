"""The shared agent interface: what every agent must provide to appear in the marketplace.

Version 1. Changes to this file need Vai's approval (see AGENTS.md).

Every agent folder contains a ``manifest.json`` matching :class:`Manifest`, and serves:

- ``GET  /manifest`` -> :class:`Manifest`
- ``GET  /health``   -> :class:`Health`
- ``POST /run``      -> body :class:`RunRequest`, response :class:`RunResponse`
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

INTERFACE_VERSION = "1"

SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,39}$"

Owner = Literal["claude", "codex", "grok", "hermes"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Manifest -------------------------------------------------------------------------


class Pricing(_Strict):
    """What renting the agent costs. Payments are mocked for now; amounts are still real numbers."""

    model: Literal["free", "monthly", "one_time"]
    amount_cents: int = Field(ge=0, description="0 when model is 'free'.")
    currency: Literal["USD"] = "USD"

    @model_validator(mode="after")
    def _free_is_zero(self) -> Pricing:
        if self.model == "free" and self.amount_cents != 0:
            raise ValueError("free agents must have amount_cents = 0")
        if self.model != "free" and self.amount_cents == 0:
            raise ValueError("paid agents must have amount_cents > 0")
        return self


class Manifest(_Strict):
    interface_version: Literal["1"] = INTERFACE_VERSION
    slug: Annotated[str, Field(pattern=SLUG_PATTERN)]
    name: Annotated[str, Field(min_length=2, max_length=40)]
    description: Annotated[
        str, Field(min_length=10, max_length=140, description="One plain sentence, no jargon.")
    ]
    long_description: Annotated[str, Field(max_length=2000)] = ""
    icon: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description="An emoji, or a path to an .svg/.png inside the agent folder.",
        ),
    ]
    owner: Owner
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")] = "0.1.0"
    pricing: Pricing
    status: Literal["available", "coming_soon"] = "coming_soon"
    location: Literal["local", "remote"] = "local"
    base_url: HttpUrl | None = Field(
        default=None, description="Required when location is 'remote', e.g. Hermes on AWS."
    )
    has_custom_page: bool = Field(
        default=False,
        description="True if the agent ships its own page in agents/<slug>/web/ "
        "instead of relying only on blocks.",
    )

    @model_validator(mode="after")
    def _remote_needs_url(self) -> Manifest:
        if self.location == "remote" and self.base_url is None:
            raise ValueError("remote agents must set base_url")
        if self.location == "local" and self.base_url is not None:
            raise ValueError("local agents must not set base_url")
        return self

    @property
    def python_module(self) -> str:
        """Module name a local agent's backend must use: ``agents/<slug>/backend/<module>/``."""
        return re.sub(r"-", "_", self.slug) + "_agent"


# --- Blocks: what /run returns for the platform to draw --------------------------------


class HeadingBlock(_Strict):
    type: Literal["heading"] = "heading"
    text: str


class TextBlock(_Strict):
    type: Literal["text"] = "text"
    text: str


class NoticeBlock(_Strict):
    """A coloured box. Use 'warning' for anything involving money or risk."""

    type: Literal["notice"] = "notice"
    level: Literal["info", "success", "warning", "danger"] = "info"
    text: str


class Item(_Strict):
    title: str
    subtitle: str = ""
    value: str = Field(default="", description="Right-aligned, e.g. '$15.49 / month'.")


class ItemsBlock(_Strict):
    """A list of things, e.g. bills. Preferred over tables on small screens."""

    type: Literal["items"] = "items"
    items: list[Item]
    empty_text: str = "Nothing to show yet."


class TableBlock(_Strict):
    type: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[str]]

    @model_validator(mode="after")
    def _row_widths(self) -> TableBlock:
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("every row must have one cell per column")
        return self


class LinkBlock(_Strict):
    type: Literal["link"] = "link"
    label: str
    url: HttpUrl


class Action(_Strict):
    """A button. Pressing it calls /run again with ``input`` merged in."""

    label: str
    input: dict[str, Any] = Field(default_factory=dict)
    style: Literal["primary", "secondary", "danger"] = "primary"
    confirm: str | None = Field(
        default=None, description="If set, the platform asks this question before sending."
    )


class ActionsBlock(_Strict):
    type: Literal["actions"] = "actions"
    actions: list[Action]


class FormField(_Strict):
    name: str
    label: str
    kind: Literal["text", "number", "date", "textarea", "email"] = "text"
    required: bool = True
    help: str = ""


class FormBlock(_Strict):
    """Ask the user for input. Submitting calls /run with the field values as ``input``."""

    type: Literal["form"] = "form"
    fields: list[FormField]
    submit_label: str = "Continue"


Block = Annotated[
    HeadingBlock
    | TextBlock
    | NoticeBlock
    | ItemsBlock
    | TableBlock
    | LinkBlock
    | ActionsBlock
    | FormBlock,
    Field(discriminator="type"),
]


# --- Run --------------------------------------------------------------------------------


class RunUser(_Strict):
    """Who is using the agent. Agents never see passwords or emails."""

    id: str
    display_name: str


class RunRequest(_Strict):
    user: RunUser
    rental_id: str
    input: dict[str, Any] = Field(default_factory=dict)


class RunResponse(_Strict):
    status: Literal["ok", "needs_input", "error"]
    message: str = Field(default="", description="Short plain-language summary.")
    blocks: list[Block] = Field(default_factory=list)


class Health(_Strict):
    ok: bool
    detail: str = ""
