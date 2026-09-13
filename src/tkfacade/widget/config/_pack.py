"""Deferred pack configuration: the master half, and the slave half beside it."""

import tkinter as tk
from typing import TYPE_CHECKING, Self, Unpack, cast

from ..._params import PackSetOptions
from ..._types import Anchor, Fill, Pad, PadValue, Side
from .._base import BaseWidget
from ._base import AbstractConfig, AbstractSetConfig

if TYPE_CHECKING:
    from .._widget import ContainerWidget, Widget


class PackConfig(AbstractConfig["ContainerWidget"]):
    """Deferred options for a pack container.

    Pack gives a master one setting, ``pack_propagate``, so that is the
    whole of this config — the per-widget options belong to the call
    that packs a widget, not to its master. Unset stays ``None`` and is
    skipped by :meth:`visit`, so applying a config only ever touches
    what was explicitly set.
    """

    if TYPE_CHECKING:
        _propagate: bool | None

    __slots__ = ("_propagate",)

    def __init__(self) -> None:
        """Start empty: propagate unset."""
        self._propagate = None

    def __copy__(self) -> Self:
        """Return an independent copy one level deep; leaf values are shared."""
        new = type(self)()
        new._propagate = self._propagate
        return new

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        """Return a fully independent copy; option values are deep-copied too."""
        new = type(self)()
        memo[id(self)] = new
        new._propagate = self._propagate
        return new

    @property
    def propagate(self) -> bool | None:
        """The pending propagate flag; ``None`` means unset.

        Assigning ``None`` clears it.
        """
        return self._propagate

    @propagate.setter
    def propagate(self, flag: bool | None) -> None:
        self._propagate = flag

    def hard_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``, ``other`` winning on conflicts.

        A propagate ``other`` never set does not clear this one's.

        Returns:
            ``self``, mutated in place.
        """
        if other._propagate is not None:
            self._propagate = other._propagate
        return self

    def soft_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``, ``self`` winning on conflicts.

        Returns:
            ``self``, mutated in place.
        """
        if self._propagate is None:
            self._propagate = other._propagate
        return self

    def visit(self, master: ContainerWidget, /) -> None:
        """Apply the accumulated options to a live master.

        Args:
            master (ContainerWidget): The wrapper whose pack container
                receives the options.
        """
        if self._propagate is not None:
            master.pack_propagate(self._propagate)


class PackSetConfig(AbstractSetConfig):
    """The composable twin of :class:`~tkfacade.PackSetOptions`.

    Holds the options :meth:`~tkfacade.widget.Widget.pack` takes —
    the child half of a pack layout — with the merge surface the
    master-side configs have: ``|`` and the hard/soft updates compose
    placements before any widget exists, and :meth:`visit` replays the
    result through the widget's own method, so Tk's incremental merge
    and the first-placement defaults apply exactly as they do to
    keyword arguments. Each option answers ``None`` while unset, and
    assigning ``None`` clears it.
    """

    __slots__ = ()

    def __init__(self, **options: Unpack[PackSetOptions]) -> None:
        """Start from ``options``, any of the method's own.

        Args:
            **options (Unpack[PackSetOptions]): Starting placement
                options, each documented on
                :meth:`~tkfacade.widget.Widget.pack`.
        """
        super().__init__(**options)

    @property
    def after(self) -> BaseWidget | None:
        """Sibling packed immediately before this one, answered as its wrapper.

        Assigning takes a wrapper or a raw Tk widget, as the keyword
        does, and ``None`` clears. The read follows the traversal
        rule: a raw master the facade did not build is held and
        applied at :meth:`visit`, but is not named here — it reads
        None, like an unset option.
        """
        held = self._get("after")
        if held is None or isinstance(held, BaseWidget):
            return held
        return BaseWidget._wrappers.get((held.tk, str(held)))

    @after.setter
    def after(self, value: tk.Misc | BaseWidget | None) -> None:
        self._set("after", value)

    @property
    def anchor(self) -> Anchor | None:
        """Position within the parcel; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Anchor | None", self._get("anchor"))

    @anchor.setter
    def anchor(self, value: Anchor | None) -> None:
        self._set("anchor", value)

    @property
    def before(self) -> BaseWidget | None:
        """Sibling packed immediately after this one, answered as its wrapper.

        Assigning takes a wrapper or a raw Tk widget, as the keyword
        does, and ``None`` clears. The read follows the traversal
        rule: a raw master the facade did not build is held and
        applied at :meth:`visit`, but is not named here — it reads
        None, like an unset option.
        """
        held = self._get("before")
        if held is None or isinstance(held, BaseWidget):
            return held
        return BaseWidget._wrappers.get((held.tk, str(held)))

    @before.setter
    def before(self, value: tk.Misc | BaseWidget | None) -> None:
        self._set("before", value)

    @property
    def expand(self) -> bool | None:
        """Whether the parcel grows into extra space; ``None`` means unset. Assigning ``None`` clears."""
        return cast("bool | None", self._get("expand"))

    @expand.setter
    def expand(self, value: bool | None) -> None:
        self._set("expand", value)

    @property
    def fill(self) -> Fill | None:
        """Axes the widget stretches along; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Fill | None", self._get("fill"))

    @fill.setter
    def fill(self, value: Fill | None) -> None:
        self._set("fill", value)

    @property
    def side(self) -> Side | None:
        """Side of the master packed against; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Side | None", self._get("side"))

    @side.setter
    def side(self, value: Side | None) -> None:
        self._set("side", value)

    @property
    def ipadx(self) -> PadValue | None:
        """Internal horizontal padding; ``None`` means unset. Assigning ``None`` clears."""
        return cast("PadValue | None", self._get("ipadx"))

    @ipadx.setter
    def ipadx(self, value: PadValue | None) -> None:
        self._set("ipadx", value)

    @property
    def ipady(self) -> PadValue | None:
        """Internal vertical padding; ``None`` means unset. Assigning ``None`` clears."""
        return cast("PadValue | None", self._get("ipady"))

    @ipady.setter
    def ipady(self, value: PadValue | None) -> None:
        self._set("ipady", value)

    @property
    def padx(self) -> Pad | None:
        """External horizontal padding; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Pad | None", self._get("padx"))

    @padx.setter
    def padx(self, value: Pad | None) -> None:
        self._set("padx", value)

    @property
    def pady(self) -> Pad | None:
        """External vertical padding; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Pad | None", self._get("pady"))

    @pady.setter
    def pady(self, value: Pad | None) -> None:
        self._set("pady", value)

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
        widget.pack(cast(PackSetOptions, dict(self._options)))
