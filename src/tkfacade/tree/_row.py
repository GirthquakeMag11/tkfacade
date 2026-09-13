"""Row-side wrappers for :class:`Tree`.

A row wrapper is a live handle onto one Treeview item, keyed by iid —
it caches nothing, so it cannot diverge from the widget's state; it
can still dangle once its iid is deleted (:attr:`TreeRow.deleted`
reports that). :class:`TreeRow` is the row itself; :class:`TreeRowTags`
is its tag view.
"""

import tkinter as tk
from collections.abc import (
    Collection,
    Iterable,
    Iterator,
    MutableMapping,
)
from contextlib import suppress
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Literal, overload

from ..media import ImageInput, ImageWrapper
from ._types import ROOT

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem

    from ._column import TreeColumn
    from ._tree import Tree


class TreeRowTags(Collection[str]):
    """The tags of one row, as a live view over Tk's tag list.

    The store is a list, not a set: it keeps the order tags were given
    in, and :meth:`set` installs duplicates if handed them, so ``len``
    counts repeats. That order is not style precedence — competing tag
    options are resolved by the order the tags were configured
    (:meth:`Tree.configure_tag`) — and every mutator but :meth:`set`
    leaves it undisturbed. For set algebra, build a set:
    ``set(row.tags) | {"new"}``.
    """

    __slots__ = ("_iid", "_treeview")

    def __init__(self, tree: Tree, iid: str, /) -> None:
        """Wrap the tags of item ``iid``; existence is not checked.

        Args:
            tree (Tree): The tree holding the item.
            iid (str): The item's iid.
        """
        self._treeview: ttk.Treeview = tree._treeview
        self._iid: str = iid

    def __iter__(self) -> Iterator[str]:
        """Iterate over the row's tags, in Tk's stored order."""
        return iter(self._current())

    def __contains__(self, value: object) -> bool:
        """Whether ``value`` is one of the row's tags."""
        return value in self._current()

    def __len__(self) -> int:
        """The number of tags on the row, duplicates counted."""
        return len(self._current())

    def _current(self) -> tuple[str, ...]:
        """Snapshot the row's tags, normalizing Tk's empty-string shape."""
        tags = self._treeview.item(self._iid, "tags")
        if tags == "":
            return ()
        return tuple(str(tag) for tag in tags)

    def set(self, value: str | Iterable[str], /) -> None:
        """Replace the row's tags wholesale.

        The one mutator that neither deduplicates nor preserves the
        existing order: what it is handed is what Tk stores.

        Args:
            value (str | Iterable[str]): The new tag or tags; a bare
                string is one tag, not an iterable of characters.
        """
        tags = (value,) if isinstance(value, str) else tuple(value)
        self._treeview.item(self._iid, tags=tags)

    def add(self, *values: str) -> None:
        """Append each of ``values`` the row does not already carry, in order.

        Batched into a single Tk write and skipped entirely when
        nothing is new, so the tags already present keep their
        positions.

        Args:
            *values (str): The tags to add. A tag already on the row is
                ignored, as is a repeat within ``values`` itself.
        """
        current = self._current()
        new = tuple(dict.fromkeys(v for v in values if v not in current))
        if new:
            self.set((*current, *new))

    def discard(self, *values: str) -> None:
        """Remove every occurrence of each of ``values``; absent is a no-op.

        Batched into a single Tk write and skipped entirely when none
        of them is present. Every occurrence goes, since :meth:`set`
        can install duplicates.

        Args:
            *values (str): The tags to remove.
        """
        current = self._current()
        doomed = frozenset(values)
        remaining = tuple(tag for tag in current if tag not in doomed)
        if len(remaining) != len(current):
            self.set(remaining)

    def toggle(self, value: str, /) -> bool:
        """Add ``value`` if the row lacks it, remove it if the row has it.

        Removing takes out every occurrence, as :meth:`discard` does;
        adding appends, as :meth:`add` does.

        Args:
            value (str): The tag to toggle.

        Returns:
            Whether the row carries the tag now.
        """
        current = self._current()
        if value in current:
            self.set(tuple(tag for tag in current if tag != value))
            return False
        self.set((*current, value))
        return True

    def replace(self, old: str, new: str, /) -> bool:
        """Swap ``old`` for ``new`` in place, keeping the position it held.

        :meth:`discard` followed by :meth:`add` would move the tag to
        the end instead. Where ``new`` is already on the row elsewhere,
        the surplus copies go, so it ends up carried once, at ``old``'s
        position.

        Args:
            old (str): The tag to replace. A tag the row does not carry
                is a no-op, ``new`` notwithstanding.
            new (str): The tag to put in its place.

        Returns:
            Whether the row's tags changed.
        """
        current = self._current()
        if old not in current:
            return False
        swapped: list[str] = []
        replaced = False
        for tag in current:
            if tag == old:
                if not replaced:
                    swapped.append(new)
                    replaced = True
            elif tag != new:
                swapped.append(tag)
        result = tuple(swapped)
        if result == current:
            return False
        self.set(result)
        return True

    def clear(self) -> None:
        """Remove every tag from the row, in a single Tk write."""
        self.set(())


