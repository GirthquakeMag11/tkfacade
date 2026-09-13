"""Card-stack container whose pages share one grid cell, one mapped at a time."""

import tkinter as tk
from collections.abc import Hashable, Iterator
from contextlib import suppress
from tkinter import ttk
from typing import TYPE_CHECKING

from .._types import Relief
from ..events import Destroyed, Event
from ..look import Look
from ._abstract import AbstractMultiFrame
from ._frame import Frame

if TYPE_CHECKING:
    from ..widget import BaseWidget


class StackFrame(AbstractMultiFrame):
    """A card stack whose pages share one grid cell, one mapped at a time.

    Every page is gridded into cell (0, 0) with ``sticky="nsew"``;
    :meth:`show` maps one and unmaps the rest, so which page is
    visible is the container's decision alone. Being a plain frame,
    it takes a ``relief`` of its own.

    Appearance comes from the ``TFrame`` style rather than from
    per-widget options; the ``relief`` this frame takes is its own,
    and being the widget's own it wins outright over a relief asked
    for by a style.
    """

    __slots__ = (
        "_children",
        "_current",
        "_first_show_job",
    )

    if TYPE_CHECKING:
        _tk: ttk.Frame
        _children: dict[Hashable, Frame]
        _current: Hashable | None
        _first_show_job: str | None

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        relief: Relief = "flat",
        look: Look | None = None,
    ) -> None:
        """Create the empty stack container.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                container is created inside.
            relief (Relief): Border style of the container itself.
                Defaults to ``"flat"``, meaning no visible border.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._tk = ttk.Frame(self._as_master(parent), relief=relief)
        self._children = {}
        self._tk.rowconfigure(0, weight=1)
        self._tk.columnconfigure(0, weight=1)
        self._current = None
        self._first_show_job = None
        super().__init__()
        self.bind(Destroyed(), self._cancel_first_show)
        if look is not None:
            self.look = look

    def __getitem__(self, key: Hashable) -> Frame:
        """Return the page frame at ``key``.

        Raises:
            KeyError: If ``key`` names no existing page.
        """
        if key in self._children:
            return self._children[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[Hashable]:
        """Iterate over the page keys, in the order the pages were added."""
        return iter(self._children)

    def __len__(self) -> int:
        """The number of pages the container holds."""
        return len(self._children)

    def _cancel_first_show(self, _event: Event) -> None:
        """Drop any pending first show once the container is gone."""
        if self._first_show_job is not None:
            with suppress(tk.TclError):
                self._tk.after_cancel(self._first_show_job)
            self._first_show_job = None

    def _forget_page(self, key: Hashable, child: Frame, /) -> None:
        """Take a destroyed page out of the books.

        Identity-guarded, so only the page that died evicts its key —
        a live replacement under the same key is never touched.
        """
        if self._children.get(key) is child:
            del self._children[key]
            if self._current == key:
                self._current = None

    def _show_first(self, key: Hashable, /) -> None:
        """Run the deferred first show, unless its page has gone.

        A gone page is skipped; the stack shows nothing until told
        otherwise.

        Args:
            key (Hashable): The page to show, unless an explicit
                :meth:`show` has already chosen one.
        """
        self._first_show_job = None
        target = self._current if self._current is not None else key
        if target in self._children:
            self.show(target)

    @property
    def showing(self) -> Frame | None:
        """The page currently shown, or ``None`` before any show."""
        if self._current is not None:
            return self._children[self._current]
        return None

    def add(self, key: Hashable, /) -> Frame:
        """Grid a new page into the shared cell and return its frame.

        Raises:
            ValueError: If ``key`` names an existing page, or is None —
                the nothing-shown sentinel.
        """
        if key is None:
            raise ValueError("None is the nothing-shown sentinel and cannot key a page")
        if key in self._children:
            raise ValueError(f"frame {key!r} already exists")
        was_empty = not self._children
        child = Frame(self)
        self._children[key] = child

        def forget(_event: Event) -> None:
            self._forget_page(key, child)

        child.bind(Destroyed(), forget)
        child.grid(row=0, column=0, sticky="nsew")
        if was_empty:
            if self._first_show_job is not None:
                with suppress(tk.TclError):
                    self._tk.after_cancel(self._first_show_job)
            self._first_show_job = self._tk.after(0, self._show_first, key)
        else:
            child.grid_remove()
        return child

    def show(self, key: Hashable, /) -> None:
        """Map the page at ``key`` and unmap its siblings.

        Raises:
            KeyError: If ``key`` names no existing page.
        """
        if key not in self._children:
            raise KeyError(key)
        child = self._children[key]
        child.grid()
        for other in self._children.values():
            if other is not child:
                other.grid_remove()
        self._current = key
