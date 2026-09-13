"""The scale wrappers: a slider over a continuous range, and one over whole steps."""

import concurrent.futures
import tkinter as tk
from abc import ABC
from tkinter import ttk
from typing import TYPE_CHECKING, Any, cast

from .._command import dispatch_command
from .._subscription import Subscription
from .._types import Arrangement, Command, Orient, PadValue
from ..events import ACTIVATED, Destroyed, Event
from ..look import Look
from ..observable import Observable, ObservableFloat, ObservableInt
from ..widget import BaseWidget, Widget

_GAP = 6
"""Pixels between the readout and the slider when they sit side by side."""


def _check_range(value: float, start: float, end: float, /) -> None:
    """Raise if ``value`` lies outside the scale's two ends.

    The ends are taken either way round, since a scale may run from
    its high value to its low one.

    Raises:
        ValueError: If ``value`` is outside the range.
    """
    low, high = (start, end) if start <= end else (end, start)
    if not low <= value <= high:
        raise ValueError(f"the value must lie from {low} to {high}, not {value}")


class AbstractScale(Widget, ABC):
    """A slider over a range, optionally showing the value it holds.

    The slider sits in a frame, and that frame is what a caller lays
    out — the readout, when there is one, is the frame's other half.
    The frame is there whether or not the readout is, so that turning
    the readout on later cannot change how the widget behaves under a
    geometry manager.

    The value is an observable, the scale's own unless one is passed
    in, shared with whatever else watches or drives it. Driving it
    moves the slider; dragging the slider writes it. The range is
    enforced by the ``value`` setter, so a caller driving a shared
    observable directly reaches the widget without passing that
    check — and a value past either end leaves the slider at the end
    of its track, since Tk neither clamps such a write nor refuses
    it.

    The optional command runs on user activation only — a drag or a
    keypress — and never on a write through the observable, which is
    the distinction a watcher cannot make. It takes a plain callable
    or a coroutine function, the latter scheduled fire-and-forget on
    the root's async core.

    Appearance comes from the ``Horizontal.TScale`` or
    ``Vertical.TScale`` style, by the orientation the scale was built
    with, rather than from per-widget options.
    """

    if TYPE_CHECKING:
        _tk: ttk.Frame
        _observable: Observable[Any]

    __slots__ = (
        "_arrangement",
        "_command",
        "_command_tasks",
        "_observable",
        "_readout",
        "_scale",
        "_value_format",
        "_watch",
    )

    def _look_targets(self) -> tuple[tk.Misc, ...]:
        """The slider and its readout label: both halves of the frame dress."""
        return (self._scale, self._readout)

    def __init__(self) -> None:
        """Register the wrapper, route its parts, and arrange to give it all back."""
        super().__init__()
        self._route_events(self._scale, self._readout)
        self.bind(Destroyed(), self._release)

    def _build(
        self,
        parent: tk.Misc | BaseWidget,
        observable: Observable[Any],
        /,
        *,
        start: float,
        end: float,
        orient: Orient,
        length: PadValue | None,
        command: Command | None,
        enabled: bool,
        show_value: bool,
        arrangement: Arrangement,
        value_format: str,
    ) -> None:
        """Build the frame, the slider, and the readout beside it.

        Called by the subclass once it has its observable, and before
        ``super().__init__()``, since all of this can still fail.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                scale is created inside.
            observable (Observable[Any]): The value the slider carries.
            start (float): The value at the slider's low end.
            end (float): The value at its high end; may be below
                ``start`` for a scale that runs the other way.
            orient (Orient): The axis the slider lies along.
            length (PadValue | None): The slider's length in pixels,
                or None for Tk's own.
            command (Command | None): Run on each user
                change.
            enabled (bool): Whether the slider starts movable.
            show_value (bool): Whether the readout is shown.
            arrangement (Arrangement): Where the readout sits against
                the slider.
            value_format (str): A format string the value is rendered
                through.
        """
        master = self._as_master(parent)
        self._observable: Observable[Any] = observable
        self._value_format: str = value_format
        self._command: Command | None = command
        self._command_tasks: set[concurrent.futures.Future[Any]] = set()
        self._tk = ttk.Frame(master)
        self._scale = ttk.Scale(
            self._tk,
            orient=orient,
            from_=start,
            to=end,
            # cast: the observable's transport is the IntVar or DoubleVar ttk.Scale asks for
            variable=cast(tk.IntVar | tk.DoubleVar, observable.transport_for(master)),
            command=self._run_command,
            state="normal" if enabled else "disabled",
        )
        if length is not None:
            self._scale.configure(length=length)
        self._readout = ttk.Label(self._tk, text=self._rendered())
        self._tk._observables = (observable,)  # type: ignore[attr-defined]
        self._watch: Subscription = observable.watch(lambda _value: self._refresh())
        self._arrange(arrangement)
        if not show_value:
            self._readout.grid_remove()

    def _rendered(self) -> str:
        """The value as the readout shows it."""
        return self._value_format.format(self._observable.value)

    def _refresh(self) -> None:
        """Put the current value back on the readout."""
        self._readout.configure(text=self._rendered())

    def _run_command(self, _position: str) -> None:
        """Run the held command; None is nothing.

        Tk hands this the slider's new position as a string, which no
        caller sees: a scale's command takes no argument, as the rest
        of the family's do, and the value is on the observable. Tk
        calls it for a user's drag and for ``Scale.set``, never for a
        write through the variable — and the variable is the only
        route this library drives, so the command stays the user's
        channel. :data:`~tkfacade.ACTIVATED` is emitted after the
        command, command or no command, on the same user-only terms.
        """
        held = self._command
        if held is not None:
            dispatch_command(self._tk, held, self._command_tasks, f"the command of {self!r}")
        self.emit(ACTIVATED)

    def _arrange(self, arrangement: Arrangement, /) -> None:
        """Grid the readout and the slider as ``arrangement`` names them.

        Writes the whole layout rather than the part that changed:
        ``grid`` merges into what is already in place, so the cell, the
        weight, and the gap a previous arrangement left behind are all
        cleared by being written over.

        Args:
            arrangement (Arrangement): Which side of the slider the
                readout sits on, named as ``"<readout>-<slider>"``.
        """
        self._arrangement = arrangement
        readout_first = arrangement in ("top-bottom", "left-right")
        readout_index, scale_index = (0, 1) if readout_first else (1, 0)
        if arrangement in ("left-right", "right-left"):
            gap = (0, _GAP) if readout_first else (_GAP, 0)
            self._readout.grid(row=0, column=readout_index, sticky="ew", padx=gap)
            self._scale.grid(row=0, column=scale_index, sticky="ew")
            scale_column = scale_index
        else:
            self._readout.grid(row=readout_index, column=0, sticky="ew", padx=0)
            self._scale.grid(row=scale_index, column=0, sticky="ew")
            scale_column = 0
        self._tk.grid_columnconfigure(scale_column, weight=1)
        self._tk.grid_columnconfigure(1 - scale_column, weight=0)

    def _release(self, _event: Event) -> None:
        """Give back the transport ride and stop watching; the widget is done.

        Bound to :class:`~tkfacade.events.Destroyed`. The watch is
        cancelled as well as the ride: a shared observable outlives
        this widget, and a readout update on a destroyed label would
        raise from inside a watcher.
        """
        self._watch.cancel()
        self._observable.release_transport()

    @property
    def start(self) -> float:
        """The value at the slider's low end; read live from Tk."""
        return float(self._scale.cget("from"))

    @start.setter
    def start(self, value: float) -> None:
        self._scale.configure(from_=value)

    @property
    def end(self) -> float:
        """The value at the slider's high end; read live from Tk.

        May sit below :attr:`start`, which runs the scale the other
        way — the high end at the left, or at the top.
        """
        return float(self._scale.cget("to"))

    @end.setter
    def end(self, value: float) -> None:
        self._scale.configure(to=value)

    @property
    def command(self) -> Command | None:
        """What a user's change runs; None is nothing extra.

        Assigning swaps what future changes run. Coroutine runs
        already in flight from the old command are left to finish —
        death narrows the future, never the present.
        """
        return self._command

    @command.setter
    def command(self, value: Command | None) -> None:
        self._command = value

    @property
    def enabled(self) -> bool:
        """Whether the slider can be moved by the user; read live from Tk."""
        return not self._scale.instate(["disabled"])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._scale.state(["!disabled" if value else "disabled"])

    @property
    def show_value(self) -> bool:
        """Whether the readout is shown beside the slider."""
        return bool(self._readout.winfo_manager())

    @show_value.setter
    def show_value(self, value: bool) -> None:
        if value == self.show_value:
            return
        if value:
            self._readout.grid()
            self._arrange(self._arrangement)
        else:
            self._readout.grid_remove()

    @property
    def arrangement(self) -> Arrangement:
        """Which side of the slider the readout sits on, as ``"<readout>-<slider>"``.

        Assigning re-places both inside the frame; nothing else about
        either changes, so the value and the slider's state survive
        the move. Held as a stored member so it answers without
        consulting Tk when the readout is hidden — an unmanaged widget
        has no grid info to read.
        """
        if not self.show_value:
            return self._arrangement
        scale_info = self._scale.grid_info()
        readout_info = self._readout.grid_info()
        if int(scale_info["row"]) != int(readout_info["row"]):
            return "top-bottom" if int(readout_info["row"]) == 0 else "bottom-top"
        return "left-right" if int(readout_info["column"]) == 0 else "right-left"

    @arrangement.setter
    def arrangement(self, value: Arrangement) -> None:
        self._arrangement = value
        if self.show_value:
            self._arrange(value)

    @property
    def value_format(self) -> str:
        """The format string the readout renders the value through."""
        return self._value_format

    @value_format.setter
    def value_format(self, value: str) -> None:
        self._value_format = value
        self._refresh()


