"""The progress bar wrappers: one scaled in percent, one in whole items.

Two bars over the same ttk widget, differing in what their scale
counts. :class:`PercentageBasedProgressBar` is fixed at 0 to 100 and
reads its progress as a float; :class:`ItemBasedProgressBar` counts
whole items against a total the caller sets and may move afterwards.
Both are determinate, and neither offers Tk's indeterminate mode.

Each is driven by an observable, its own by default or one the caller
passes to share the value with something else. The range is enforced
by the ``current`` setter, so a caller driving a shared observable
directly reaches the widget without passing that check.
"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, cast

from .._types import Orient, PadValue
from ..events import Destroyed, Event
from ..look import Look
from ..observable import ObservableFloat, ObservableInt
from ..widget import BaseWidget, Widget


class PercentageBasedProgressBar(Widget):
    """A determinate progress bar scaled from 0 to 100 percent.

    The scale is fixed: :attr:`current` is the percentage complete, and
    the widget's maximum is 100 whatever the work behind it actually
    counts. Code measuring something else converts to a percentage, or
    uses :class:`ItemBasedProgressBar` and counts in its own unit.

    Appearance comes from the ``Horizontal.TProgressbar`` or
    ``Vertical.TProgressbar`` style, by the orientation the bar was
    built with, rather than from per-widget options: there is no colour
    or relief to set here, and a bar restyled through
    :class:`ttk.Style` follows.
    """

    if TYPE_CHECKING:
        _tk: ttk.Progressbar
        _observable: ObservableFloat

    __slots__ = ("_observable",)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        orient: Orient,
        length: PadValue,
        current: float | ObservableFloat = 0.0,
        look: Look | None = None,
    ) -> None:
        """Create the bar, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the bar
                is created inside.
            orient (Orient): The axis the bar fills along.
            length (PadValue): The bar's size along that axis, in pixels
                or as a Tk screen distance.
            current (float | ObservableFloat): The percentage complete —
                a starting value, range-checked like every assignment,
                or the observable already holding it, displayed as it
                stands and never range-checked. Defaults to 0.0, an
                empty bar with an observable of its own.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``current`` is a plain value outside 0
                to 100.
        """
        if not isinstance(current, ObservableFloat):
            if not 0 <= current <= 100:
                raise ValueError(f"current must be a percentage from 0 to 100, not {current}")
            current = ObservableFloat(float(current))
        self._observable = current
        master = self._as_master(parent)
        self._tk = ttk.Progressbar(
            master,
            orient=orient,
            length=length,
            maximum=100.0,
            # cast: the transport is the DoubleVar `_new_var` built, a subtype typeshed's `Progressbar` wants spelled anyway
            variable=cast(tk.DoubleVar, self._observable.transport_for(master)),
            mode="determinate",
        )
        self._tk._observables = (self._observable,)  # type: ignore[attr-defined]
        super().__init__()
        self.bind(Destroyed(), self._give_back_transport)
        if look is not None:
            self.look = look

    def _give_back_transport(self, _event: Event) -> None:
        """Release the transport ride construction took; the widget is done."""
        self._observable.release_transport()

    @property
    def current(self) -> float:
        """The percentage complete; assignments outside 0 to 100 raise.

        Raises rather than clamping; an int assigned is stored as the
        equivalent float.

        Raises:
            ValueError: If the assigned value is outside 0 to 100.
        """
        return self._observable.value

    @current.setter
    def current(self, value: int | float) -> None:
        if not 0 <= value <= 100:
            raise ValueError(f"current must be a percentage from 0 to 100, not {value}")
        self._observable.value = float(value)

    @property
    def current_observable(self) -> ObservableFloat:
        """The observable holding the percentage, for watching or sharing.

        The bar's own unless one was passed to the constructor. Writes
        driven through it reach the widget without the range check
        :attr:`current` applies.
        """
        return self._observable


class ItemBasedProgressBar(Widget):
    """A determinate progress bar counting whole items against a total.

    :attr:`current` is how many items are done and :attr:`maximum` how
    many there are, both whole counts. The total is not fixed at
    construction: a job that discovers more work moves :attr:`maximum`
    and the drawn proportion follows.

    Appearance comes from the ``Horizontal.TProgressbar`` or
    ``Vertical.TProgressbar`` style, by the orientation the bar was
    built with, rather than from per-widget options: there is no colour
    or relief to set here, and a bar restyled through
    :class:`ttk.Style` follows.
    """

    if TYPE_CHECKING:
        _tk: ttk.Progressbar
        _observable: ObservableInt

    __slots__ = ("_observable",)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        orient: Orient,
        length: PadValue,
        maximum: int,
        current: int | ObservableInt = 0,
        look: Look | None = None,
    ) -> None:
        """Create the bar, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the bar
                is created inside.
            orient (Orient): The axis the bar fills along.
            length (PadValue): The bar's size along that axis, in pixels
                or as a Tk screen distance.
            maximum (int): How many items a full bar stands for.
            current (int | ObservableInt): The count done — a starting
                value, range-checked like every assignment, or the
                observable already holding it, displayed as it stands
                and never range-checked. Defaults to 0, an empty bar
                with an observable of its own.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``maximum`` is less than one item, or
                ``current`` is a plain value outside 0 to ``maximum``.
        """
        if maximum <= 0:
            raise ValueError(f"maximum must be at least one item, not {maximum}")
        if not isinstance(current, ObservableInt):
            if not 0 <= current <= maximum:
                raise ValueError(f"current must be a count from 0 to {maximum}, not {current}")
            current = ObservableInt(int(current))
        self._observable = current
        master = self._as_master(parent)
        self._tk = ttk.Progressbar(
            master,
            orient=orient,
            length=length,
            maximum=maximum,
            # cast: the transport is the IntVar `_new_var` built, a subtype typeshed's `Progressbar` wants spelled anyway
            variable=cast(tk.IntVar, self._observable.transport_for(master)),
            mode="determinate",
        )
        self._tk._observables = (self._observable,)  # type: ignore[attr-defined]
        super().__init__()
        self.bind(Destroyed(), self._give_back_transport)
        if look is not None:
            self.look = look

    def _give_back_transport(self, _event: Event) -> None:
        """Release the transport ride construction took; the widget is done."""
        self._observable.release_transport()

    @property
    def current(self) -> int:
        """How many items are done; assignments outside 0 to :attr:`maximum` raise.

        Raises rather than clamping; a float within range is truncated
        toward zero: the bar counts whole items only.

        Raises:
            ValueError: If the assigned value is negative or exceeds
                :attr:`maximum`.
        """
        return self._observable.value

    @current.setter
    def current(self, value: int | float) -> None:
        maximum = self.maximum
        if not 0 <= value <= maximum:
            raise ValueError(f"current must be a count from 0 to {maximum}, not {value}")
        self._observable.value = int(value)

    @property
    def current_observable(self) -> ObservableInt:
        """The observable holding the count done, for watching or sharing.

        The bar's own unless one was passed to the constructor. Writes
        driven through it reach the widget without the range check
        :attr:`current` applies.
        """
        return self._observable

    @property
    def maximum(self) -> int:
        """How many items a full bar stands for; read live from the widget.

        Lowering it below :attr:`current` leaves the count where it is
        and the bar drawn full. A float assigned is truncated toward
        zero before the check, so anything under one whole item is
        rejected.

        Raises:
            ValueError: If the assigned value is less than one item.
        """
        return int(self._tk.cget("maximum"))

    @maximum.setter
    def maximum(self, value: int | float) -> None:
        items = int(value)
        if items <= 0:
            raise ValueError(f"maximum must be at least one item, not {value}")
        self._tk.configure(maximum=items)
