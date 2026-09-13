"""Types for the raw field dict of a delivered Tk event."""

import tkinter as tk
from typing import Literal, NotRequired, TypedDict

type NA = Literal["??"] | Literal[""]
"""What a field holds when it does not apply to the event type:
``"??"``, Tk's substitution for an inapplicable percent code, or the
empty string."""

type VisibilityStateName = Literal[
    "VisibilityUnobscured",
    "VisibilityPartiallyObscured",
    "VisibilityFullyObscured",
]
"""Names delivered as the ``state`` field of a Visibility event."""


class RawEventDict(TypedDict):
    """Raw fields of a Tk event, exactly as tkinter delivers them.

    Fields the event type does not carry degrade to :data:`NA`. Two
    fields fall back further inside tkinter itself: ``type`` stays the
    raw ``str`` or ``int`` when ``tk.EventType()`` rejects the value,
    and ``widget`` stays the Tk path string when ``_nametowidget``
    raises ``KeyError``.
    """

    serial: int
    num: int | NA
    delta: int | NA
    focus: NotRequired[bool]
    height: int | NA
    keycode: int | NA
    state: int | VisibilityStateName | NA
    time: int | NA
    width: int | NA
    x: int | NA
    y: int | NA
    char: str | NA
    send_event: bool
    keysym: str | NA
    keysym_num: int | NA
    type: tk.EventType | str | int  # tkinter falls back to the raw value if EventType() rejects it.
    widget: tk.Misc | str  # Falls back to the Tk path string when _nametowidget raises KeyError.
    x_root: int | NA
    y_root: int | NA
