"""The scrollbar declaration: what a bar is, before one exists."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .._sentinels import OMIT, Omitted
from .._types import Orient, Side

if TYPE_CHECKING:
    from ._scrollable import AbstractScrollable


@dataclass
class ScrollbarSpec:
    """A scrollbar's declared configuration, applied to a live widget by ``visit``.

    Passed where a bare ``True`` would go — ``TextBox(parent,
    vertical_scrollbar=ScrollbarSpec(auto_hide=True))`` — so asking for
    a bar and saying what kind are the same act. Self-contained: every
    field has a usable default, and a spec may be applied to any
    number of widgets, since ``visit`` does not mutate it.

    The spec is the construction door; the same settings answer live
    afterwards on the bar's facet —
    :attr:`~tkfacade.AbstractScrollable.vertical_scrollbar` and its
    horizontal twin — the way a tree's column specs sit beside its
    live column views.

    Attributes:
        auto_hide (bool): Whether the bar leaves the layout while its
            axis has nothing to scroll, and returns when it does.
            Defaults to False — a bar that comes and goes reflows
            everything around it, which should be asked for rather
            than arrive uninvited.
        placement (Side | Omitted): The side of the content the bar
            sits at — left or right for a vertical bar, top or bottom
            for a horizontal one, anything else refused when applied.
            Defaults to ``OMIT``, each axis's own convention: right,
            and bottom. One spec serves either axis only while this
            stays omitted, a side belonging to exactly one.
    """

    auto_hide: bool = False
    placement: Side | Omitted = OMIT

    def visit(self, widget: AbstractScrollable, axis: Orient, /) -> None:
        """Apply this spec to ``axis``'s bar on a widget that already has one.

        Args:
            widget (AbstractScrollable): The widget holding the bar.
            axis (Orient): Which of its bars this configures.

        Raises:
            ValueError: If :attr:`placement` names a side that is not
                on ``axis``.
        """
        if self.placement is not OMIT:
            widget._set_bar_side(axis, self.placement)
        widget._set_auto_hide(axis, self.auto_hide)
