"""Event specifications: the bindable occurrences, as values.

Each specification is an immutable, hashable value a decorator can
store before any widget exists, built from this package's own
vocabulary and answering with the Tk sequence it binds as. The set
covers the ruled common vocabulary — presses and releases of keys and
mouse buttons, motion, the wheel, crossing, focus, destruction, and
virtual events including user-defined ones — and a new kind is an
addition, never a change to these.

A specification describes one hardware occurrence, memorylessly: the
delivered fact Tk can guarantee. Anything that needs the input
device's *state* — what else is held right now, what was pressed just
before, how many times in a row — is a judgment across occurrences,
and belongs to the keyboard-and-mouse observer.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Final

from ._enums import Key, MouseButton, VirtualEvent


def _validate(input: Key | MouseButton | str) -> None:
    """Refuse an input whose spelling cannot mean anything to Tk.

    Raises:
        ValueError: If a non-button input is not a keysym spelling.
    """
    if isinstance(input, MouseButton):
        return
    keysym = str(input)
    if not keysym or any(part in keysym for part in ("<", ">", " ")):
        raise ValueError(f"not a keysym: {keysym!r}")


def _sequence(input: Key | MouseButton | str, *, release: bool) -> str:
    """Spell one press or release occurrence as its Tk sequence."""
    if isinstance(input, MouseButton):
        return f"<{'ButtonRelease' if release else 'Button'}-{int(input)}>"
    return f"<{'KeyRelease' if release else 'KeyPress'}-{input}>"


class EventSpec(ABC):
    """What every event specification answers: the sequence it binds as.

    Specifications are values — immutable, hashable, comparable by
    content — so they can be stored at class-definition time, long
    before any widget exists, and used as registry keys.
    """

    __slots__ = ()

    @property
    @abstractmethod
    def sequence(self) -> str:
        """The Tk binding sequence this specification stands for."""

    @property
    def at_pointer(self) -> bool:
        """Whether the occurrence happens at the pointer's position.

        Position facts ride only such occurrences: Tk stuffs the
        pointer's idle position into every packet, keystrokes
        included, and the dispatch drops it wherever this answers
        False — where the pointer idled during an occurrence is device
        state, not a fact of the occurrence.
        """
        return False


@dataclass(frozen=True, slots=True)
class Press(EventSpec):
    """One input going down: the key or mouse button was just pressed.

    Args:
        input (Key | MouseButton | str): The input, as a :class:`Key`
            or :class:`MouseButton` member, or Tk's own spelling for a
            keysym the enum does not carry.
    """

    input: Key | MouseButton | str

    def __post_init__(self) -> None:
        _validate(self.input)

    @property
    def sequence(self) -> str:
        return _sequence(self.input, release=False)

    @property
    def at_pointer(self) -> bool:
        return isinstance(self.input, MouseButton)


@dataclass(frozen=True, slots=True)
class Release(EventSpec):
    """One input coming back up: the key or mouse button was just released.

    Args:
        input (Key | MouseButton | str): The input, as a :class:`Key`
            or :class:`MouseButton` member, or Tk's own spelling for a
            keysym the enum does not carry.
    """

    input: Key | MouseButton | str

    def __post_init__(self) -> None:
        _validate(self.input)

    @property
    def sequence(self) -> str:
        return _sequence(self.input, release=True)

    @property
    def at_pointer(self) -> bool:
        return isinstance(self.input, MouseButton)


@dataclass(frozen=True, slots=True)
class Motion(EventSpec):
    """Pointer motion over the widget.

    Fires whatever is held at the time; telling a drag from a plain
    move is a state judgment, and the input-state layer's to make.
    """

    @property
    def sequence(self) -> str:
        return "<Motion>"

    @property
    def at_pointer(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class Wheel(EventSpec):
    """The mouse wheel, as Windows and macOS deliver it.

    X11 delivers wheel motion as buttons 4 and 5 instead
    (``Press(MouseButton.WHEEL_UP_X11)`` and its twin); portable code
    binds both routes.
    """

    @property
    def sequence(self) -> str:
        return "<MouseWheel>"

    @property
    def at_pointer(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class PointerEnter(EventSpec):
    """The pointer entering the widget."""

    @property
    def sequence(self) -> str:
        return "<Enter>"

    @property
    def at_pointer(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class PointerLeave(EventSpec):
    """The pointer leaving the widget."""

    @property
    def sequence(self) -> str:
        return "<Leave>"

    @property
    def at_pointer(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class FocusGained(EventSpec):
    """Keyboard focus arriving at the widget."""

    @property
    def sequence(self) -> str:
        return "<FocusIn>"


@dataclass(frozen=True, slots=True)
class FocusLost(EventSpec):
    """Keyboard focus leaving the widget."""

    @property
    def sequence(self) -> str:
        return "<FocusOut>"


@dataclass(frozen=True, slots=True)
class Destroyed(EventSpec):
    """The widget's destruction.

    Subscribers registered through the facade run alongside the
    library's own construction-time bookkeeping, which always runs
    first — bind order is execution order, and the wrapper bound its
    own before user code could register anything.
    """

    @property
    def sequence(self) -> str:
        return "<Destroy>"


@dataclass(frozen=True, slots=True)
class Virtual(EventSpec):
    """A virtual event: the named ``<<...>>`` occurrences software speaks.

    One kind for Tk's shipped events and user-defined ones alike — a
    user-defined virtual event differs from a shipped one only in who
    named it, and :attr:`type` answers with the built-in member where
    the name is one Tk ships. Since the same name is the same event,
    ``Virtual(VirtualEvent.COPY)`` and ``Virtual("Copy")`` are one
    specification.

    This is the one specification
    :meth:`~tkfacade.widget.BaseWidget.emit` may carry a payload on.
    Tk drops a generated event silently until the target widget's X
    window exists (`hazards/tkinter.md`, *Bindings*), so an emit can reach
    nobody on a widget Tk has not realized yet.

    Args:
        name (VirtualEvent | str): The event's name — a
            :class:`VirtualEvent` member, or any bracketless name for
            a user-defined event.
    """

    name: VirtualEvent | str = field()

    def __post_init__(self) -> None:
        name = str(self.name)
        if not name or any(part in name for part in ("<", ">", " ")):
            raise ValueError(f"not an event name: {name!r}")

    @property
    def type(self) -> VirtualEvent | None:
        """The Tk-shipped event this names; None for a user-defined one."""
        try:
            return VirtualEvent(str(self.name))
        except ValueError:
            return None

    @property
    def sequence(self) -> str:
        return f"<<{self.name}>>"


ACTIVATED: Final[Virtual] = Virtual("Activated")
"""The activation occurrence every command-shaped surface emits.

A ``command`` is Tk's mainloop-native channel with exactly one holder,
so activation was never subscribable — and a coroutine, first-class on
the subscription route, had no way to hear a button. Now every surface
that runs a command also emits this event on its wrapper, command
first and emission after (a coroutine command is *scheduled* first,
its body following off the mainloop as fire-and-forget always does),
whether or not a command is set — so any
number of subscribers, coroutines included, hear an activation the
single command slot never could share. The wrapper the event arrives
on says *what* was activated; where one wrapper holds several
activatable parts, the payload names the part: ``"row"`` for a menu
entry, ``"column"`` for a tree or table heading, ``"button"`` for a
bank's member. Emission rides :meth:`~tkfacade.widget.BaseWidget.emit`,
so a programmatic ``invoke()`` before the widget's window exists is
dropped as any early emit is (`hazards/tkinter.md`, *Bindings*), and a command
that destroys its own widget — a dialog button completing the dialog —
emits into the same silence: widget death ends deliveries, so the
activation that destroyed the widget is heard by nobody. A real
interaction on a live widget always finds its window realized.
"""
