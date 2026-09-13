"""The scrollable contract: navigating a widget's content in four directions."""

import tkinter as tk
from abc import ABC
from functools import partial
from tkinter import ttk
from typing import Any, Final, Protocol, cast

from .._types import Orient, ScrollUnit, Side
from ..widget import Widget
from ._spec import ScrollbarSpec

_TK_UNITS: dict[ScrollUnit, str] = {"steps": "units", "pages": "pages"}
"""The library's movement units, in the words Tk's ``scroll`` verb takes."""

_AXIS_SIDES: Final[dict[Orient, tuple[Side, ...]]] = {
    "vertical": ("left", "right"),
    "horizontal": ("top", "bottom"),
}
"""The sides each axis's bar can sit at; anything else is refused."""

_DEFAULT_SIDES: Final[dict[Orient, Side]] = {"vertical": "right", "horizontal": "bottom"}
"""Where a bar sits when nothing says otherwise: Tk's own convention."""


class ScrollTarget(Protocol):
    """What the gutter machinery needs of the widget it scrolls.

    Structural rather than nominal because Tk's scrollable widgets
    share no base that declares any of it: :class:`tkinter.Text`,
    :class:`tkinter.Listbox`, :class:`ttk.Treeview` and
    :class:`tkinter.Canvas` all answer these, and
    :class:`tkinter.Misc` — which is all their common ancestry amounts
    to — declares none of them.
    """

    def yview(self, *args: Any) -> Any:
        """Query or move the up-and-down view."""

    def xview(self, *args: Any) -> Any:
        """Query or move the side-to-side view."""

    def grid(self, **options: Any) -> Any:
        """Place the widget in its master's grid."""

    def configure(self, **options: Any) -> Any:
        """Set widget options, the scroll-command pair among them."""


