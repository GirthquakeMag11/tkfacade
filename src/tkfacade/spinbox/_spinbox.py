"""The spinbox wrappers: a number stepped by arrows, whole or fractional."""

import concurrent.futures
import tkinter as tk
from abc import ABC
from tkinter import ttk
from typing import TYPE_CHECKING, Any, cast

from .._command import dispatch_command
from .._types import Command, Justify
from ..events import ACTIVATED, Destroyed, Event
from ..look import Look
from ..observable import Observable, ObservableFloat, ObservableInt
from ..widget import BaseWidget, Widget


def _check_bounds(minimum: float, maximum: float, step: float, /) -> None:
    """Raise unless the range runs upward and the step can move within it.

    Raises:
        ValueError: If ``maximum`` is not above ``minimum``, or if
            ``step`` is not positive.
    """
    if maximum <= minimum:
        raise ValueError(f"maximum must be above minimum; got minimum={minimum}, maximum={maximum}")
    if step <= 0:
        raise ValueError(f"step must be positive, not {step}")


def _check_within(value: float, minimum: float, maximum: float, /) -> None:
    """Raise if ``value`` lies outside the spinbox's range.

    Raises:
        ValueError: If ``value`` is outside the range.
    """
    if not minimum <= value <= maximum:
        raise ValueError(f"the value must lie from {minimum} to {maximum}, not {value}")


class AbstractSpinbox(Widget, ABC):
    """A number the user steps through with a pair of arrows.

    The range is :attr:`minimum` to :attr:`maximum` and a step moves by
    :attr:`step`, stopping at each end or cycling past it when
    :attr:`wraps` is set. The value is an observable, the spinbox's own
    unless one is passed in, shared with whatever else watches or
    drives it.

    Unlike the scales, the bounds are named for their order and must
    be given in it. A ``ttk.Spinbox`` built from 10 down to 0 answers
    every step in either direction with 10, whatever it held first, so
    an inverted range is refused here rather than passed through as a
    widget that cannot be stepped.

    The optional command runs on user activation only — a step from
    the arrows or the keyboard — and never on a write, whether through
    the observable or through :attr:`value`. It takes a plain callable
    or a coroutine function, the latter scheduled fire-and-forget on
    the root's async core.

    **A typed value is not range-checked.** :attr:`value` refuses one
    outside the range, and so does construction, but an
    :attr:`editable` spinbox lets the user type straight into the
    widget, and that path writes the observable without passing
    through either. Tk validates none of it: a spinbox limited to 100
    accepts a typed 900 and displays it, and only a subsequent step
    snaps back into range. Building with ``editable=False`` leaves the
    arrows as the only way in, which is the configuration where the
    range genuinely holds. A typed-write guard would close the gap;
    until then ``editable=False`` is the honest configuration.

    Appearance comes from the ``TSpinbox`` style, with the same font
    exception the entry family carries.
    """

    if TYPE_CHECKING:
        _tk: ttk.Spinbox
        _observable: Observable[Any]

    __slots__ = ("_command", "_command_tasks", "_observable")

    def _build(
        self,
        parent: tk.Misc | BaseWidget,
        observable: Observable[Any],
        /,
        *,
        minimum: float,
        maximum: float,
        step: float,
        wraps: bool,
        editable: bool,
        enabled: bool,
        command: Command | None,
        width: int,
        justify: Justify,
    ) -> None:
        """Build the widget and wire the observable behind it.

        Called by the subclass once it has its observable, and before
        ``super().__init__()``, since all of this can still fail.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                spinbox is created inside.
            observable (Observable[Any]): The value the arrows move.
            minimum (float): The low end of the range.
            maximum (float): The high end; must be above ``minimum``.
            step (float): How far one step moves.
            wraps (bool): Whether a step past an end cycles round.
            editable (bool): Whether the value may be typed as well as
                stepped.
            enabled (bool): Whether the spinbox may be used at all.
            command (Command | None): Run on each step.
            width (int): Width in characters.
            justify (Justify): How the value aligns.

        The bounds are checked by the caller, before the value is,
        so that an impossible range is reported as one rather than as
        a value outside it.
        """
        master = self._as_master(parent)
        self._observable: Observable[Any] = observable
        self._command: Command | None = command
        self._command_tasks: set[concurrent.futures.Future[Any]] = set()
        self._tk = ttk.Spinbox(
            master,
            from_=minimum,
            to=maximum,
            increment=step,
            wrap=wraps,
            # cast: the observable's transport is the IntVar or DoubleVar ttk.Spinbox asks for
            textvariable=cast(tk.IntVar | tk.DoubleVar, observable.transport_for(master)),
            command=self._run_command,
            width=width,
            justify=justify,
        )
        if not editable:
            self._tk.state(["readonly"])
        if not enabled:
            self._tk.state(["disabled"])
        self._tk._observables = (observable,)  # type: ignore[attr-defined]

    def __init__(self) -> None:
        """Register the wrapper, then arrange to give back its transport."""
        super().__init__()
        self.bind(Destroyed(), self._give_back_transport)

    def _run_command(self) -> None:
        """Run the held command; None is nothing.

        Tk calls this for a step and for nothing else — not for
        ``Spinbox.set``, and not for a write through the variable —
        so the command means here what it means on the button family
        without the library having to arrange it. That is worth
        naming, because the neighbouring :class:`~tkfacade.FloatScale`
        gets the same guarantee only because the library declines to
        use the one write path that would break it.
        :data:`~tkfacade.ACTIVATED` is emitted after the command,
        command or no command, on the same user-only terms.
        """
        held = self._command
        if held is not None:
            dispatch_command(self._tk, held, self._command_tasks, f"the command of {self!r}")
        self.emit(ACTIVATED)

    def _give_back_transport(self, _event: Event) -> None:
        """Release the transport ride construction took; the widget is done.

        Bound to :class:`~tkfacade.events.Destroyed` so a shared
        observable never counts a dead widget among its riders
        (`hazards/tkinter.md`, *Variables*: a `tk.Variable` pins its
        interpreter).
        """
        self._observable.release_transport()

    @property
    def minimum(self) -> float:
        """The low end of the range; read live from Tk."""
        return float(self._tk.cget("from"))

    @property
    def maximum(self) -> float:
        """The high end of the range; read live from Tk."""
        return float(self._tk.cget("to"))

    @property
    def step(self) -> float:
        """How far one press of an arrow moves the value; read live from Tk."""
        return float(self._tk.cget("increment"))

    @property
    def wraps(self) -> bool:
        """Whether a step past an end cycles round to the other.

        False stops at the end instead, which is Tk's default and the
        behaviour a bounded quantity usually wants.
        """
        return bool(self._tk.cget("wrap"))

    @property
    def editable(self) -> bool:
        """Whether the value may be typed as well as stepped; read live from Tk.

        False leaves the arrows as the only way in, which is the
        configuration where the range genuinely holds — see the class
        body on typed values. Independent of :attr:`enabled`: a
        spinbox switched off remembers whether it was typeable, and
        says so.
        """
        return not self._tk.instate(["readonly"])

    @editable.setter
    def editable(self, value: bool) -> None:
        self._tk.state(["!readonly" if value else "readonly"])

    @property
    def enabled(self) -> bool:
        """Whether the spinbox may be used at all; read live from Tk."""
        return not self._tk.instate(["disabled"])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._tk.state(["!disabled" if value else "disabled"])

    @property
    def command(self) -> Command | None:
        """What a user's step runs; None is nothing extra.

        Assigning swaps what future steps run. Coroutine runs already
        in flight from the old command are left to finish — death
        narrows the future, never the present.
        """
        return self._command

    @command.setter
    def command(self, value: Command | None) -> None:
        self._command = value

    def step_up(self) -> None:
        """Move the value one step toward :attr:`maximum`.

        Stops at the end, or cycles to :attr:`minimum` where
        :attr:`wraps` is set. This is the same route the arrows take,
        so it runs :attr:`command` as a user's press would.
        """
        self._tk.event_generate("<<Increment>>")

    def step_down(self) -> None:
        """Move the value one step toward :attr:`minimum`.

        Stops at the end, or cycles to :attr:`maximum` where
        :attr:`wraps` is set. This is the same route the arrows take,
        so it runs :attr:`command` as a user's press would.
        """
        self._tk.event_generate("<<Decrement>>")


