"""Helpers with no home of their own.

A function earns a place here by being useful to more than one
subpackage and specific to none of them.
"""

import textwrap
import tkinter as tk
import unicodedata
from collections.abc import Iterable, Iterator
from contextlib import suppress
from tkinter import ttk
from typing import Literal

from ._types import Rect, SelectParam


def font_character_width(w: tk.Misc, /) -> int:
    return tk.font.Font(w.cget("font")).measure("0")


def widget_width_in_characters(w: tk.Misc, /) -> float:
    return w.winfo_width() / font_character_width(w)


def wrap_text(data: str, width: int, mode: Literal["word", "char"] = "word") -> list[str]:
    if mode == "word":
        return textwrap.wrap(data, width=width)
    elif mode == "char":
        return [data[i : i + width] for i in range(0, len(data), width)]
    else:
        raise ValueError("mode must be 'word' or 'char'")


def justify_all(
    strings: Iterable[str],
    width: int,
    mode: Literal["left", "right", "center"] = "left",
) -> list[str]:
    align = {"left": str.ljust, "right": str.rjust, "center": str.center}[mode]
    return [align(s, width) for s in strings]


def images_in_use(w: tk.Misc, /, recurse_children: bool = True) -> set[str]:
    found: set[str] = set()

    def _names(value: object) -> Iterator[str]:
        if isinstance(value, (tuple, list)):
            for v in value:
                yield from _names(v)
        elif value:
            yield str(value)

    for opt in ("image", "selectimage", "tristateimage"):
        with suppress(tk.TclError):
            found.update(_names(w.cget(opt)))

    if isinstance(w, tk.Menu):
        # parenthesized: `or` binds looser than `+`, and the unbracketed spelling skipped the last entry
        for i in range((w.index("end") or 0) + 1):
            for opt in ("image", "selectimage"):
                with suppress(tk.TclError):
                    found.update(_names(w.entrycget(i, opt)))

    if isinstance(w, tk.Text):
        for name in w.image_names():
            found.update(_names(w.image_cget(name, "-image")))

    if isinstance(w, tk.Canvas):
        for item in w.find_withtag("all"):
            if w.type(item) == "image":  # type: ignore[comparison-overlap]
                for opt in ("image", "activeimage", "disabledimage"):
                    found.update(_names(w.itemcget(item, opt)))  # type: ignore[no-untyped-call]

    if isinstance(w, ttk.Treeview):
        stack = list(w.get_children(""))
        while stack:
            iid = stack.pop()
            found.update(_names(w.item(iid, "image")))
            stack.extend(w.get_children(iid))
        for col in ("#0", *w.cget("columns")):
            found.update(_names(w.heading(col, "image")))

    if isinstance(w, ttk.Notebook):
        for tab in w.tabs():  # type: ignore[no-untyped-call]
            found.update(_names(w.tab(tab, "image")))  # type: ignore[no-untyped-call]

    if recurse_children:
        for child in w.winfo_children():
            found |= images_in_use(child)

    return found


def screen_rect(widget: tk.Misc, /) -> Rect:
    """Return ``widget``'s current area in screen coordinates.

    Screen coordinates because callers compare widgets from different
    levels of the hierarchy, which share no other frame of reference.

    Args:
        widget (tk.Misc): The widget to measure.

    Returns:
        The box the widget occupies. Meaningful only after Tk's
        geometry pass has run; before then Tk reports a 1x1
        placeholder.
    """
    left = widget.winfo_rootx()
    top = widget.winfo_rooty()
    return (left, top, left + widget.winfo_width(), top + widget.winfo_height())


def intersects(first: Rect, second: Rect, /) -> bool:
    """Return whether two boxes share at least one pixel.

    Boxes are half-open, so ones that merely abut do not intersect.

    >>> intersects((0, 0, 10, 10), (10, 0, 20, 10))
    False
    >>> intersects((0, 0, 10, 10), (5, 5, 15, 15))
    True

    Args:
        first (Rect): One box.
        second (Rect): The other box.

    Returns:
        True if the boxes overlap.
    """
    return (
        first[0] < second[2]
        and second[0] < first[2]
        and first[1] < second[3]
        and second[1] < first[3]
    )


def format_time(seconds: float, /) -> str:
    """Render a duration as H:MM:SS, or M:SS when the hour is zero.

    >>> format_time(0.0)
    '0:00'
    >>> format_time(3661.0)
    '1:01:01'

    Args:
        seconds (float): The duration. Negative values read as zero: a
            clock running backwards means the caller has a bug, and a
            readout is not where to report it.

    Returns:
        The formatted duration.
    """
    total = int(max(seconds, 0.0))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _tokenize(text: str) -> list[str]:
    """Split ``text`` into alphanumeric runs, discarding separators.

    Runs are read after NFC normalization, so composed and decomposed
    spellings tokenize alike, and a combining mark rides the run it
    follows rather than splitting it.

    >>> _tokenize("first_name")
    ['first', 'name']
    """
    tokens: list[str] = []
    current: list[str] = []
    for char in unicodedata.normalize("NFC", text):
        joins = char != "_" and (
            char.isalnum() or (bool(current) and unicodedata.category(char).startswith("M"))
        )
        if joins:
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def to_title_case(text: str) -> str:
    """Convert an identifier-like string to spaced Title Case.

    Tokens are the alphanumeric runs of ``text``; separators (``_``,
    ``-``, whitespace) become single spaces. A token starting with a
    digit is kept as-is.

    >>> to_title_case("first_name")
    'First Name'
    >>> to_title_case("")
    ''

    Args:
        text (str): The string to convert.

    Returns:
        The title-cased string; empty when ``text`` has no tokens.
    """
    return " ".join(word.title() if word[0].isalpha() else word for word in _tokenize(text))


def to_snake_case(text: str) -> str:
    """Convert an identifier-like string to snake_case.

    Tokens are the alphanumeric runs of ``text``, casefolded and joined
    with ``_``. Case boundaries within a token are not split
    (``"FirstName"`` is one token).

    >>> to_snake_case("First Name")
    'first_name'

    Args:
        text (str): The string to convert.

    Returns:
        The snake-cased string; empty when ``text`` has no tokens.
    """
    return "_".join(word.casefold() for word in _tokenize(text))


def select_param(enabled: bool, extended: bool) -> SelectParam:
    """Translate two booleans into Tk's ``selectmode`` option literal.

    Args:
        enabled (bool): Whether selection is possible at all.
        extended (bool): Whether more than one thing may be selected
            at once; ignored when ``enabled`` is False.

    Returns:
        ``"extended"``, ``"browse"``, or ``"none"``.
    """
    match enabled, extended:
        case True, True:
            return "extended"
        case True, False:
            return "browse"
        case False, _:
            return "none"
        case _:
            raise ValueError((enabled, extended))