class TreeRow(MutableMapping[str, Any]):
    """One row of a tree: converted cell mapping plus structure and display.

    A live view keyed by iid, holding no state of its own: two rows for
    the same tree and iid are interchangeable and compare equal. The
    mapping face reads and writes converted cell values, always through
    the owning column's converters; :attr:`tags` and
    :meth:`iter_children` expose the other facets.

    Removal is refused throughout that mapping face, a column belonging
    to the tree rather than to one row: :meth:`clear` blanks the cells
    instead, and :meth:`setdefault` can only read.
    """

    __slots__ = ("_iid", "_tree")

    def __init__(self, tree: Tree, iid: str, /) -> None:
        """Wrap item ``iid`` of ``tree``; existence is not checked.

        Args:
            tree (Tree): The tree wrapper the row belongs to.
            iid (str): The item's iid.
        """
        self._tree: Tree = tree
        self._iid: str = iid

    def __eq__(self, other: object) -> bool:
        """Equal when the tree is identical and the iid matches."""
        if not isinstance(other, TreeRow):
            return NotImplemented
        return self._tree is other._tree and self._iid == other._iid

    def __hash__(self) -> int:
        """Hash consistently with :meth:`__eq__`."""
        return hash((id(self._tree), self._iid))

    def __repr__(self) -> str:
        """Show the class name and iid — the row's identity within its tree."""
        return f"{type(self).__name__}(iid={self._iid!r})"

    def __getitem__(self, key: str) -> Any:
        """Return the converted value in column ``key``.

        An empty cell round-trips ``""`` through the outgoing
        converter.

        Raises:
            KeyError: If the column or the row does not exist.
        """
        try:
            raw = str(self._tree._treeview.set(self._iid, key))
        except tk.TclError:
            raise KeyError(key) from None
        return self._tree._converters_for(key).outgoing(raw)

    def __setitem__(self, key: str, value: Any) -> None:
        """Write ``value`` into column ``key`` through the incoming converter.

        Raises:
            KeyError: If the column or the row does not exist.
        """
        try:
            self._tree._treeview.set(
                self._iid, key, self._tree._converters_for(key).incoming(value)
            )
        except tk.TclError:
            raise KeyError(key) from None
        self._tree._cell_changed(self._iid, key)

    def __delitem__(self, key: str, /) -> None:
        """Refuse: a per-row value cannot be deleted.

        Columns are structural to the whole tree, and blanking instead
        would silently break Mapping invariants (the key stays present,
        ``__len__`` unchanged). Set the cell to ``""`` to blank it.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Treeview columns are tree-wide; a per-row value cannot be "
            'deleted. Set it to "" explicitly if you want to blank it.'
        )

    def __len__(self) -> int:
        """The number of columns; 0 when the row no longer exists."""
        return len(self._cells())

    def __iter__(self) -> Iterator[str]:
        """Iterate over column names, in logical order."""
        return iter(self._cells())

    def _cells(self) -> dict[str, str]:
        """Snapshot the row's raw cells; empty when the row no longer exists."""
        try:
            return dict(self._tree._treeview.set(self._iid))
        except tk.TclError:
            return {}

    # --------
    # Identity
    # --------

    @property
    def iid(self) -> str:
        """The row's Tk item id."""
        return self._iid

    @property
    def tree(self) -> Tree:
        """The tree wrapper this row belongs to."""
        return self._tree

    # ---------------
    # Converted cells
    # ---------------

    @property
    def data(self) -> dict[str, Any]:
        """A converted snapshot as a plain dict."""
        return {name: self[name] for name in self}

    # ---------
    # Structure
    # ---------

    @property
    def parent(self) -> TreeRow | None:
        """The parent row, or ``None`` for top-level rows.

        Note: Tk reports a detached row's parent as the root too, so its
        ``parent`` is also ``None``; use ``is_detached`` to distinguish.
        """
        parent_iid = self._tree._treeview.parent(self._iid)
        if parent_iid == ROOT:
            return None
        return self._tree._row(parent_iid)

    @parent.setter
    def parent(self, parent: TreeRow | str | None) -> None:
        self._tree.move(self, ROOT if parent is None else parent, "end")

    @property
    def depth(self) -> int:
        """Nesting depth: 0 for top-level rows."""
        return sum(1 for _ in self.iter_ancestors())

    @property
    def span(self) -> int:
        """This row plus every descendant revealed by expansion.

        A closed child still counts as one row — only the rows hidden
        inside it are excluded.
        """
        if self.is_open:
            return 1 + sum(child.span for child in self.iter_children())
        return 1

    @property
    def index(self) -> int:
        """Position among siblings."""
        return self._tree._treeview.index(self._iid)

    @index.setter
    def index(self, value: int) -> None:
        parent = self.parent
        self._tree.move(self, ROOT if parent is None else parent, value)

    # ----------
    # Visibility
    # ----------

    @property
    def is_detached(self) -> bool:
        """Whether this row or any ancestor is unlinked from the display.

        A detached ancestor hides the whole subtree even though its
        internal links stay intact, so the full chain is checked, not
        just this row.
        """
        treeview = self._tree._treeview
        iid = self._iid
        while iid != ROOT:
            parent_iid = treeview.parent(iid)
            if iid not in treeview.get_children(parent_iid):
                return True
            iid = parent_iid
        return False

    @property
    def is_collapsed(self) -> bool:
        """Whether some ancestor is closed, hiding this row."""
        return any(not ancestor.is_open for ancestor in self.iter_ancestors())

    @property
    def is_visible(self) -> bool:
        """Attached with every ancestor open — rendered, modulo scrolling."""
        return not self.is_detached and not self.is_collapsed

    @property
    def is_open(self) -> bool:
        """Whether the row is expanded, showing its children."""
        return bool(self._tree._treeview.item(self._iid, "open"))

    @is_open.setter
    def is_open(self, value: bool) -> None:
        self._tree._treeview.item(self._iid, open=value)

    # -------------
    # Item settings
    # -------------

    @property
    def text(self) -> str:
        """The row's tree-column label (shown when the tree column is visible)."""
        return str(self._tree._treeview.item(self._iid, "text"))

    @text.setter
    def text(self, value: str) -> None:
        self._tree._treeview.item(self._iid, text=value)

    @property
    def image(self) -> ImageWrapper | None:
        """The wrapper behind the row's image, or None when none is set.

        The very object the setter or :meth:`Tree.insert` was given,
        not a copy, so an image can be read back, transformed and
        handed to another row without being unwrapped.

        Assigning any :data:`~tkfacade.ImageInput` replaces what is there
        and retains the wrapper against garbage collection; assigning
        None clears and releases it. An image written straight onto the
        Treeview item behind this property's back reads as None here,
        and is not retained.
        """
        return self._tree._images.get(self._iid)

    @image.setter
    def image(self, value: ImageInput | None) -> None:
        if value is None:
            self._tree._treeview.item(self._iid, image="")
            self._tree._images.pop(self._iid, None)
            return
        wrapper, handle = self._tree._resolve_image(value)
        self._tree._treeview.item(self._iid, image=handle)
        self._tree._images[self._iid] = wrapper

    @property
    def tags(self) -> TreeRowTags:
        """A live view of the row's tags."""
        return TreeRowTags(self._tree, self._iid)

    @tags.setter
    def tags(self, value: str | Iterable[str]) -> None:
        TreeRowTags(self._tree, self._iid).set(value)

    # --------
    # Deletion
    # --------

    @property
    def deleted(self) -> bool:
        """Whether the row no longer exists in the tree."""
        return not self._tree.exists(self._iid)

    # ---------------
    # Converted cells
    # ---------------

    @overload
    def update(self, data: SupportsKeysAndGetItem[str, Any], /, **kwargs: Any) -> None: ...

    @overload
    def update(self, data: Iterable[tuple[str, Any]], /, **kwargs: Any) -> None: ...

    @overload
    def update(self, /, **kwargs: Any) -> None: ...

    def update(
        self,
        data: SupportsKeysAndGetItem[str, Any] | Iterable[tuple[str, Any]] = (),
        /,
        **kwargs: Any,
    ) -> None:
        """Write several converted cell values at once.

        Not atomic: keys are written one at a time, so entries earlier
        in the merged order are already committed when a later key
        raises.

        Args:
            data (SupportsKeysAndGetItem[str, Any] | Iterable[tuple[str, Any]]):
                Items to write, as a mapping-like object or key-value
                pairs. Defaults to ``()``, meaning kwargs only.
            **kwargs (Any): Further items; win over competing keys in
                ``data``.

        Raises:
            KeyError: If any key names no existing column.
        """
        for key, value in (dict(data) | kwargs).items():
            self[key] = value

    def setdefault(self, key: str, default: Any = None, /) -> Any:
        """Return the converted value in column ``key``; never inserts.

        Every column of the tree is a key of every row, so there is no
        absent key for a default to fill: a name no column answers to
        cannot be brought into being by writing it, and raises instead.
        ``default`` is therefore never returned.

        Args:
            key (str): The column name.
            default (Any): Unused; carried for the
                :class:`MutableMapping` signature. Defaults to None.

        Returns:
            The converted value in column ``key``.

        Raises:
            KeyError: If the column or the row does not exist.
        """
        return self[key]

    def clear(self) -> None:
        """Blank every cell of this row; the columns remain.

        A no-op once the row is gone, matching the empty mapping such
        a row already reads as everywhere else in this class.
        """
        with suppress(tk.TclError):
            columns = self._tree._treeview.cget("columns") or ()
            self._tree._treeview.item(self._iid, values=("",) * len(columns))
            self._tree._cell_changed(self._iid, None)

    def pop(self, key: str, default: Any = None, /) -> Any:
        """Refuse: a per-row value cannot be removed, only read or blanked.

        Named here rather than inherited, since
        :class:`MutableMapping`'s version removes by way of
        :meth:`__delitem__` and would answer for a method the caller
        never called.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Treeview columns are tree-wide; a per-row value cannot be "
            'popped. Read it first, then set it to "" to blank it.'
        )

    def popitem(self) -> tuple[str, Any]:
        """Refuse: a row has no removable item to hand back.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Treeview columns are tree-wide; a per-row value cannot be "
            'popped. Read it first, then set it to "" to blank it.'
        )

    # ---------
    # Structure
    # ---------

    def iter_children(self) -> Iterator[TreeRow]:
        """Iterate this row's direct children, in order; detached rows excluded.

        Lazy over a snapshot of the child iids, so restructuring during
        the walk is the caller's to avoid.

        Yields:
            Each child as a :class:`TreeRow`, in sibling order.
        """
        for iid in tuple(self._tree._treeview.get_children(self._iid)):
            yield self._tree._row(iid)

    def sort_children(
        self, column: TreeColumn, ascending: bool = True, recurse: bool = False
    ) -> None:
        """Sort this row's children in place by their values in a column.

        Compares converted values, so e.g. numeric columns sort
        numerically rather than as strings. Only attached children
        participate — :meth:`iter_children` excludes detached rows.

        Args:
            column (TreeColumn): The column whose converted values
                order the children.
            ascending (bool): Sort direction. Defaults to True,
                meaning smallest first.
            recurse (bool): Whether to also sort each child's
                children, all the way down. Defaults to False,
                meaning direct children only.

        Raises:
            KeyError: If ``column`` belongs to another tree, matching
                the refusal a foreign row gets everywhere.
        """
        if column.tree is not self._tree:
            raise KeyError(column)
        name = column.name
        ordered = sorted(
            self.iter_children(),
            key=lambda row: row[name],
            reverse=not ascending,
        )
        for index, child_row in enumerate(ordered):
            self._tree.move(child_row, self, index)
            if recurse:
                child_row.sort_children(column, ascending, recurse)

    def iter_ancestors(self) -> Iterator[TreeRow]:
        """Iterate outward from this row's parent to its top-level ancestor.

        Yields:
            Each ancestor as a :class:`TreeRow`, nearest first.
        """
        row = self.parent
        while row is not None:
            yield row
            row = row.parent

    # ----------
    # Visibility
    # ----------

    def hide(self) -> None:
        """Detach this row from the display via :meth:`Tree.detach`.

        Unlike :meth:`delete` the row (and its subtree) still exists,
        and :meth:`show` brings it back.
        """
        self._tree.detach(self)

    def show(self) -> None:
        """Reattach a hidden row via :meth:`Tree.reattach`.

        Restores the old position as closely as the current tree
        allows; a no-op unless the row was detached through the
        wrapper.
        """
        self._tree.reattach(self)

    def reveal(self) -> None:
        """Open every closed ancestor so this row is not collapsed.

        Never scrolls, so the row may remain off screen —
        :meth:`Tree.see` scrolls as well — and a detached row stays
        hidden regardless.
        """
        for ancestor in self.iter_ancestors():
            if not ancestor.is_open:
                ancestor.is_open = True

    def open(self) -> None:
        """Expand the row (``is_open = True``)."""
        self.is_open = True

    def collapse(self) -> None:
        """Collapse the row (``is_open = False``)."""
        self.is_open = False

    # --------
    # Deletion
    # --------

    def delete(self) -> None:
        """Permanently delete this row; delegates to :meth:`Tree.delete`."""
        self._tree.delete(self)

    # -----------
    # Convenience
    # -----------

    def insert_child(
        self,
        iid: str | None = None,
        *,
        index: int | Literal["end"] = "end",
        **kwargs: Any,
    ) -> TreeRow:
        """Insert a new row as a child of this one.

        Convenience over :meth:`Tree.insert` with ``parent`` preset;
        everything else passes through.

        Args:
            iid (str | None): The new item's iid. Defaults to None,
                meaning Tk generates one; a duplicate raises.
            index (int | Literal["end"]): Position among this row's
                children. Defaults to "end", meaning after the last
                child.
            **kwargs (Any): Remaining :meth:`Tree.insert` options —
                ``text``, ``image``, ``is_open``, ``tags``,
                ``values``, and per-column value kwargs.

        Returns:
            The newly inserted child row.

        Raises:
            tk.TclError: If ``iid`` is already in use, as with
                :meth:`Tree.insert`.
        """
        return self._tree.insert(iid, parent=self, index=index, **kwargs)