class FloatSpinbox(AbstractSpinbox):
    """A spinbox over a continuous range, stepping by a fractional amount.

    The value is an :class:`~tkfacade.ObservableFloat`. Where the
    quantity is counted rather than measured,
    :class:`~tkfacade.IntSpinbox` is the one to reach for.
    """

    if TYPE_CHECKING:
        _observable: ObservableFloat

    __slots__ = ()

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        minimum: float,
        maximum: float,
        value: float | ObservableFloat = 0.0,
        step: float = 1.0,
        wraps: bool = False,
        editable: bool = True,
        enabled: bool = True,
        command: Command | None = None,
        width: int = 10,
        justify: Justify = "left",
        look: Look | None = None,
    ) -> None:
        """Create the spinbox, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                spinbox is created inside.
            minimum (float): The low end of the range.
            maximum (float): The high end; must be above ``minimum``.
            value (float | ObservableFloat): The starting value, or
                the observable already holding it, shared with
                whatever else watches or drives it. Defaults to 0.0.
            step (float): How far one press of an arrow moves.
                Defaults to 1.0.
            wraps (bool): Whether a step past an end cycles round.
                Defaults to False, stopping at the end.
            editable (bool): Whether the value may be typed as well as
                stepped. Defaults to True.
            enabled (bool): Whether the spinbox may be used at all.
                Defaults to True.
            command (Command | None): Run on each user
                step — a plain callable on the mainloop, a coroutine
                function on the root's async core. Defaults to None.
            width (int): Width in characters. Defaults to 10.
            justify (Justify): How the value aligns. Defaults to
                ``"left"``.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``maximum`` is not above ``minimum``, if
                ``step`` is not positive, or if ``value`` is a plain
                number outside the range.
        """
        _check_bounds(minimum, maximum, step)
        if isinstance(value, ObservableFloat):
            held: ObservableFloat = value
        else:
            _check_within(value, minimum, maximum)
            held = ObservableFloat(value)
        self._build(
            parent,
            held,
            minimum=minimum,
            maximum=maximum,
            step=step,
            wraps=wraps,
            editable=editable,
            enabled=enabled,
            command=command,
            width=width,
            justify=justify,
        )
        super().__init__()
        if look is not None:
            self.look = look

    @property
    def value(self) -> float:
        """The number the spinbox holds.

        Assigning writes through :attr:`value_observable`, so it works
        while the widget is off and every watcher hears it; the
        command does not run, being the user's channel.

        Raises:
            ValueError: If the value lies outside the range. Tk would
                take such a write and display it, leaving the spinbox
                showing a number it will snap away from on the next
                step.
        """
        return self._observable.value

    @value.setter
    def value(self, value: float) -> None:
        _check_within(value, self.minimum, self.maximum)
        self._observable.value = value

    @property
    def value_observable(self) -> ObservableFloat:
        """The observable holding the value, for watching or sharing.

        The spinbox's own unless one was passed to the constructor.
        Every change passes through it, stepped, typed or assigned —
        and a write straight to it reaches the widget without the
        range check :attr:`value` applies.
        """
        return self._observable