class FloatScale(AbstractScale):
    """A slider over a continuous range, holding whatever value it lands on.

    The value is a :class:`~tkfacade.ObservableFloat`, and every
    position between :attr:`start` and :attr:`end` is one it can hold.
    Where only whole steps are wanted, :class:`IntScale` is the one to
    reach for.
    """

    if TYPE_CHECKING:
        _observable: ObservableFloat

    __slots__ = ()

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        start: float,
        end: float,
        value: float | ObservableFloat = 0.0,
        orient: Orient = "horizontal",
        length: PadValue | None = None,
        command: Command | None = None,
        enabled: bool = True,
        show_value: bool = False,
        arrangement: Arrangement = "top-bottom",
        value_format: str = "{:.2f}",
        look: Look | None = None,
    ) -> None:
        """Create the scale, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                scale is created inside.
            start (float): The value at the slider's low end.
            end (float): The value at its high end; may be below
                ``start`` for a scale that runs the other way.
            value (float | ObservableFloat): The starting value, or the
                observable already holding it, shared with whatever
                else watches or drives it. Defaults to 0.0, a scale
                with an observable of its own.
            orient (Orient): The axis the slider lies along. Defaults
                to ``"horizontal"``.
            length (PadValue | None): The slider's length in pixels.
                Defaults to None, meaning Tk's own.
            command (Command | None): Run on each user
                change — a plain callable on the mainloop, a coroutine
                function on the root's async core. Defaults to None.
            enabled (bool): Whether the slider starts movable.
                Defaults to True.
            show_value (bool): Whether a readout of the value sits
                beside the slider. Defaults to False.
            arrangement (Arrangement): Where that readout sits.
                Defaults to ``"top-bottom"``, above the slider.
            value_format (str): How the readout renders the value.
                Defaults to ``"{:.2f}"``.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``value`` is a plain number outside the
                scale's two ends.
        """
        if isinstance(value, ObservableFloat):
            held = value
        else:
            _check_range(value, start, end)
            held = ObservableFloat(value)
        self._build(
            parent,
            held,
            start=start,
            end=end,
            orient=orient,
            length=length,
            command=command,
            enabled=enabled,
            show_value=show_value,
            arrangement=arrangement,
            value_format=value_format,
        )
        super().__init__()
        if look is not None:
            self.look = look

    @property
    def value(self) -> float:
        """Where the slider sits.

        Assigning moves it, and works while disabled: the write goes
        through :attr:`value_observable`, which Tk honours while it
        ignores the mouse.

        Raises:
            ValueError: If the value lies outside the scale's two
                ends. Tk itself would take such a write and leave the
                slider stranded at the end of its track, so it is
                refused here — the same check, and the same
                observable-route escape from it, that the progress
                bars carry.
        """
        return self._observable.value

    @value.setter
    def value(self, value: float) -> None:
        _check_range(value, self.start, self.end)
        self._observable.value = value

    @property
    def value_observable(self) -> ObservableFloat:
        """The observable holding the value, for watching or sharing.

        The scale's own unless one was passed to the constructor.
        Every change passes through it, dragged or assigned, so a
        watcher on it sees both.
        """
        return self._observable


