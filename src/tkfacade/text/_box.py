import tkinter as tk
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from tkinter import ttk
from typing import Literal

from ..look import Look
from ..scroll import AbstractScrollable, ScrollbarSpec
from ..widget import BaseWidget
from ._abstract import AbstractTextInterface


def _wrap_param(word: bool, char: bool) -> Literal["none", "char", "word"]:
    """Translate two booleans into Tk's ``wrap`` option literal.

    Args:
        word (bool): Whether a long line may break at a word boundary.
        char (bool): Whether it may break mid-word; takes precedence.

    Returns:
        The matching literal; ``"none"`` when both are False — the
        only setting a horizontal scrollbar can scroll.
    """
    match word, char:
        case False, False:
            return "none"
        case True, False:
            return "word"
        case _, True:
            return "char"
        case _:
            raise ValueError((word, char))


class TextBox(AbstractTextInterface, AbstractScrollable):
    """A scrolling multi-line text input, editable or read-only.

    The Tk text widget sits in a frame with optional scrollbars in the
    gutter cells, and that frame is what a caller lays out.

    A read-only box still takes keyboard focus, so its content can be
    selected and copied, and assigning :attr:`text` still works; only
    GUI editing is locked out.

    The content is not watchable yet. Tk's text widget has no variable
    channel, and its ``<<Modified>>`` virtual event fires when the
    modified flag first sets and then holds until that flag is reset —
    a flag this wrapper does not expose — so a facade binding hears the
    first edit only. A content-watch seam will need its own channel;
    none exists here.

    Styling exception: the text area is a classic ``tk.Text`` the theme
    system does not govern, so a :class:`~tkfacade.Look` reaches only
    the gutter scrollbars here.
    """

    __slots__ = ("_text",)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        text: str = "",
        *,
        read_only: bool = False,
        width: int = 80,
        height: int = 24,
        wrap_word: bool = True,
        wrap_char: bool = False,
        vertical_scrollbar: bool | ScrollbarSpec = True,
        horizontal_scrollbar: bool | ScrollbarSpec = False,
        look: Look | None = None,
    ) -> None:
        """Create the box, its scrollbars, and any initial content.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the box
                is created inside.
            text (str): Initial content. Defaults to ``""``, meaning
                the box starts empty.
            read_only (bool): Whether to start disabled, locking the
                GUI out of editing. Defaults to False.
            width (int): Width in characters. Defaults to 80.
            height (int): Height in lines. Defaults to 24.
            wrap_word (bool): Whether long lines may break at word
                boundaries. Defaults to True.
            wrap_char (bool): Whether long lines may break mid-word;
                takes precedence over ``wrap_word``. Defaults to
                False.
            vertical_scrollbar (bool | ScrollbarSpec): Whether to add a vertical
                scrollbar. Defaults to True.
            horizontal_scrollbar (bool | ScrollbarSpec): Whether to add a horizontal
                scrollbar; it can only scroll when both wraps are
                False. Defaults to False.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._tk: ttk.Frame = ttk.Frame(self._as_master(parent))
        self._text: tk.Text = tk.Text(
            self._tk,
            width=width,
            height=height,
            wrap=_wrap_param(wrap_word, wrap_char),
            takefocus=True,
            state="normal",
        )
        self._build_gutters(
            self._text, vertical=vertical_scrollbar, horizontal=horizontal_scrollbar
        )
        if text:
            self._text.insert("1.0", text)
        if read_only:
            self._text.configure(state="disabled")
        super().__init__()
        self._route_events(self._text, *self._scroll_bars.values())
        if look is not None:
            self.look = look

    @contextmanager
    def _writable(self) -> Iterator[None]:
        """Lift the disabled state for the duration of a write.

        Restores whatever state it found, so nesting is safe and it is a
        no-op on an enabled box.

        Yields:
            None, with the box editable.
        """
        was_disabled = self.disabled
        self.enable()
        try:
            yield
        finally:
            if was_disabled:
                self.disable()

    @property
    def disabled(self) -> bool:
        """Whether the GUI is locked out of editing; read live from Tk."""
        return str(self._text.cget("state")) == "disabled"

    @property
    def is_empty(self) -> bool:
        """Whether the box holds no text."""
        return not self._text.get("1.0", "end-1c")

    @property
    def text(self) -> str:
        """The whole content, without the trailing newline Tk keeps.

        Assigning replaces the whole content — newlines start new
        lines — and works even while disabled.
        """
        return self._text.get("1.0", "end-1c")

    @text.setter
    def text(self, value: str) -> None:
        with self._writable():
            self._text.replace("1.0", "end-1c", value)

    @property
    def selection(self) -> str:
        """The selected text; ``""`` when nothing is selected."""
        with suppress(tk.TclError):
            return self._text.get("sel.first", "sel.last")
        return ""

    def disable(self) -> None:
        """Lock the GUI out of editing; the content is left alone."""
        self._text.configure(state="disabled")

    def enable(self) -> None:
        """Let the GUI edit again; the content is left alone."""
        self._text.configure(state="normal")

    def select_all(self) -> None:
        """Select the whole content, replacing any existing selection."""
        self._text.tag_remove("sel", "1.0", "end")
        self._text.tag_add("sel", "1.0", "end-1c")

    def select_none(self) -> None:
        """Clear the selection; a no-op when nothing is selected."""
        self._text.tag_remove("sel", "1.0", "end")

    def copy_selection(self) -> str:
        """Copy the selection to the clipboard.

        Works while disabled, since copying only reads.

        Returns:
            The text copied, or ``""`` when nothing was selected — in
            which case the clipboard is left untouched.
        """
        selected = self.selection
        if selected:
            self._text.clipboard_clear()
            self._text.clipboard_append(selected)
        return selected