class IntSpinbox(AbstractSpinbox):
    """A spinbox over whole numbers, stepping by whole amounts.

    The value is an :class:`~tkfacade.ObservableInt`, so the spinbox
    counts rather than measures — a quantity, a year, a number of
    copies. Where the quantity is continuous,
    :class:`~tkfacade.FloatSpinbox` is the one to reach for.

    A part-typed number never reaches a watcher: the transport is an
    ``IntVar``, and text it cannot read leaves the last good value
    standing, so typing ``12x`` on the way to ``123`` is not seen.
    """

    if TYPE_CHECKING:
        _observable: ObservableInt

    __slots__ = ()

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        minimum: int,
        maximum: int,
        value: int | ObservableInt = 0,
        step: int = 1,
        wraps: bool = False,
        editable: bool = True,
        enabled: bool = True,
        command: Command | None = None,
        width: int = 10,
        justify: Justify = "left",
        look: Look | None = None,
    ) -> None:
        """Create the spinbox, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                spinbox is created inside.
            minimum (int): The low end of the range.
            maximum (int): The high end; must be above ``minimum``.
            value (int | ObservableInt): The starting value, or the
                observable already holding it, shared with whatever
                else watches or drives it. Defaults to 0.
            step (int): How many whole units one press of an arrow
                moves. Defaults to 1.
            wraps (bool): Whether a step past an end cycles round.
                Defaults to False, stopping at the end.
            editable (bool): Whether the value may be typed as well as
                stepped. Defaults to True.
            enabled (bool): Whether the spinbox may be used at all.
                Defaults to True.
            command (Command | None): Run on each user
                step — a plain callable on the mainloop, a coroutine
                function on the root's async core. Defaults to None.
            width (int): Width in characters. Defaults to 10.
            justify (Justify): How the value aligns. Defaults to
                ``"left"``.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``maximum`` is not above ``minimum``, if
                ``step`` is not positive, or if ``value`` is a plain
                number outside the range.
        """
        _check_bounds(minimum, maximum, step)
        if isinstance(value, ObservableInt):
            held: ObservableInt = value
        else:
            _check_within(value, minimum, maximum)
            held = ObservableInt(value)
        self._build(
            parent,
            held,
            minimum=minimum,
            maximum=maximum,
            step=step,
            wraps=wraps,
            editable=editable,
            enabled=enabled,
            command=command,
            width=width,
            justify=justify,
        )
        super().__init__()
        if look is not None:
            self.look = look

    @property
    def minimum(self) -> int:
        """The low end of the range; read live from Tk."""
        return int(self._tk.cget("from"))

    @property
    def maximum(self) -> int:
        """The high end of the range; read live from Tk."""
        return int(self._tk.cget("to"))

    @property
    def step(self) -> int:
        """How many whole units one press of an arrow moves; read live from Tk."""
        return int(self._tk.cget("increment"))

    @property
    def value(self) -> int:
        """The whole number the spinbox holds.

        Assigning writes through :attr:`value_observable`, so it works
        while the widget is off and every watcher hears it; the
        command does not run, being the user's channel.

        Raises:
            ValueError: If the value lies outside the range.
        """
        return self._observable.value

    @value.setter
    def value(self, value: int) -> None:
        _check_within(value, self.minimum, self.maximum)
        self._observable.value = value

    @property
    def value_observable(self) -> ObservableInt:
        """The observable holding the value, for watching or sharing.

        The spinbox's own unless one was passed to the constructor.
        Every change passes through it, stepped, typed or assigned —
        and a write straight to it reaches the widget without the
        range check :attr:`value` applies.
        """
        return self._observable
