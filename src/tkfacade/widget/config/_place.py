"""Deferred place configuration: an empty master half, a full slave half."""

import tkinter as tk
from typing import TYPE_CHECKING, Self, Unpack, cast

from ..._params import PlaceSetOptions
from ..._types import Anchor, BorderMode, PadValue, Rel
from .._base import BaseWidget
from ._base import AbstractConfig, AbstractSetConfig

if TYPE_CHECKING:
    from .._widget import ContainerWidget, Widget


class PlaceConfig(AbstractConfig["ContainerWidget"]):
    """Deferred options for a place container — of which Tk has none.

    Place configures the widget being placed and never its master:
    ``PlaceContainerWidget`` offers ``place_slaves`` and no setter at
    all, so there is nothing for a master-side config to accumulate and
    :meth:`visit` has nothing to apply. The class exists so that every
    geometry manager answers to the same protocol — a caller holding a
    config per manager can merge and visit all three without asking
    which one it has.
    """

    __slots__ = ()

    def __init__(self) -> None:
        """Start empty, which is the only state this config has."""

    def __copy__(self) -> Self:
        """Return an independent copy; there is no state to share."""
        return type(self)()

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        """Return a fully independent copy; there is no state to copy."""
        new = type(self)()
        memo[id(self)] = new
        return new

    def hard_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``; there is nothing to merge.

        Returns:
            ``self``, unchanged.
        """
        return self

    def soft_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``; there is nothing to merge.

        Returns:
            ``self``, unchanged.
        """
        return self

    def visit(self, master: ContainerWidget, /) -> None:
        """Apply the accumulated options to a live master; a no-op.

        ``master`` is left exactly as it was found, placed children
        included: place stores its options on the child, and this
        config holds none.

        Args:
            master (ContainerWidget): The wrapper that would receive
                the options, if there were any.
        """


class PlaceSetConfig(AbstractSetConfig):
    """The composable twin of :class:`~tkfacade.PlaceSetOptions`.

    Holds the options :meth:`~tkfacade.widget.Widget.place` takes —
    the child half of a place layout — with the merge surface the
    master-side configs have: ``|`` and the hard/soft updates compose
    placements before any widget exists, and :meth:`visit` replays the
    result through the widget's own method, so Tk's incremental merge
    and the first-placement defaults apply exactly as they do to
    keyword arguments. Each option answers ``None`` while unset, and
    assigning ``None`` clears it.
    """

    __slots__ = ()

    def __init__(self, **options: Unpack[PlaceSetOptions]) -> None:
        """Start from ``options``, any of the method's own.

        Args:
            **options (Unpack[PlaceSetOptions]): Starting placement
                options, each documented on
                :meth:`~tkfacade.widget.Widget.place`.
        """
        super().__init__(**options)

    @property
    def anchor(self) -> Anchor | None:
        """The widget point pinned to the coordinates; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Anchor | None", self._get("anchor"))

    @anchor.setter
    def anchor(self, value: Anchor | None) -> None:
        self._set("anchor", value)

    @property
    def bordermode(self) -> BorderMode | None:
        """How coordinates measure against the border; ``None`` means unset. Assigning ``None`` clears."""
        return cast("BorderMode | None", self._get("bordermode"))

    @bordermode.setter
    def bordermode(self, value: BorderMode | None) -> None:
        self._set("bordermode", value)

    @property
    def x(self) -> PadValue | None:
        """Horizontal offset in pixels; ``None`` means unset. Assigning ``None`` clears."""
        return cast("PadValue | None", self._get("x"))

    @x.setter
    def x(self, value: PadValue | None) -> None:
        self._set("x", value)

    @property
    def y(self) -> PadValue | None:
        """Vertical offset in pixels; ``None`` means unset. Assigning ``None`` clears."""
        return cast("PadValue | None", self._get("y"))

    @y.setter
    def y(self, value: PadValue | None) -> None:
        self._set("y", value)

    @property
    def relx(self) -> Rel | None:
        """Horizontal position as a fraction of the master; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Rel | None", self._get("relx"))

    @relx.setter
    def relx(self, value: Rel | None) -> None:
        self._set("relx", value)

    @property
    def rely(self) -> Rel | None:
        """Vertical position as a fraction of the master; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Rel | None", self._get("rely"))

    @rely.setter
    def rely(self, value: Rel | None) -> None:
        self._set("rely", value)

    @property
    def width(self) -> PadValue | None:
        """Width in pixels; ``None`` means unset. Assigning ``None`` clears."""
        return cast("PadValue | None", self._get("width"))

    @width.setter
    def width(self, value: PadValue | None) -> None:
        self._set("width", value)

    @property
    def height(self) -> PadValue | None:
        """Height in pixels; ``None`` means unset. Assigning ``None`` clears."""
        return cast("PadValue | None", self._get("height"))

    @height.setter
    def height(self, value: PadValue | None) -> None:
        self._set("height", value)

    @property
    def relwidth(self) -> Rel | None:
        """Width as a fraction of the master; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Rel | None", self._get("relwidth"))

    @relwidth.setter
    def relwidth(self, value: Rel | None) -> None:
        self._set("relwidth", value)

    @property
    def relheight(self) -> Rel | None:
        """Height as a fraction of the master; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Rel | None", self._get("relheight"))

    @relheight.setter
    def relheight(self, value: Rel | None) -> None:
        self._set("relheight", value)

    @property
    def in_(self) -> BaseWidget | None:
        """Master to place into, answered as its wrapper.

        Assigning takes a wrapper or a raw Tk widget, as the keyword
        does, and ``None`` clears. The read follows the traversal
        rule: a raw master the facade did not build is held and
        applied at :meth:`visit`, but is not named here — it reads
        None, like an unset option.
        """
        held = self._get("in_")
        if held is None or isinstance(held, BaseWidget):
            return held
        return BaseWidget._wrappers.get((held.tk, str(held)))

    @in_.setter
    def in_(self, value: tk.Misc | BaseWidget | None) -> None:
        self._set("in_", value)

    def visit(self, widget: Widget, /) -> None:
        """Place or reconfigure ``widget`` with the held options.

        Args:
            widget (Widget): The wrapper to place; its master is the
                existing one unless :attr:`in_` names another.
        """
        widget.place(cast(PlaceSetOptions, dict(self._options)))