class AbstractScrollable(Widget, ABC):
    """A widget whose content is navigated, with the scrollbars it owns.

    The frame is what a caller lays out; the content sits in it, and
    any scrollbars sit in the gutter cells beside and below — or
    before and above, since each bar's :attr:`~Scrollbar.placement` is
    the caller's. What a caller does with the content is **navigate**
    — :meth:`scroll_up` and its three siblings for relative movement,
    :meth:`scroll_to` for an absolute one, :attr:`x_offset` and
    :attr:`y_offset` for where the content sits now, and
    :attr:`can_scroll_up` and its siblings for whether there is
    anywhere left to go.

    The bars themselves are wired here — the axis a scrollbar has to
    agree about with its widget in three separate places is named once,
    so the handshake tkinter asks for cannot be got wrong — and answer
    as component facades: a caller says whether a bar exists at
    construction, says what kind with a
    :class:`~tkfacade.ScrollbarSpec`, and reaches the live bar
    afterwards as :attr:`vertical_scrollbar` or
    :attr:`horizontal_scrollbar`. The spec is the construction door
    and the facet the live one, the way a tree's column specs sit
    beside its live column views.

    Navigation works whether or not a bar exists: a widget built with
    none still scrolls, still reports its offsets, and still says
    where it can go.
    """

    __slots__ = ("_scroll_auto_hide", "_scroll_bars", "_scroll_sides", "_scroll_target")

    def _look_targets(self) -> tuple[tk.Misc, ...]:
        """The scrolled content and the bars: the whole facade unit dresses.

        The content is dressed when its kind is themed (a tree's
        treeview) and skipped when classic (a text box's text widget,
        which the class body documents); the gutter bars are themed
        either way, so a look reaches them on every scrollable.
        """
        return (self._scroll_target, *self._scroll_bars.values())

    def _build_gutters(
        self,
        target: tk.Misc,
        /,
        *,
        vertical: bool | ScrollbarSpec,
        horizontal: bool | ScrollbarSpec,
    ) -> None:
        """Lay ``target`` out in the frame and build the bars it owns.

        Called by the subclass once it has built the widget that
        scrolls, and before ``super().__init__()``, since the bars are
        part of the construction that can still fail.

        Args:
            target (tk.Misc): The widget whose content scrolls,
                already created inside this wrapper's frame.
            vertical (bool | ScrollbarSpec): Whether a vertical bar
                sits in the right gutter, or the spec declaring one.
            horizontal (bool | ScrollbarSpec): Whether a horizontal
                bar sits in the bottom gutter, or the spec declaring
                one.
        """
        self._scroll_target: tk.Misc = target
        self._scroll_bars: dict[Orient, ttk.Scrollbar] = {}
        self._scroll_auto_hide: set[Orient] = set()
        self._scroll_sides: dict[Orient, Side] = dict(_DEFAULT_SIDES)
        scrollable = cast(ScrollTarget, target)
        options: dict[Orient, str] = {
            "vertical": "yscrollcommand",
            "horizontal": "xscrollcommand",
        }
        for axis, asked in (("vertical", vertical), ("horizontal", horizontal)):
            if asked is False:
                continue
            axis = cast(Orient, axis)
            bar = ttk.Scrollbar(self._tk, orient=axis, command=partial(self._scroll_command, axis))
            self._scroll_bars[axis] = bar
            scrollable.configure(**{options[axis]: partial(self._scroll_report, axis)})
        self._layout_gutters()
        for axis, asked in (("vertical", vertical), ("horizontal", horizontal)):
            if isinstance(asked, ScrollbarSpec):
                asked.visit(self, cast(Orient, axis))

    def _layout_gutters(self) -> None:
        """Grid the content and every bar from the held sides, whole.

        Written entire rather than by the part that changed: ``grid``
        merges into what is already in place, so the cells and weights
        a previous placement used are cleared by being written over.
        An auto-hidden bar is re-seated and re-hidden, so its
        remembered cell moves with the layout while it stays off
        screen.
        """
        content_row = 1 if self._scroll_sides["horizontal"] == "top" else 0
        content_column = 1 if self._scroll_sides["vertical"] == "left" else 0
        cast(ScrollTarget, self._scroll_target).grid(
            row=content_row, column=content_column, sticky="nsew"
        )
        cells: dict[Orient, dict[str, Any]] = {
            "vertical": {
                "row": content_row,
                "column": 0 if self._scroll_sides["vertical"] == "left" else content_column + 1,
                "sticky": "ns",
            },
            "horizontal": {
                "row": 0 if self._scroll_sides["horizontal"] == "top" else content_row + 1,
                "column": content_column,
                "sticky": "ew",
            },
        }
        for axis, bar in self._scroll_bars.items():
            hidden = axis in self._scroll_auto_hide and not bar.winfo_manager()
            bar.grid(**cells[axis])
            if hidden:
                bar.grid_remove()
        for index in (0, 1):
            self._tk.rowconfigure(index, weight=1 if index == content_row else 0)
            self._tk.columnconfigure(index, weight=1 if index == content_column else 0)

    def _set_bar_side(self, axis: Orient, side: Side, /) -> None:
        """Put ``axis``'s bar at ``side``, re-laying the gutters out whole.

        The one path placement takes, whichever door asked — the
        spec's ``visit`` at construction or the facet's setter after.

        Raises:
            ValueError: If ``side`` is not on ``axis`` — a vertical
                bar sits left or right, a horizontal one top or
                bottom. Tk would grid it anywhere and draw nonsense.
        """
        if side not in _AXIS_SIDES[axis]:
            raise ValueError(f"a {axis} scrollbar sits at one of {_AXIS_SIDES[axis]}, not {side!r}")
        self._scroll_sides[axis] = side
        self._layout_gutters()

    @property
    def vertical_scrollbar(self) -> Scrollbar | None:
        """The vertical bar's live view, or None while none was asked for.

        A bar exists by the constructor's word alone; this is where an
        existing one is reached afterwards.
        """
        return Scrollbar(self, "vertical") if "vertical" in self._scroll_bars else None

    @property
    def horizontal_scrollbar(self) -> Scrollbar | None:
        """The horizontal bar's live view, or None while none was asked for."""
        return Scrollbar(self, "horizontal") if "horizontal" in self._scroll_bars else None

    def _scroll_call(self, axis: Orient, /, *args: object) -> tuple[float, ...]:
        """Reach Tk's view verb for ``axis``, with ``args`` as its arguments.

        Called with none it is the query form, answering the
        ``(first, last)`` pair as floats — tkinter converts that
        direction itself, unlike the callback direction, which arrives
        as strings (`hazards/tkinter.md`, *Scrolling*).
        """
        # cast per the construction invariant, as in _build_gutters
        target = cast(ScrollTarget, self._scroll_target)
        verb = target.yview if axis == "vertical" else target.xview
        return tuple(verb(*args) or ())

    def _scroll_command(self, axis: Orient, /, *args: str) -> None:
        """Move ``axis`` the way a bar just asked, in Tk's own words.

        The one place the drive end's strings are not converted: they
        arrive from Tk and go straight back to Tk without passing a
        facade surface, so there is nobody to convert them for. The
        library's own vocabulary for the same movement is
        :meth:`scroll_up` and its siblings.
        """
        self._scroll_call(axis, *args)

    def _scroll_report(self, axis: Orient, first: str, last: str, /) -> None:
        """Take Tk's report for ``axis`` to the bar, and honour auto-hide.

        Both fractions arrive as strings, Tk's own numbers included
        (`hazards/tkinter.md`, *Scrolling*); they are converted once, here.
        """
        bar = self._scroll_bars.get(axis)
        if bar is None:
            return
        span = (float(first), float(last))
        bar.set(*span)
        if axis in self._scroll_auto_hide:
            self._set_bar_shown(axis, span[1] - span[0] < 1.0)

    def _set_bar_shown(self, axis: Orient, showing: bool, /) -> None:
        """Put ``axis``'s bar in its cell or take it out, leaving the cell intact.

        ``grid_remove`` and a bare ``grid`` keep row, column and
        sticky, so hiding needs no remembered geometry (`hazards/tkinter.md`,
        *Scrolling*).
        """
        bar = self._scroll_bars.get(axis)
        if bar is None or bool(bar.winfo_manager()) == showing:
            return
        if showing:
            bar.grid()
        else:
            bar.grid_remove()

    def _set_auto_hide(self, axis: Orient, value: bool, /) -> None:
        """Mark ``axis``'s bar as hiding itself when idle, and apply it now."""
        if value:
            self._scroll_auto_hide.add(axis)
        else:
            self._scroll_auto_hide.discard(axis)
        self._set_bar_shown(axis, self._can_scroll(axis) if value else True)

    def _can_scroll(self, axis: Orient, /) -> bool:
        """Whether ``axis`` has anything to scroll; False when it all fits."""
        first, last = self._scroll_call(axis)
        return last - first < 1.0

    @property
    def x_offset(self) -> float:
        """How far the content has scrolled sideways, as a fraction of its width.

        0.0 at the left edge; the maximum is wherever the last
        screenful begins, which is below 1.0 by however much is
        visible. Read live from Tk, and read-only:
        :meth:`scroll_to` is where an offset is written.
        """
        return self._scroll_call("horizontal")[0]

    @property
    def y_offset(self) -> float:
        """How far the content has scrolled down, as a fraction of its height.

        0.0 at the top; the maximum is wherever the last screenful
        begins, which is below 1.0 by however much is visible. Read
        live from Tk, and read-only: :meth:`scroll_to` is where an
        offset is written.
        """
        return self._scroll_call("vertical")[0]

    @property
    def can_scroll_up(self) -> bool:
        """Whether there is content above what is on screen."""
        return self._scroll_call("vertical")[0] > 0.0

    @property
    def can_scroll_down(self) -> bool:
        """Whether there is content below what is on screen."""
        return self._scroll_call("vertical")[1] < 1.0

    @property
    def can_scroll_left(self) -> bool:
        """Whether there is content to the left of what is on screen."""
        return self._scroll_call("horizontal")[0] > 0.0

    @property
    def can_scroll_right(self) -> bool:
        """Whether there is content to the right of what is on screen."""
        return self._scroll_call("horizontal")[1] < 1.0

    def scroll_up(self, amount: int = 1, /, *, unit: ScrollUnit = "steps") -> None:
        """Move the content ``amount`` units toward its start; stops at the top.

        Args:
            amount (int): How far to move. Defaults to 1.
            unit (ScrollUnit): What one unit counts — the widget's own
                smallest movement, or a screenful. Defaults to
                ``"steps"``.

        Raises:
            ValueError: If ``amount`` is negative. The four directions
                exist so that nobody has to reason about signs.
        """
        self._scroll_by("vertical", -_checked(amount), unit)

    def scroll_down(self, amount: int = 1, /, *, unit: ScrollUnit = "steps") -> None:
        """Move the content ``amount`` units toward its end; stops at the bottom.

        Args:
            amount (int): How far to move. Defaults to 1.
            unit (ScrollUnit): What one unit counts. Defaults to
                ``"steps"``.

        Raises:
            ValueError: If ``amount`` is negative.
        """
        self._scroll_by("vertical", _checked(amount), unit)

    def scroll_left(self, amount: int = 1, /, *, unit: ScrollUnit = "steps") -> None:
        """Move the content ``amount`` units toward its start; stops at the left.

        Args:
            amount (int): How far to move. Defaults to 1.
            unit (ScrollUnit): What one unit counts. Defaults to
                ``"steps"``.

        Raises:
            ValueError: If ``amount`` is negative.
        """
        self._scroll_by("horizontal", -_checked(amount), unit)

    def scroll_right(self, amount: int = 1, /, *, unit: ScrollUnit = "steps") -> None:
        """Move the content ``amount`` units toward its end; stops at the right.

        Args:
            amount (int): How far to move. Defaults to 1.
            unit (ScrollUnit): What one unit counts. Defaults to
                ``"steps"``.

        Raises:
            ValueError: If ``amount`` is negative.
        """
        self._scroll_by("horizontal", _checked(amount), unit)

    def scroll_to(self, *, x: float | None = None, y: float | None = None) -> None:
        """Put the content at the given fractions of its width and height.

        An axis left out is left alone, so one call moves either or
        both. A fraction the widget cannot reach settles where it can:
        Tk clamps to the last screenful, and lands on whatever
        boundary the content has — a whole line in a text box, a whole
        row in a tree — so reading an offset back rarely answers with
        exactly what was asked for.

        Args:
            x (float | None): Where to put the left edge, from 0.0 to
                1.0. Defaults to None, leaving it where it is.
            y (float | None): Where to put the top edge, from 0.0 to
                1.0. Defaults to None, leaving it where it is.

        Raises:
            ValueError: If either fraction is outside 0.0 to 1.0.
                Tk would take it and clamp silently.
        """
        for axis, fraction in (("horizontal", x), ("vertical", y)):
            if fraction is None:
                continue
            if not 0.0 <= fraction <= 1.0:
                raise ValueError(f"{fraction!r} is not a fraction between 0.0 and 1.0")
            self._scroll_call(cast(Orient, axis), "moveto", fraction)

    def _scroll_by(self, axis: Orient, amount: int, unit: ScrollUnit, /) -> None:
        """Move ``axis`` by a signed ``amount`` of ``unit``."""
        self._scroll_call(axis, "scroll", amount, _TK_UNITS[unit])