class IntScale(AbstractScale):
    """A slider over whole steps, holding one of them at a time.

    The value is an :class:`~tkfacade.ObservableInt`, so the scale
    counts steps rather than measuring a quantity — volume levels, a
    number of copies, a rating out of five.

    The handle itself is not stepped, only the value: Tk's themed
    scale has no setting that makes the slider land on whole numbers,
    and the only way to force it fires the widget's command as though
    a user had acted. So the slider may rest between two steps while
    the value reads the nearer one. A whole-number-landing mode is a
    known gap rather than a present feature.
    """

    if TYPE_CHECKING:
        _observable: ObservableInt

    __slots__ = ()

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        start: int,
        end: int,
        value: int | ObservableInt = 0,
        orient: Orient = "horizontal",
        length: PadValue | None = None,
        command: Command | None = None,
        enabled: bool = True,
        show_value: bool = False,
        arrangement: Arrangement = "top-bottom",
        value_format: str = "{}",
        look: Look | None = None,
    ) -> None:
        """Create the scale, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                scale is created inside.
            start (int): The step at the slider's low end.
            end (int): The step at its high end; may be below
                ``start`` for a scale that runs the other way.
            value (int | ObservableInt): The starting step, or the
                observable already holding it, shared with whatever
                else watches or drives it. Defaults to 0, a scale with
                an observable of its own.
            orient (Orient): The axis the slider lies along. Defaults
                to ``"horizontal"``.
            length (PadValue | None): The slider's length in pixels.
                Defaults to None, meaning Tk's own.
            command (Command | None): Run on each user
                change — a plain callable on the mainloop, a coroutine
                function on the root's async core. Defaults to None.
            enabled (bool): Whether the slider starts movable.
                Defaults to True.
            show_value (bool): Whether a readout of the value sits
                beside the slider. Defaults to False.
            arrangement (Arrangement): Where that readout sits.
                Defaults to ``"top-bottom"``, above the slider.
            value_format (str): How the readout renders the value.
                Defaults to ``"{}"``.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``value`` is a plain number outside the
                scale's two ends.
        """
        if isinstance(value, ObservableInt):
            held = value
        else:
            _check_range(value, start, end)
            held = ObservableInt(value)
        self._build(
            parent,
            held,
            start=start,
            end=end,
            orient=orient,
            length=length,
            command=command,
            enabled=enabled,
            show_value=show_value,
            arrangement=arrangement,
            value_format=value_format,
        )
        super().__init__()
        if look is not None:
            self.look = look

    @property
    def start(self) -> int:
        """The step at the slider's low end; read live from Tk."""
        return int(self._scale.cget("from"))

    @start.setter
    def start(self, value: float) -> None:
        self._scale.configure(from_=value)

    @property
    def end(self) -> int:
        """The step at the slider's high end; read live from Tk.

        May sit below :attr:`start`, which runs the scale the other
        way — the high step at the left, or at the top.
        """
        return int(self._scale.cget("to"))

    @end.setter
    def end(self, value: float) -> None:
        self._scale.configure(to=value)

    @property
    def value(self) -> int:
        """Which step the slider sits on.

        Assigning moves it, and works while disabled: the write goes
        through :attr:`value_observable`, which Tk honours while it
        ignores the mouse.

        Raises:
            ValueError: If the value lies outside the scale's two
                ends. Tk itself would take such a write and leave the
                slider stranded at the end of its track, so it is
                refused here — the same check, and the same
                observable-route escape from it, that the progress
                bars carry.
        """
        return self._observable.value

    @value.setter
    def value(self, value: int) -> None:
        _check_range(value, self.start, self.end)
        self._observable.value = value

    @property
    def value_observable(self) -> ObservableInt:
        """The observable holding the step, for watching or sharing.

        The scale's own unless one was passed to the constructor.
        Every change passes through it, dragged or assigned, so a
        watcher on it sees both.
        """
        return self._observable
