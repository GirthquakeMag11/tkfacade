"""The delivered event: an immutable record of one occurrence.

One :class:`Event` is built per delivery and handed to every subscriber
of the specification that fired — a fact, not a handle: nothing on it
can be assigned, its payload is a read-only mapping, and it is safe to
keep, log, or carry to another thread. Events compare by identity, the
way occurrences do.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from ._spec import EventSpec

if TYPE_CHECKING:
    from ..widget import BaseWidget

EMPTY_PAYLOAD: Final[Mapping[str, object]] = MappingProxyType({})
"""The payload of every event that carried none."""


class Event:
    """What a subscriber receives: the occurrence, immutably.

    The dispatch builds one per delivery, translating tkinter's raw
    event before it gets here; the constructor takes only plain values,
    so a test can fabricate an occurrence for a handler with no tkinter
    object anywhere. The fields are the occurrence's own facts — where
    it happened and when — plus the :attr:`spec` that fired, the
    :attr:`widget` wrapper the event landed on, and the emitted
    :attr:`payload`. Position rides only the occurrence kinds that
    happen at the pointer (:attr:`EventSpec.at_pointer
    <tkfacade.events.EventSpec.at_pointer>`), never a keystroke's
    packet. What the input device's *state* was — keys and
    buttons held, the character a keystroke would type — is
    deliberately absent: state belongs to the input-state layer (the
    keyboard-and-mouse observer), and the specification already names
    the input a press or release delivers.
    Consumption is not on it anywhere: whether Tk's default action
    follows is a property of the dispatch, not of the occurrence, and
    it is decided by the consumers' completion alone.
    """

    __slots__ = (
        "_payload",
        "_screen_x",
        "_screen_y",
        "_spec",
        "_time",
        "_widget",
        "_widget_x",
        "_widget_y",
    )

    def __init__(
        self,
        *,
        spec: EventSpec,
        widget: BaseWidget | None,
        payload: Mapping[str, object] = EMPTY_PAYLOAD,
        widget_x: int | None = None,
        widget_y: int | None = None,
        screen_x: int | None = None,
        screen_y: int | None = None,
        time: int | None = None,
    ) -> None:
        """Record one occurrence from its delivered facts.

        Args:
            spec (EventSpec): The specification that fired.
            widget (BaseWidget | None): The wrapper the event landed
                on, or None where no wrapper owns the widget.
            payload (Mapping[str, object]): The emitted payload.
                Defaults to the shared empty mapping.
            widget_x (int | None): The occurrence's x within
                ``widget``. Defaults to None, an occurrence that
                carries no position.
            widget_y (int | None): The occurrence's y within
                ``widget``. Defaults to None.
            screen_x (int | None): The occurrence's x on the screen.
                Defaults to None.
            screen_y (int | None): The occurrence's y on the screen.
                Defaults to None.
            time (int | None): The occurrence's Tk timestamp, in its
                milliseconds. Defaults to None.
        """
        self._spec = spec
        self._widget = widget
        self._payload = payload
        self._widget_x = widget_x
        self._widget_y = widget_y
        self._screen_x = screen_x
        self._screen_y = screen_y
        self._time = time

    def __repr__(self) -> str:
        """Return the spec fired and where, for logs and failures."""
        return f"<Event {self._spec.sequence} on {self._widget!r}>"

    @property
    def spec(self) -> EventSpec:
        """The specification whose binding delivered this event."""
        return self._spec

    @property
    def widget(self) -> BaseWidget | None:
        """The wrapper the event landed on; None when no wrapper owns it."""
        return self._widget

    @property
    def widget_x(self) -> int | None:
        """The occurrence's x within :attr:`widget`, where it carries one."""
        return self._widget_x

    @property
    def widget_y(self) -> int | None:
        """The occurrence's y within :attr:`widget`, where it carries one."""
        return self._widget_y

    @property
    def screen_x(self) -> int | None:
        """The occurrence's x on the screen, where it carries one."""
        return self._screen_x

    @property
    def screen_y(self) -> int | None:
        """The occurrence's y on the screen, where it carries one."""
        return self._screen_y

    @property
    def time(self) -> int | None:
        """The occurrence's Tk timestamp, in its milliseconds."""
        return self._time

    @property
    def payload(self) -> Mapping[str, object]:
        """What :meth:`~tkfacade.widget.BaseWidget.emit` sent, read-only.

        Empty for every event that carried none — physical occurrences
        always, and virtual events arriving from outside ``emit``.
        """
        return self._payload