class Scrollbar:
    """A live view of one axis's bar on the scrollable that owns it.

    Never built by a caller — a scrollable answers one from
    :attr:`~AbstractScrollable.vertical_scrollbar` or
    :attr:`~AbstractScrollable.horizontal_scrollbar` for each bar its
    constructor was asked for. The view is the bar's afterwards: what
    a :class:`~tkfacade.ScrollbarSpec` says at construction, this says
    live. The bar's own six Tk options stay unoffered — the facet
    names the relationship, not the widget behind it.
    """

    __slots__ = ("_axis", "_widget")

    def __init__(self, widget: AbstractScrollable, axis: Orient, /) -> None:
        """Capture the scrollable and the axis this views.

        Args:
            widget (AbstractScrollable): The scrollable owning the bar.
            axis (Orient): Which of its bars this views.
        """
        self._widget = widget
        self._axis = axis

    @property
    def placement(self) -> Side:
        """The side of the content the bar sits at.

        Assigning re-lays the gutters out; a vertical bar sits left or
        right, a horizontal one top or bottom.

        Raises:
            ValueError: If the side is not on this bar's axis.
        """
        return self._widget._scroll_sides[self._axis]

    @placement.setter
    def placement(self, value: Side) -> None:
        self._widget._set_bar_side(self._axis, value)

    @property
    def auto_hide(self) -> bool:
        """Whether the bar leaves the layout while its axis has nothing to scroll.

        Assigning applies immediately, as the spec's field does at
        construction.
        """
        return self._axis in self._widget._scroll_auto_hide

    @auto_hide.setter
    def auto_hide(self, value: bool) -> None:
        self._widget._set_auto_hide(self._axis, value)

    @property
    def shown(self) -> bool:
        """Whether the bar currently occupies its cell; auto-hide's visible face."""
        return bool(self._widget._scroll_bars[self._axis].winfo_manager())


def _checked(amount: int, /) -> int:
    """Return ``amount``, or raise if it is negative.

    Raises:
        ValueError: If ``amount`` is negative.
    """
    if amount < 0:
        raise ValueError(f"a scroll amount is not negative; got {amount!r}")
    return amount
