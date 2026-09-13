"""The toplevel window wrapper."""

import re
import tkinter as tk
from tkinter import ttk

from ..events import Destroyed
from ..media import ImageInput, ImageWrapper, window_icon
from ..menu import Menubar
from ..widget import ContainerWidget
from ._root import BaseWindow, Root, get_root

_GEOMETRY_RE = re.compile(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)")
"""Tk geometry strings are ``WIDTHxHEIGHT+X+Y``; offsets may be negative."""


class Window(ContainerWidget):
    """A toplevel attached to the shared (or a given) :class:`Root`.

    Destroying the last live window on *this* root tears that root down
    and ends its mainloop; a window on a caller-supplied root never
    reaches the shared one. Geometry, size limits, and resizability are
    read/write properties; a read returns the last requested value
    until that request has been applied by the window manager (at
    which point a read answers what Tk reports), and geometry writes
    are safe back-to-back: one assigned before the window manager has
    applied the previous one does not undo it.

    The window holds its icon and menu bar alive, so neither needs
    keeping on the caller's side; the icon is reached again through
    :attr:`icon`.

    A corner resize grip is the window's to offer rather than a widget
    to build, since the only place one is any use is a window's
    bottom-right corner: see :attr:`sizegrip`.
    """

    __slots__ = ("_icon", "_menubar", "_requested", "_root", "_sizegrip")

    def __init__(
        self,
        *,
        title: str | None = None,
        width: int = 300,
        height: int = 300,
        x_position: int = 100,
        y_position: int = 100,
        min_width: int | None = None,
        min_height: int | None = None,
        max_width: int | None = None,
        max_height: int | None = None,
        resizable_width: bool | None = None,
        resizable_height: bool | None = None,
        sizegrip: bool = False,
        menubar: bool = False,
        icon: ImageInput | None = None,
        root: Root | None = None,
    ) -> None:
        """Create the toplevel and apply title, geometry, and limits.

        Args:
            title (str | None): Window title. Defaults to None, meaning
                the class name.
            width (int): Initial width in pixels. Defaults to 300.
            height (int): Initial height in pixels. Defaults to 300.
            x_position (int): Initial left edge, in pixels from the
                screen's left. Defaults to 100.
            y_position (int): Initial top edge, in pixels from the
                screen's top. Defaults to 100.
            min_width (int | None): Minimum width in pixels. Defaults to
                None, leaving Tk's current minimum.
            min_height (int | None): Minimum height in pixels. Defaults
                to None, leaving Tk's current minimum.
            max_width (int | None): Maximum width in pixels. Defaults to
                None, leaving Tk's current maximum.
            max_height (int | None): Maximum height in pixels. Defaults
                to None, leaving Tk's current maximum.
            resizable_width (bool | None): Whether the user may resize
                horizontally. Defaults to None, leaving Tk's setting.
            resizable_height (bool | None): Whether the user may resize
                vertically. Defaults to None, leaving Tk's setting.
            sizegrip (bool): Whether to put a resize grip in the
                bottom-right corner. Defaults to False.
            menubar (bool): Whether to give the window a menu bar,
                reachable afterwards as :attr:`menubar`. Defaults to
                False: an empty bar still reserves a strip of the
                window, so one is never built unasked.
            icon (ImageInput | None): Window icon, scaled to fit 64x64
                via :func:`~tkfacade.media.window_icon`. Defaults to None,
                leaving Tk's setting.
            root (Root | None): The root to attach to. Defaults to None,
                meaning the shared :func:`get_root` root.

        Raises:
            OSError: If ``icon`` names a source that cannot be found,
                read, or decoded — before the window exists, so a
                failed construction leaves nothing behind.
        """
        self._root: Root = root if root is not None else get_root()
        icon_wrapper: ImageWrapper | None = None
        if icon is not None:
            icon_wrapper = window_icon(icon)
            icon_wrapper.photo_for(self._root._tk)
        self._tk: BaseWindow = BaseWindow(self._root._tk, owner=self._root)
        try:
            self._tk.geometry(f"{width!s}x{height!s}+{x_position!s}+{y_position!s}")
            self._requested: tuple[int | None, int | None, int | None, int | None] = (
                width,
                height,
                x_position,
                y_position,
            )
            self._tk.bind("<Configure>", self._forget_requested, add="+")
            self._sizegrip: ttk.Sizegrip | None = None
            self._tk.bind("<Configure>", self._raise_sizegrip, add="+")
            self._tk.bind("<Map>", self._raise_sizegrip, add="+")
            self._tk.title(title if title is not None else type(self).__name__)
            if min_width is not None or min_height is not None:
                current_w, current_h = self._tk.minsize()
                self._tk.minsize(
                    min_width if min_width is not None else current_w,
                    min_height if min_height is not None else current_h,
                )
            if max_width is not None or max_height is not None:
                current_w, current_h = self._tk.maxsize()
                self._tk.maxsize(
                    max_width if max_width is not None else current_w,
                    max_height if max_height is not None else current_h,
                )
            if resizable_width is not None or resizable_height is not None:
                current_rw, current_rh = self._tk.resizable()
                self._tk.resizable(
                    resizable_width if resizable_width is not None else current_rw,
                    resizable_height if resizable_height is not None else current_rh,
                )
            if sizegrip:
                self.sizegrip = True
            self._menubar: Menubar | None = Menubar(self) if menubar else None
            self._icon: ImageWrapper | None = icon_wrapper
            if icon_wrapper is not None:
                self._apply_icon(icon_wrapper)
        except BaseException:
            tk.Toplevel.destroy(self._tk)
            raise
        self._root.add_child(self)
        super().__init__()
        if self._menubar is not None:
            self.bind(Destroyed(), self._menubar._give_back_transports)

    def _dimensions(self) -> tuple[int, int, int, int]:
        """Return the current ``(width, height, x, y)`` parsed from Tk.

        Raises:
            ValueError: If Tk reports a geometry string this wrapper
                cannot parse.
        """
        vals = self._tk.geometry()
        match = _GEOMETRY_RE.fullmatch(vals)
        if match is None:
            raise ValueError(f"unparseable Tk geometry string: {vals!r}")
        return (int(match[1]), int(match[2]), int(match[3]), int(match[4]))

    def _forget_requested(self, event: tk.Event[tk.Misc]) -> None:
        """Drop the requested-geometry memo once Tk answers with a geometry.

        Whatever prompted the ``<Configure>`` — this wrapper's own
        write landing, or the user dragging an edge — Tk's report is
        now the truth, and a memo kept past that would re-request a
        size the user has since changed.

        Args:
            event (tk.Event[tk.Misc]): The ``<Configure>`` that
                arrived. Ignored unless it names the toplevel itself.
        """
        if event.widget is self._tk:
            self._requested = (None, None, None, None)

    def _set_dimensions(
        self, width: int | None, height: int | None, x_pos: int | None, y_pos: int | None
    ) -> None:
        """Write geometry as one call, filling gaps from the values in force.

        A single ``wm geometry`` write, because back-to-back writes
        race Tk's internal apply and the earlier one gets clobbered. A
        gap is filled from the geometry last asked for while that is
        still outstanding, and from Tk's report otherwise: Tk answers
        with the size the window *has*, which until the window manager
        applies a pending request is the size it had before.

        Args:
            width (int | None): New width in pixels; None keeps the
                one in force.
            height (int | None): New height in pixels; None keeps the
                one in force.
            x_pos (int | None): New left offset; None keeps the one in
                force.
            y_pos (int | None): New top offset; None keeps the one in
                force.
        """
        dimensions = self._dimensions()
        requested = self._requested
        if width is None:
            width = requested[0] if requested[0] is not None else dimensions[0]
        if height is None:
            height = requested[1] if requested[1] is not None else dimensions[1]
        if x_pos is None:
            x_pos = requested[2] if requested[2] is not None else dimensions[2]
        if y_pos is None:
            y_pos = requested[3] if requested[3] is not None else dimensions[3]
        self._requested = (width, height, x_pos, y_pos)
        self._tk.geometry(f"{width!s}x{height!s}+{x_pos!s}+{y_pos!s}")

    def _apply_icon(self, wrapper: ImageWrapper, /) -> None:
        """Hand ``wrapper``'s handle to Tk as this window's icon.

        The handle is built for this window's own root: Tk images live
        on one interpreter, and a masterless one binds to tkinter's
        default root — the wrong one whenever a root was passed in.

        Args:
            wrapper (ImageWrapper): The already-scaled icon to draw.
        """
        self._tk.iconphoto(False, wrapper.photo_for(self._root._tk))  # type: ignore[arg-type]

    @property
    def title(self) -> str:
        """The window title."""
        return self._tk.title()

    @title.setter
    def title(self, value: str) -> None:
        self._tk.title(value)

    @property
    def width(self) -> int:
        """The current width in pixels."""
        requested = self._requested[0]
        return requested if requested is not None else self._dimensions()[0]

    @width.setter
    def width(self, value: int) -> None:
        self._set_dimensions(value, None, None, None)

    @property
    def height(self) -> int:
        """The current height in pixels."""
        requested = self._requested[1]
        return requested if requested is not None else self._dimensions()[1]

    @height.setter
    def height(self, value: int) -> None:
        self._set_dimensions(None, value, None, None)

    @property
    def x_position(self) -> int:
        """The left edge, in pixels from the screen's left."""
        requested = self._requested[2]
        return requested if requested is not None else self._dimensions()[2]

    @x_position.setter
    def x_position(self, value: int) -> None:
        self._set_dimensions(None, None, value, None)

    @property
    def y_position(self) -> int:
        """The top edge, in pixels from the screen's top."""
        requested = self._requested[3]
        return requested if requested is not None else self._dimensions()[3]

    @y_position.setter
    def y_position(self, value: int) -> None:
        self._set_dimensions(None, None, None, value)

    @property
    def min_width(self) -> int:
        """The minimum width the user may resize to, in pixels."""
        return self._tk.minsize()[0]

    @min_width.setter
    def min_width(self, value: int) -> None:
        self._tk.minsize(value, self.min_height)

    @property
    def min_height(self) -> int:
        """The minimum height the user may resize to, in pixels."""
        return self._tk.minsize()[1]

    @min_height.setter
    def min_height(self, value: int) -> None:
        self._tk.minsize(self.min_width, value)

    @property
    def max_width(self) -> int:
        """The maximum width the user may resize to, in pixels."""
        return self._tk.maxsize()[0]

    @max_width.setter
    def max_width(self, value: int) -> None:
        self._tk.maxsize(value, self.max_height)

    @property
    def max_height(self) -> int:
        """The maximum height the user may resize to, in pixels."""
        return self._tk.maxsize()[1]

    @max_height.setter
    def max_height(self, value: int) -> None:
        self._tk.maxsize(self.max_width, value)

    @property
    def resizable_width(self) -> bool:
        """Whether the user may resize the window horizontally."""
        return bool(self._tk.resizable()[0])

    @resizable_width.setter
    def resizable_width(self, value: bool) -> None:
        self._tk.resizable(value, self.resizable_height)

    @property
    def resizable_height(self) -> bool:
        """Whether the user may resize the window vertically."""
        return bool(self._tk.resizable()[1])

    @resizable_height.setter
    def resizable_height(self, value: bool) -> None:
        self._tk.resizable(self.resizable_width, value)

    @property
    def sizegrip(self) -> bool:
        """Whether a resize grip sits in the window's bottom-right corner.

        Assigning True builds one and False takes it away; assigning
        what is already true does nothing. There is no sizegrip widget
        to construct, because the only place one is any use is this
        corner of this window — the same reason no scrollbar is built
        by hand either.

        Three things about the grip are Tk's and worth knowing rather
        than discovering. It resizes **south-east only**: Tk pins the
        window's top-left while dragging, so the corner is not a choice.
        It honours :attr:`resizable_width` and :attr:`resizable_height`
        — a grip on a window fixed both ways does nothing when dragged,
        which is the window's own declaration being kept. And it is
        *placed* over the corner rather than given a cell of its own,
        so it covers whatever sits in the last 15-odd pixels instead of
        pushing it aside; a window cannot reserve that space without
        dictating the layout around it.

        Held as a reference rather than read back out of Tk: the grip
        is a component this window owns, not an option on the toplevel.
        """
        return self._sizegrip is not None

    @sizegrip.setter
    def sizegrip(self, value: bool) -> None:
        if value == (self._sizegrip is not None):
            return
        if self._sizegrip is not None:
            self._sizegrip.destroy()
            self._sizegrip = None
            return
        self._sizegrip = ttk.Sizegrip(self._tk)
        self._sizegrip.place(relx=1.0, rely=1.0, anchor="se")
        self._sizegrip.lift()

    def _raise_sizegrip(self, _event: tk.Event[tk.Misc]) -> None:
        """Put the grip back on top of anything laid out after it.

        The grip is built when the window is, so everything a caller
        lays out afterwards is a younger sibling and wins the corner.
        Configure catches the window mapping and every resize, and Map
        catches a widget appearing over the corner later, the toplevel
        being in every descendant's bindtags.
        """
        if self._sizegrip is not None:
            self._sizegrip.lift()

    @property
    def icon(self) -> ImageWrapper | None:
        """The wrapper behind the window's icon, or None when it has none.

        Assigning any :data:`~tkfacade.ImageInput` replaces it, scaled to
        fit 64x64 by :func:`~tkfacade.media.window_icon` exactly as the
        constructor's is, and retains the wrapper against garbage
        collection. There is no way to take an icon back off a window.

        What comes back is that scaled result, not the object assigned
        — unlike :attr:`~tkfacade.TreeRow.image`, which answers with its
        source.
        """
        return self._icon

    @icon.setter
    def icon(self, value: ImageInput) -> None:
        wrapper = window_icon(value)
        self._apply_icon(wrapper)
        self._icon = wrapper

    @property
    def menubar(self) -> Menubar | None:
        """This window's menu bar, or None if it was built without one.

        Read-only, and settable at construction alone. A bar holds the
        rows a caller put in it, so a setter able to take one away
        would destroy them on an assignment that reads like turning a
        switch off — where :attr:`sizegrip` toggles safely because a
        grip holds nothing.

        Held as a reference rather than read back out of Tk. The
        toplevel's own ``menu`` option is a path string Tk never
        validates: it names a destroyed widget as readily as a live
        one, and resolves against whichever interpreter asks
        (`hazards/tkinter.md`, *Menus*). The wrapper that built the bar is the
        only thing that knows which menu is actually this window's.
        """
        return self._menubar

    def destroy(self) -> None:
        """Destroy this window; the root cascade-closes with the last window.

        Idempotent in every ordering: destroying an already-destroyed
        window is a no-op, matching tkinter's own convention — which
        the last-window cascade would otherwise break, since the first
        destroy (or a titlebar close, which takes the same path) tears
        the whole interpreter down and Tk's ``destroy`` on a dead
        application raises where a live one silently ignores a gone
        window. Shutdown code racing the user's close button is the
        caller this protects.
        """
        self._root.rem_child(self)
        if self._root.destroyed:
            return
        self._tk.destroy()

    def update_idletasks(self) -> None:
        """Flush pending idle tasks (redraws, geometry), not user events."""
        self._tk.update_idletasks()

    def mainloop_running(self) -> bool:
        """Return whether the root's mainloop is in its loop right now.

        Read off the loop's own flag — a ``threading.Event`` — so any
        thread gets a live answer while the loop runs.
        """
        return self._root.mainloop_running()

    def run_mainloop(self) -> None:
        """Enter the root's mainloop unless it is already running.

        Blocks until the root is destroyed — without holding
        ``GLOBAL_LOCK``, so other threads' :func:`get_root` and
        :meth:`mainloop_running` stay answerable for the loop's whole
        life. Delegates to :meth:`Root.run_mainloop`, so its
        main-thread rule applies, and a root whose previous loop has
        exited enters again rather than being skipped.

        Raises:
            RuntimeError: If called off the main thread while the
                mainloop is not already running.
        """
        if not self.mainloop_running():
            self._root.run_mainloop()
