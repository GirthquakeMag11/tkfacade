"""The split container: panes side by side, resized by dragging the sashes."""

import tkinter as tk
from collections.abc import Hashable, Iterator, Mapping
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Protocol, cast

from .._types import Orient
from ..events import Destroyed, Event
from ..look import Look
from ..widget import BaseWidget, Widget
from ._frame import Frame


class _PanedCommands(Protocol):
    """The paned subcommands typeshed leaves undeclared.

    ``ttk.Panedwindow`` inherits from ``tk.PanedWindow``, so the
    Python object carries a pile of classic methods the Tcl command
    refuses — ``paneconfigure`` answers *bad command* and names the
    real set (`hazards/tkinter.md`, *Panes*). These three are in that real set
    and untyped, so they are declared here rather than reached for
    through :data:`Any`, which would hide the next one that is not.
    """

    def panes(self) -> tuple[str, ...]:
        """The widget paths of the panes, in order."""

    def pane(self, child: tk.Misc, option: str | None = ..., /, **options: Any) -> Any:
        """Read one of a pane's options, or set them."""

    def sashpos(self, index: int, position: int | None = ..., /) -> int:
        """Read where a sash sits, or move it."""


class PanedFrame(Widget, Mapping[Hashable, Frame]):
    """A container of panes laid side by side, split by draggable sashes.

    Every pane is visible at once and the user redistributes the space
    between them by dragging the sash that divides two neighbours.
    That is what separates this from
    :class:`~tkfacade.AbstractMultiFrame`, whose pages share one region
    and take turns: there is no page showing here, because they all
    are, so this borrows that family's shape — keys naming frames the
    container makes — without claiming its contract.

    A pane is a :class:`~tkfacade.Frame` this container builds and
    hands back for a caller to fill; the container places it and the
    caller never does. Tk is unusually careless here — it accepts a
    pane that is not its child, and accepts a pane being gridded on
    top of the pane management, leaving two geometry managers
    disagreeing in silence. A caller who is handed a frame can do
    neither.

    The mapping face is those panes, keyed as they were added and
    ordered as they sit. A pane destroyed out from under the container
    leaves the mapping, freeing its key to :meth:`add` again.

    :attr:`sash_positions` reads where the divisions are and
    :meth:`move_sash` moves one. Neither is watchable: a sash position
    is layout rather than a value, and Tk announces a drag to nobody —
    moving a sash fires no event on this widget at all, only a
    ``<Configure>`` on the pane that changed size.

    Appearance comes from the ``TPanedwindow`` style.
    """

    if TYPE_CHECKING:
        _tk: ttk.PanedWindow
        _panes: dict[Hashable, Frame]

    __slots__ = ("_panes",)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        orient: Orient = "horizontal",
        width: int = 0,
        height: int = 0,
        look: Look | None = None,
    ) -> None:
        """Create the empty split container.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                container is created inside.
            orient (Orient): The axis the panes are laid along —
                ``"horizontal"`` puts them side by side with vertical
                sashes between. Defaults to ``"horizontal"``. Fixed
                for the widget's life: Tk refuses to change it, and
                the orientation is part of the style name besides.
            width (int): Width to ask for, in pixels. Defaults to 0,
                meaning ask for nothing and size to the panes.
            height (int): Height to ask for, in pixels. Defaults to 0,
                meaning ask for nothing and size to the panes.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._tk = ttk.PanedWindow(self._as_master(parent), orient=orient)
        self._panes = {}
        if width:
            self._tk.configure(width=width)
        if height:
            self._tk.configure(height=height)
        super().__init__()
        if look is not None:
            self.look = look

    def __getitem__(self, key: Hashable) -> Frame:
        """Return the pane frame at ``key``.

        Raises:
            KeyError: If ``key`` names no existing pane.
        """
        if key in self._panes:
            return self._panes[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[Hashable]:
        """Iterate the pane keys, in the order the panes sit."""
        return iter(self._panes)

    def __len__(self) -> int:
        """The number of panes the container holds."""
        return len(self._panes)

    def __eq__(self, other: object) -> bool:
        """Equal only to itself: identity, not contents."""
        return self is other

    def __hash__(self) -> int:
        """Hash consistently with :meth:`__eq__`."""
        return id(self)

    @property
    def _commands(self) -> _PanedCommands:
        """The paned subcommands, typed."""
        return cast(_PanedCommands, self._tk)

    def _claim(self, key: Hashable, /) -> None:
        """Refuse a key that already names a pane.

        Raises:
            ValueError: If ``key`` names an existing pane.
        """
        if key in self._panes:
            raise ValueError(f"pane {key!r} already exists")

    def _adopt(self, key: Hashable, child: Frame, index: int | None, weight: int, /) -> None:
        """Enter a built pane in the books and hand it to Tk to place."""
        self._panes[key] = child
        if index is None:
            self._tk.add(child._tk, weight=weight)
        else:
            self._tk.insert(index, child._tk, weight=weight)
            self._panes = {
                self._key_for(path): self._panes[self._key_for(path)]
                for path in self._commands.panes()
            }

        def forget(_event: Event) -> None:
            self._forget_pane(key, child)

        child.bind(Destroyed(), forget)

    def _forget_pane(self, key: Hashable, child: Frame, /) -> None:
        """Take a destroyed pane out of the books.

        Identity-guarded, so only the pane that died evicts its key —
        a live replacement under the same key is never touched.
        """
        if self._panes.get(key) is child:
            del self._panes[key]

    def _key_for(self, path: str, /) -> Hashable:
        """The key of the pane Tk names by widget path.

        Raises:
            KeyError: If no pane answers to that path.
        """
        for key, child in self._panes.items():
            if str(child._tk) == str(path):
                return key
        raise KeyError(path)

    @property
    def orient(self) -> Orient:
        """The axis the panes are laid along; fixed at construction."""
        return str(self._tk.cget("orient"))  # type: ignore[return-value]

    @property
    def sash_positions(self) -> tuple[int, ...]:
        """Where each sash sits, in pixels along :attr:`orient`.

        One fewer than the panes: a sash divides two neighbours, so an
        empty or single-pane container has none. Read live from Tk.
        """
        return tuple(
            int(self._commands.sashpos(index)) for index in range(max(len(self._panes) - 1, 0))
        )

    def add(self, key: Hashable, /, *, weight: int = 0) -> Frame:
        """Add a pane at the end and return the frame to fill.

        Args:
            key (Hashable): What the pane answers to.
            weight (int): The pane's share of space left over once
                every pane has what it asked for. Defaults to 0,
                meaning it takes none of the surplus and keeps its own
                size.

        Returns:
            The new pane's frame.

        Raises:
            ValueError: If ``key`` names an existing pane.
        """
        self._claim(key)
        child = Frame(self)
        self._adopt(key, child, None, weight)
        return child

    def insert(self, index: int, key: Hashable, /, *, weight: int = 0) -> Frame:
        """Add a pane at ``index`` and return the frame to fill.

        Args:
            index (int): Where among the existing panes it goes; past
                the end appends.
            key (Hashable): What the pane answers to.
            weight (int): The pane's share of the surplus space.
                Defaults to 0.

        Returns:
            The new pane's frame.

        Raises:
            ValueError: If ``key`` names an existing pane.
        """
        self._claim(key)
        position = None if index >= len(self._panes) else max(index, 0)
        child = Frame(self)
        self._adopt(key, child, position, weight)
        return child

    def forget(self, key: Hashable, /) -> None:
        """Remove a pane, destroying the frame that was it.

        Args:
            key (Hashable): The pane to remove.

        Raises:
            KeyError: If ``key`` names no existing pane.
        """
        child = self[key]
        self._tk.forget(child._tk)
        # the Destroyed binding takes it out of the books
        child.destroy()

    def weight(self, key: Hashable, /) -> int:
        """The pane's share of the space left over.

        Args:
            key (Hashable): The pane to ask about.

        Returns:
            The weight.

        Raises:
            KeyError: If ``key`` names no existing pane.
        """
        return int(self._commands.pane(self[key]._tk, "weight"))

    def set_weight(self, key: Hashable, weight: int, /) -> None:
        """Set the pane's share of the space left over.

        Args:
            key (Hashable): The pane to change.
            weight (int): Its share of the surplus; 0 takes none.

        Raises:
            KeyError: If ``key`` names no existing pane.
        """
        self._commands.pane(self[key]._tk, weight=weight)

    def move_sash(self, index: int, position: int, /) -> None:
        """Put the sash at ``index`` at ``position`` pixels along the axis.

        The write half of :attr:`sash_positions`. Tk settles the sash
        where the panes around it allow, so reading the position back
        may answer near what was asked rather than exactly it.

        Args:
            index (int): Which sash, counting from the start; there is
                one fewer than there are panes.
            position (int): Where to put it, in pixels along
                :attr:`orient`.

        Raises:
            IndexError: If no sash answers to that index.
        """
        if not 0 <= index < max(len(self._panes) - 1, 0):
            raise IndexError(
                f"no sash at {index}: {len(self._panes)} panes have {max(len(self._panes) - 1, 0)}"
            )
        self._commands.sashpos(index, position)
