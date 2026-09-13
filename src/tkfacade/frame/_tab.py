"""Card-stack container whose pages are the tabs of a ``ttk.Notebook``."""

import tkinter as tk
from collections.abc import Hashable, Iterator
from tkinter import ttk
from typing import TYPE_CHECKING

from ..events import Destroyed, Event, Virtual, VirtualEvent
from ..look import Look
from ..widget import BaseWidget
from ._abstract import AbstractMultiFrame
from ._frame import Frame


class TabFrame(AbstractMultiFrame):
    """A card stack whose pages are the tabs of a ``ttk.Notebook``.

    The container is the notebook itself, so the user can switch
    pages too; :meth:`show` selects the matching tab. A notebook has
    no relief or borderwidth of its own, so unlike :class:`StackFrame`
    a ``TabFrame`` takes no ``relief``.
    """

    __slots__ = (
        "_children",
        "_current",
    )

    if TYPE_CHECKING:
        _tk: ttk.Notebook
        _children: dict[Hashable, Frame]
        _current: Hashable | None

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        look: Look | None = None,
    ) -> None:
        """Create the empty tabbed container.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                container is created inside.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._tk = ttk.Notebook(self._as_master(parent))
        self._children = {}
        self._current = None
        super().__init__()
        self.bind(Virtual(VirtualEvent.NOTEBOOK_TAB_CHANGED), self._on_tab_changed)
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

    def _forget_page(self, key: Hashable, child: Frame, /) -> None:
        """Take a destroyed page out of the books.

        Identity-guarded, so only the page that died evicts its key —
        a live replacement under the same key is never touched. The
        notebook forgets the tab itself; selection of a survivor, if
        any, arrives as ``<<NotebookTabChanged>>``.
        """
        if self._children.get(key) is child:
            del self._children[key]
            if self._current == key:
                self._current = None

    def _on_tab_changed(self, _event: Event, /) -> None:
        """Track the selected tab so :attr:`showing` follows user clicks."""
        selected: str = self._tk.select()  # type: ignore[no-untyped-call]
        if not selected:
            return
        widget = self._tk.nametowidget(selected)
        for key, child in self._children.items():
            if child._tk is widget:
                self._current = key
                return

    @property
    def showing(self) -> Frame | None:
        """The page currently shown, or ``None`` before any show."""
        if self._current is not None:
            return self._children[self._current]
        return None

    def add(self, key: Hashable, /, *, title: str | None = None) -> Frame:
        """Hand a new page to the notebook as a tab and return its frame.

        Args:
            key (Hashable): Key for the new page.
            title (str | None): Tab label. Defaults to None, meaning
                ``str(key)`` is used.

        Returns:
            The new page frame.

        Raises:
            ValueError: If ``key`` names an existing page, or is None —
                the nothing-shown sentinel.
        """
        if key is None:
            raise ValueError("None is the nothing-shown sentinel and cannot key a page")
        if key in self._children:
            raise ValueError(f"frame {key!r} already exists")
        child = Frame(self)
        self._children[key] = child

        def forget(_event: Event) -> None:
            self._forget_page(key, child)

        child.bind(Destroyed(), forget)
        self._tk.add(child._tk, text=title if title is not None else str(key))
        return child

    def show(self, key: Hashable, /) -> None:
        """Select the tab of the page at ``key``.

        Raises:
            KeyError: If ``key`` names no existing page.
        """
        if key not in self._children:
            raise KeyError(key)
        self._tk.select(self._children[key]._tk)  # type: ignore[no-untyped-call]
        self._current = key
