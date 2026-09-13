"""The Listbox wrapper: a themed list of strings, selectable."""

import tkinter as tk
from collections.abc import Iterable, Iterator, MutableSequence, Sequence
from tkinter import ttk
from typing import TYPE_CHECKING, overload

from .._utils import select_param
from ..look import Look
from ..scroll import AbstractScrollable, ScrollbarSpec
from ..widget import BaseWidget


class Listbox(AbstractScrollable, MutableSequence[str]):
    """A themed list of strings the user can select from.

    Reads as a list because it is one: indexing, slicing, ``append``,
    ``insert``, ``remove``, ``len`` and iteration all work, and the
    widget updates as the sequence changes.

    **Built on a themed tree rather than on ``tk.Listbox``**, which is
    a classic widget with no ttk style at all — ``Style().layout``
    raises for it — so its whole appearance is per-widget colours,
    fonts and reliefs. Wrapped, it would be foreign in every themed
    application and unreachable from any styling facade, there being
    no style to reach. A ``ttk.Treeview`` showing only its tree column
    is the same list, themed. This costs one behaviour: Tk's
    ``multiple`` selection mode, where clicks accumulate without a
    modifier, is refused by the themed widget, which offers only the
    modifier-driven ``extended``.

    Selection is read through :attr:`selection` and moved through
    :meth:`select` and its three companions — the vocabulary
    :class:`~tkfacade.Tree` already uses, keyed by position here
    because a list may hold the same string twice and a value is
    therefore not an identity. A change of selection arrives as
    ``Virtual(VirtualEvent.TREEVIEW_SELECT)``, the same event a tree's
    selection announces, which is how this widget stays watchable
    without inventing an observable for a set of strings.

    The list is a display of content, not a menu of options: where a
    caller wants one value committed from a small fixed set,
    :class:`~tkfacade.ChoiceBox` and its siblings are that family.
    """

    if TYPE_CHECKING:
        _tk: ttk.Frame

    __slots__ = ("_treeview",)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        items: Iterable[str] = (),
        *,
        selection_enabled: bool = True,
        selection_extended: bool = False,
        height: int = 10,
        vertical_scrollbar: bool | ScrollbarSpec = True,
        horizontal_scrollbar: bool | ScrollbarSpec = False,
        look: Look | None = None,
    ) -> None:
        """Create the list, its scrollbars, and any initial items.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                list is created inside.
            items (Iterable[str]): The strings the list starts with,
                in order. Defaults to ``()``, an empty list.
            selection_enabled (bool): Whether items can be selected at
                all. Defaults to True.
            selection_extended (bool): Whether more than one item may
                be selected at once; ignored when
                ``selection_enabled`` is False. Defaults to False.
            height (int): Items visible without scrolling. Defaults to
                10.
            vertical_scrollbar (bool | ScrollbarSpec): Whether a
                vertical bar sits in the right gutter, or the spec
                declaring one. Defaults to True.
            horizontal_scrollbar (bool | ScrollbarSpec): Whether a
                horizontal bar sits in the bottom gutter, or the spec
                declaring one. Defaults to False.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._tk = ttk.Frame(self._as_master(parent))
        self._treeview: ttk.Treeview = ttk.Treeview(
            self._tk,
            show="tree",
            selectmode=select_param(enabled=selection_enabled, extended=selection_extended),
            height=height,
        )
        self._build_gutters(
            self._treeview, vertical=vertical_scrollbar, horizontal=horizontal_scrollbar
        )
        for item in items:
            self._treeview.insert("", "end", text=item)
        super().__init__()
        self._route_events(self._treeview, *self._scroll_bars.values())
        if look is not None:
            self.look = look

    def __len__(self) -> int:
        """The number of items in the list."""
        return len(self._treeview.get_children(""))

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> list[str]: ...

    def __getitem__(self, index: int | slice) -> str | list[str]:
        """Return the item at ``index``, or the list a slice names.

        Raises:
            IndexError: If an integer index is out of range.
        """
        iids = self._treeview.get_children("")
        if isinstance(index, slice):
            return [self._text(iid) for iid in iids[index]]
        return self._text(iids[index])

    @overload
    def __setitem__(self, index: int, value: str) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[str]) -> None: ...

    def __setitem__(self, index: int | slice, value: str | Iterable[str]) -> None:
        """Replace the item at ``index``, or the items a slice names.

        A contiguous slice may be replaced by any number of items, as
        a list's may; an extended slice needs exactly as many items as
        it names.

        Raises:
            IndexError: If an integer index is out of range.
            ValueError: If an extended slice and its replacement are
                different lengths.
        """
        iids = self._treeview.get_children("")
        if not isinstance(index, slice):
            self._treeview.item(iids[index], text=str(value))
            return
        replacement = [str(item) for item in items_from(value)]
        positions = range(*index.indices(len(iids)))
        if index.step not in (None, 1):
            if len(positions) != len(replacement):
                raise ValueError(
                    f"an extended slice of {len(positions)} items cannot take "
                    f"{len(replacement)} of them"
                )
            for position, item in zip(positions, replacement, strict=True):
                self._treeview.item(iids[position], text=item)
            return
        # a contiguous slice may change the list's length
        start = positions.start if positions else index.indices(len(iids))[0]
        for position in positions:
            self._treeview.delete(iids[position])
        for offset, item in enumerate(replacement):
            self._treeview.insert("", start + offset, text=item)

    def __delitem__(self, index: int | slice) -> None:
        """Remove the item at ``index``, or every item a slice names.

        Raises:
            IndexError: If an integer index is out of range.
        """
        iids = self._treeview.get_children("")
        doomed = iids[index] if isinstance(index, slice) else (iids[index],)
        for iid in doomed:
            self._treeview.delete(iid)

    def __iter__(self) -> Iterator[str]:
        """Iterate the items in order.

        Defined rather than inherited: the mixin's version walks
        indices and would ask Tk for the whole list once per item.
        """
        return (self._text(iid) for iid in self._treeview.get_children(""))

    def _text(self, iid: str, /) -> str:
        """The string one row displays."""
        return str(self._treeview.item(iid, "text"))

    def _iid_at(self, index: int, /) -> str:
        """The row id at ``index``.

        Raises:
            IndexError: If the index is out of range.
        """
        return self._treeview.get_children("")[index]

    @property
    def selection(self) -> tuple[int, ...]:
        """The positions of the selected items, in list order.

        Read-only: :meth:`select` and its companions are how a
        selection is moved, which is the vocabulary
        :class:`~tkfacade.Tree` uses.
        """
        iids = self._treeview.get_children("")
        selected = set(self._treeview.selection())
        return tuple(position for position, iid in enumerate(iids) if iid in selected)

    @property
    def selected_items(self) -> tuple[str, ...]:
        """The selected items themselves, in list order.

        The convenience :class:`~tkfacade.Tree` has no need of, its
        row handles carrying their own content where a position does
        not.
        """
        return tuple(self._text(iid) for iid in self._ordered_selection())

    @property
    def selection_enabled(self) -> bool:
        """Whether items can be selected at all; read live from Tk."""
        return str(self._treeview.cget("selectmode")) != "none"

    @property
    def selection_extended(self) -> bool:
        """Whether more than one item may be selected at once; read live from Tk."""
        return str(self._treeview.cget("selectmode")) == "extended"

    @property
    def height(self) -> int:
        """Items visible without scrolling; read live from Tk."""
        return int(self._treeview.cget("height"))

    @height.setter
    def height(self, value: int) -> None:
        if value < 1:
            raise ValueError(f"height must be at least 1, not {value}")
        self._treeview.configure(height=value)

    def _ordered_selection(self) -> tuple[str, ...]:
        """The selected row ids, in list order rather than Tk's."""
        selected = set(self._treeview.selection())
        return tuple(iid for iid in self._treeview.get_children("") if iid in selected)

    def insert(self, index: int, value: str) -> None:
        """Put ``value`` into the list at ``index``, moving the rest along.

        Args:
            index (int): Where the item lands; past the end appends,
                as a list's ``insert`` does.
            value (str): The item.
        """
        length = len(self)
        if index < 0:
            index = max(0, length + index)
        self._treeview.insert("", min(index, length), text=str(value))

    def select(self, *indices: int) -> None:
        """Replace the selection with exactly the items at these positions.

        Raises:
            IndexError: If any index is out of range.
        """
        self._treeview.selection_set([self._iid_at(index) for index in indices])

    def add_to_selection(self, *indices: int) -> None:
        """Add these positions to the selection, keeping the rest.

        Raises:
            IndexError: If any index is out of range.
        """
        self._treeview.selection_add([self._iid_at(index) for index in indices])

    def remove_from_selection(self, *indices: int) -> None:
        """Remove these positions from the selection, keeping the rest.

        Raises:
            IndexError: If any index is out of range.
        """
        self._treeview.selection_remove([self._iid_at(index) for index in indices])

    def toggle_selection(self, *indices: int) -> None:
        """Invert each position's membership in the selection.

        Raises:
            IndexError: If any index is out of range.
        """
        self._treeview.selection_toggle([self._iid_at(index) for index in indices])


def items_from(value: str | Iterable[str], /) -> Sequence[str]:
    """Return ``value`` as a sequence, treating a bare string as one item.

    Assigning a string to a slice would otherwise spread it one
    character per row, which is a list's behaviour but never what a
    caller of this widget means.
    """
    if isinstance(value, str):
        return (value,)
    return list(value)
