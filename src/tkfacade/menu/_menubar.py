"""The Menubar wrapper: the row of menus across a window's top."""

import tkinter as tk
from typing import TYPE_CHECKING

from ..events import Event
from ..widget import BaseWidget
from ._menu import MenuBase
from ._rows import MenuPart

if TYPE_CHECKING:
    from ..window import Window


class Menubar(BaseWidget, MenuBase):
    """A window's menu bar: the row its menus are drawn across.

    Built by a :class:`~tkfacade.Window` asked for one and reachable
    only through it, so a caller fills the bar without naming the menu
    inside it::

        window = Window(title="Editor", menubar=True)
        edit = window.menubar.insert_submenu("Edit")
        edit.insert_command("Undo", command=undo)

    Rows come back as handles rather than being addressed by their text
    afterwards, which is what lets two menus share a name. That is not
    a convenience here but the only workable addressing: Tk matches an
    entry's label with glob patterns, resolves the reserved words and
    any decimal string ahead of matching at all, and clamps an
    out-of-range index onto the last entry rather than refusing it
    (`hazards/tkinter.md`, *Menus*). None of that is reachable through a handle,
    which finds its own position by identity.

    **The bar takes no command and no separator.** A command in a
    window's top row is indistinguishable from a menu — Tk draws the
    two identically (`hazards/tkinter.md`, *Menus*) — and a rule draws nothing
    at all while still occupying a position, so both calls are absent
    rather than present and inert. That is why the bar wears
    :class:`~tkfacade.MenuBase` where a menubutton and a submenu wear
    :class:`~tkfacade.RuledMenu`, which takes both.

    **The bar is not an event surface.** Tk does not show the menu it
    is given: it builds a hidden clone and shows that, and a binding
    that fires from the clone reports a widget path no wrapper can be
    found for. What a user does here arrives as the row's command or
    through its observable, which says which row was chosen — the same
    division :class:`~tkfacade.Menubutton` draws for its own menu, and
    Tk's rather than the library's.

    **Appearance waits on the styling facade.** A menubar is a classic
    ``tk.Menu`` and has no ttk style at all, so its colors, font and
    relief are genuinely its own rather than a theme's — and none of
    them rides this constructor, because a per-widget appearance option
    with no way to reach the theme behind it is half a feature. The
    hole is the styling facade for classic widgets: a classic ``tk.Menu``
    has no ttk style to reach, so its appearance is its own rather than
    a theme's until such a facade exists. The same applies to every
    classic widget the library hosts.
    """

    if TYPE_CHECKING:
        _tk: tk.Menu

    __slots__ = ("_parts", "_tk_menu", "_window")

    def __init__(self, window: Window, /) -> None:
        """Create the bar and install it on ``window``.

        Args:
            window (Window): The window the bar is drawn across. A
                window builds its own bar and never adopts one: Tk
                checks nothing about the menu named in a toplevel's
                ``-menu``, accepts a path that names a dead widget or
                no widget, and resolves the path against whichever
                interpreter is asking, so a menu built anywhere else is
                a lifetime nobody owns (`hazards/tkinter.md`, *Menus*).
        """
        # one object under two names: a bar wraps the menu itself, so the two names meet here
        self._tk = self._tk_menu = tk.Menu(window._tk, tearoff=False)
        self._parts: list[MenuPart] = []
        self._window = window
        super().__init__()
        window._tk["menu"] = str(self._tk)

    def _give_back_transports(self, event: Event) -> None:
        """Release every parked observable's ride when the window dies.

        Subscribed by the window rather than here, and to the
        *window's* destruction rather than the bar's own, which is the
        only route that fires. A wrapper evicts itself from the
        registry as its widget is destroyed, and an event's widget is
        resolved through that registry — so by the time a ``<Destroy>``
        on the menu reaches a subscriber, the bar can no longer be
        recognised in it and a guard comparing against ``self`` would
        reject every event it will ever see. A window is still
        resolvable in its own. The window subscribes because a bar is
        built while the window is still constructing, before the
        window can take a subscriber at all.

        The guard makes the release happen once rather than once per
        widget torn down under the window, the binding hearing all of
        them (`hazards/tkinter.md`, *Bindings*).
        """
        if event.widget is not self._window:
            return
        self._release_deeply()
