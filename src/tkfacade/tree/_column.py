"""Column-side wrappers: the live column, its heading, and the column spec."""

import contextlib
import tkinter as tk
from collections.abc import Callable, Iterator, MutableMapping
from dataclasses import dataclass
from tkinter import ttk
from typing import TYPE_CHECKING, Any, cast

from .._sentinels import OMIT, Omitted
from .._types import Anchor, Command
from .._utils import to_title_case
from ..media import ImageInput, ImageWrapper
from ..observable import ObservableStr

if TYPE_CHECKING:
    from ._row import TreeRow
    from ._tree import Tree


class TreeColumnHeading:
    """A live view of one column's header cell.

    The heading is a separate Tk object from the column body, reached
    through ``heading()`` rather than ``column()``.
    """

    __slots__ = ("_name", "_tree", "_treeview")

    def __init__(self, column: TreeColumn, /) -> None:
        """Capture the tree, Treeview, and column name the heading belongs to.

        Args:
            column (TreeColumn): The column whose heading this wraps.
        """
        self._tree: Tree = column.tree
        self._treeview: ttk.Treeview = column._tree._treeview
        self._name: str = column.name

    @property
    def text_observable(self) -> ObservableStr | None:
        """The observable driving the heading text, or None when none is.

        Assigning one syncs the heading to it immediately and on every
        later write, releasing any prior observable first; assigning
        None releases it and the heading keeps its last text.

        On a :class:`~tkfacade.Table` the read answers None even while
        an observable drives the heading: the sort commander composes
        the observable into itself as the heading's sole owner, which
        the suite pins as deliberate.
        """
        return self._tree._column_observables.get(self._name)

    @text_observable.setter
    def text_observable(self, observable: ObservableStr | None, /) -> None:
        self._tree._set_heading_observable(self._name, observable)

    @property
    def text(self) -> str:
        """The heading's display text.

        Routed through :meth:`Tree._get_heading_text` so
        :class:`~tkfacade.Table` can intercept the write and route it
        into the sort commander's base text.
        """
        return self._tree._get_heading_text(self._name)

    @text.setter
    def text(self, value: str) -> None:
        self._tree._set_heading_text(self._name, value)

    @property
    def image(self) -> ImageWrapper | None:
        """The wrapper behind the heading's image, or None when none is set.

        The very object the setter was given, not a copy, so an image
        can be read back, transformed and handed elsewhere without
        being unwrapped.

        Assigning any :data:`~tkfacade.ImageInput` replaces what is there
        and retains the wrapper against garbage collection; assigning
        None clears and releases it, as dropping the column does. An
        image written straight onto the heading behind this property's
        back reads as None here, and is not retained.
        """
        return self._tree._heading_images.get(self._name)

    @image.setter
    def image(self, value: ImageInput | None) -> None:
        if value is None:
            self._treeview.heading(self._name, image="")
            self._tree._heading_images.pop(self._name, None)
            return
        wrapper, handle = self._tree._resolve_image(value)
        self._treeview.heading(self._name, image=handle)
        self._tree._heading_images[self._name] = wrapper

    @property
    def anchor(self) -> Anchor:
        """How the heading text is positioned within the header cell."""
        return cast(Anchor, self._treeview.heading(self._name, "anchor"))

    @anchor.setter
    def anchor(self, value: Anchor) -> None:
        self._treeview.heading(self._name, anchor=value)

    @property
    def command(self) -> Command | None:
        """What a click on the heading runs; None is nothing.

        Held by the tree the way the button family holds a command —
        dual-kind: a plain callable on the mainloop or a coroutine
        function on the root's async core.
        Assigning swaps what future clicks run. Coroutine runs already
        in flight from the old command are left to finish — death
        narrows the future, never the present.
        """
        return self._tree._get_heading_command(self._name)

    @command.setter
    def command(self, value: Command | None) -> None:
        self._tree._set_heading_command(self._name, value)


class TreeColumn(MutableMapping[str, Any]):
    """A live view of one logical column; holds no state of its own.

    Two views of the same tree and column name are interchangeable, and
    compare equal by tree and name rather than by cell contents.

    The mapping face is this column's cells, keyed by row iid and
    carrying values through the converters this column owns;
    placement, heading, and body settings are the other facets. A
    lookup also accepts a :class:`TreeRow` or a screen-order index, and
    never adds a key: an iid no row answers to raises rather than
    bringing a row into being, so :meth:`setdefault` can only read and
    removal is refused throughout — :meth:`clear` blanks the cells
    instead.

    Only attached rows are iterated, while lookup and membership answer
    for every row Tk still holds, detached ones included. A dropped
    column reads as an empty mapping, as a deleted row does.
    """

    __slots__ = ("_name", "_tree")

    def __init__(self, tree: Tree, name: str, /) -> None:
        """Wrap column ``name`` of ``tree``; existence is not checked.

        Args:
            tree (Tree): The tree wrapper the column belongs to.
            name (str): The column's logical name.
        """
        self._tree: Tree = tree
        self._name: str = name

    def __eq__(self, other: object) -> bool:
        """Equal when the tree is identical and the column name matches.

        Identity, not contents: :class:`Mapping`'s content equality —
        under which every column of an empty tree would compare equal
        to every other — is deliberately overridden, and :meth:`__hash__`
        with it.
        """
        if not isinstance(other, TreeColumn):
            return NotImplemented
        return self._tree is other._tree and self._name == other._name

    def __hash__(self) -> int:
        """Hash consistently with :meth:`__eq__`."""
        return hash((id(self._tree), self._name))

    def __repr__(self) -> str:
        """The debug form, identifying the column by name."""
        return f"{type(self).__name__}(name={self._name!r})"

    def __getitem__(self, key: TreeRow | str | int) -> Any:
        """Return this column's converted value in the row at ``key``.

        The raw cell passes through :attr:`outgoing_converter`, which
        this column owns; an empty cell round-trips ``""`` through it.
        A detached row answers like any other — Tk keeps its cells —
        even though it is not iterated.

        Args:
            key (TreeRow | str | int): A row, its iid, or its
                screen-order index.

        Returns:
            The cell's converted value.

        Raises:
            KeyError: If the row or the column does not exist, or an
                integer index is out of range.
            TypeError: If ``key`` is not a row, a string, or an
                integer.
        """
        iid = self._iid(key)
        try:
            raw = str(self._tree._treeview.set(iid, self._name))
        except tk.TclError:
            raise KeyError(key) from None
        return self.outgoing_converter(raw)

    def __setitem__(self, key: TreeRow | str | int, value: Any) -> None:
        """Write ``value`` into the row at ``key`` through the incoming converter.

        Args:
            key (TreeRow | str | int): A row, its iid, or its
                screen-order index.
            value (Any): The value to write into the cell.

        Raises:
            KeyError: If the row or the column does not exist, or an
                integer index is out of range.
            TypeError: If ``key`` is not a row, a string, or an
                integer.
        """
        iid = self._iid(key)
        raw = self.incoming_converter(value)
        try:
            self._tree._treeview.set(iid, self._name, raw)
        except tk.TclError:
            raise KeyError(key) from None
        self._tree._cell_changed(iid, self._name)

    def __delitem__(self, key: TreeRow | str | int, /) -> None:
        """Refuse: a row's value cannot be deleted from a column.

        A cell belongs to a row and a column at once, so removing one
        alone would have to mean deleting the whole row — which is
        :meth:`TreeRow.delete`, not a mapping operation — and blanking
        instead would silently break Mapping invariants (the key stays
        present, ``__len__`` unchanged). Set the cell to ``""`` to
        blank it.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "A cell belongs to a row and a column at once and cannot be "
            'deleted from either. Set it to "" explicitly if you want to '
            "blank it, or delete the row itself."
        )

    def __len__(self) -> int:
        """The number of attached rows, hence cells in this column.

        0 once the column is dropped, matching the empty mapping such
        a column reads as everywhere else in this class.
        """
        return len(self._tree) if self.exists else 0

    def __iter__(self) -> Iterator[str]:
        """Iterate over the attached rows' iids, in screen order.

        Detached rows are skipped, agreeing with :meth:`__len__`,
        though their cells stay readable by iid; a dropped column
        iterates nothing.
        """
        if not self.exists:
            return iter(())
        return (row.iid for row in self._tree)

    def __contains__(self, key: object) -> bool:
        """Whether the row at ``key`` has a cell in this column.

        Answers False rather than raising for a key of an unusable
        type, as :meth:`Tree.__contains__` does — and False for
        another tree's row, however its iid reads. A detached row
        still answers True, matching :meth:`__getitem__` rather than
        :meth:`__iter__`.

        Args:
            key (object): A row, its iid, or its screen-order index.
        """
        try:
            iid = self._iid(key)
        # PEP 758: two exception types without parentheses is valid on the 3.14 floor
        except KeyError, TypeError:
            return False
        return self.exists and self._tree.exists(iid)

    def _iid(self, key: object, /) -> str:
        """Resolve a cell key to the iid of the row it names.

        Args:
            key (object): A :class:`TreeRow` of this tree, its iid, or
                its screen-order index. A string is taken as an iid
                and returned unchecked.

        Returns:
            The row's iid.

        Raises:
            KeyError: If an integer index is out of range, or a row of
                another tree is given — Tk generates the same iids in
                every tree, so a foreign handle must not resolve here.
            TypeError: If ``key`` is not a row, a string, or an
                integer.
        """
        if isinstance(key, str):
            return key
        if isinstance(key, int):
            row = self._tree.row(key)
            if row is None:
                raise KeyError(key)
            return row.iid
        iid = getattr(key, "iid", None)
        if isinstance(iid, str):
            if getattr(key, "tree", None) is not self._tree:
                raise KeyError(key)
            return iid
        raise TypeError(f"cell key must be a TreeRow, str, or int, not {type(key).__name__}")

    # --------
    # Identity
    # --------

    @property
    def name(self) -> str:
        """The column's logical name."""
        return self._name

    @property
    def tree(self) -> Tree:
        """The tree wrapper this column belongs to."""
        return self._tree

    @property
    def exists(self) -> bool:
        """Whether the tree still has a column with this name."""
        return self._tree.column(self._name) == self

    # ---------------
    # Converted cells
    # ---------------

    @property
    def data(self) -> dict[str, Any]:
        """A converted snapshot as a plain dict, keyed by row iid."""
        return {iid: self[iid] for iid in self}

    # ---------
    # Placement
    # ---------

    @property
    def index(self) -> int:
        """The column's logical (declaration-order) index."""
        return self._tree.column_index(self._name)

    @property
    def display_index(self) -> int | None:
        """The column's position in the display order, or None when hidden."""
        displayed = self._tree.displayed_columns
        if self in displayed:
            return displayed.index(self)
        return None

    @property
    def displayed(self) -> bool:
        """Whether the column is currently shown."""
        return self in self._tree.displayed_columns

    @displayed.setter
    def displayed(self, value: bool) -> None:
        if value:
            self._tree.show_column(self._name)
        else:
            self._tree.hide_column(self._name)

    # -------
    # Heading
    # -------

    @property
    def heading(self) -> TreeColumnHeading:
        """A fresh live view of this column's header cell."""
        return TreeColumnHeading(self)

    # -------------
    # Body settings
    # -------------

    @property
    def width(self) -> int:
        """The column's current width in pixels."""
        return int(self._tree._treeview.column(self._name, "width"))

    @width.setter
    def width(self, px: int) -> None:
        self._tree._treeview.column(self._name, width=px)

    @property
    def minwidth(self) -> int:
        """The narrowest the column may be squeezed, in pixels."""
        return int(self._tree._treeview.column(self._name, "minwidth"))

    @minwidth.setter
    def minwidth(self, px: int) -> None:
        self._tree._treeview.column(self._name, minwidth=px)

    @property
    def stretch(self) -> bool:
        """Whether the column absorbs extra width when the tree grows."""
        return bool(self._tree._treeview.column(self._name, "stretch"))

    @stretch.setter
    def stretch(self, value: bool) -> None:
        self._tree._treeview.column(self._name, stretch=value)

    @property
    def anchor(self) -> Anchor:
        """How cell values are positioned within the column."""
        return cast("Anchor", str(self._tree._treeview.column(self._name, "anchor")))

    @anchor.setter
    def anchor(self, value: Anchor) -> None:
        self._tree._treeview.column(self._name, anchor=value)

    @property
    def identifier(self) -> str:
        """The column's own logical id, as Tk reports it (read-only)."""
        return str(self._tree._treeview.column(self._name, "id"))

    # ----------
    # Converters
    # ----------

    @property
    def incoming_converter(self) -> Callable[[Any], str]:
        """The converter applied to values written into this column."""
        return self._tree._converters_for(self._name).incoming

    @incoming_converter.setter
    def incoming_converter(self, converter: Callable[[Any], str]) -> None:
        self._tree._converters_for(self._name).incoming = converter

    @property
    def outgoing_converter(self) -> Callable[[str], Any]:
        """The converter applied to values read out of this column."""
        return self._tree._converters_for(self._name).outgoing

    @outgoing_converter.setter
    def outgoing_converter(self, converter: Callable[[str], Any]) -> None:
        self._tree._converters_for(self._name).outgoing = converter

    # ---------------
    # Converted cells
    # ---------------

    def clear(self) -> None:
        """Blank this column's cell in every attached row; the rows remain.

        Blanks are written raw, exactly as an omitted column starts
        out, so :attr:`incoming_converter` is not applied. Detached
        rows keep their values, being no part of the mapping, and a
        dropped column is a no-op. A row that stops existing mid-walk
        is skipped, and the rest are still blanked.
        """
        treeview = self._tree._treeview
        iids: list[str] = []
        with contextlib.suppress(tk.TclError):
            iids.extend(self)
        blanked: str | None = None
        for iid in iids:
            with contextlib.suppress(tk.TclError):
                treeview.set(iid, self._name, "")
                blanked = iid
        if blanked is not None:
            self._tree._cell_changed(blanked, self._name)

    def setdefault(self, key: TreeRow | str | int, default: Any = None, /) -> Any:
        """Return this column's value in the row at ``key``; never inserts.

        A cell exists for every row the tree holds, so there is no
        absent key for a default to fill: a key naming no row cannot be
        brought into being by writing it, and raises instead.
        ``default`` is therefore never returned.

        Args:
            key (TreeRow | str | int): A row, its iid, or its
                screen-order index.
            default (Any): Unused; carried for the
                :class:`MutableMapping` signature. Defaults to None.

        Returns:
            The cell's converted value.

        Raises:
            KeyError: If the row or the column does not exist, or an
                integer index is out of range.
            TypeError: If ``key`` is not a row, a string, or an
                integer.
        """
        return self[key]

    def pop(self, key: TreeRow | str | int, default: Any = None, /) -> Any:
        """Refuse: a cell cannot be removed from a column, only blanked.

        Named here rather than inherited, since
        :class:`MutableMapping`'s version removes by way of
        :meth:`__delitem__` and would answer for a method the caller
        never called.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "A cell belongs to a row and a column at once and cannot be "
            'popped from either. Read it first, then set it to "" to blank '
            "it, or delete the row itself."
        )

    def popitem(self) -> tuple[str, Any]:
        """Refuse: a column has no removable cell to hand back.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "A cell belongs to a row and a column at once and cannot be "
            'popped from either. Read it first, then set it to "" to blank '
            "it, or delete the row itself."
        )

    # ---------
    # Placement
    # ---------

    def hide(self) -> None:
        """Hide the column; delegates to :meth:`Tree.hide_column`."""
        self._tree.hide_column(self._name)

    def show(self) -> None:
        """Show the column; delegates to :meth:`Tree.show_column`."""
        self._tree.show_column(self._name)

    # -------
    # Sorting
    # -------

    def sort_rows(self, ascending: bool = True, recurse: bool = False) -> None:
        """Sort the tree's top-level rows by this column.

        Delegates to the tree's ``sort_rows`` (dispatched virtually,
        so a Table's override applies); values are compared
        *converted*, and rows whose values do not order raise there.

        Args:
            ascending (bool): Sort low-to-high. Defaults to True.
            recurse (bool): Also sort every row's children the same
                way, all the way down. Defaults to False.
        """
        self._tree.sort_rows(self, ascending, recurse)


@dataclass(slots=True, kw_only=True)
class TreeColumnSpec:
    """A column's declared configuration, applied to a live tree by ``visit``.

    Self-contained: every field has a usable default except ``name``.
    The order specs are passed to ``Tree(columns=...)`` is the columns'
    logical order.

    Attributes:
        name (str): The column's logical name.
        displayed (bool | Omitted): Whether the column is shown.
            Defaults to ``OMIT``, meaning leave its visibility as it is
            — which for a column being declared for the first time
            means shown.
        heading_text (str | ObservableStr | None): The heading text —
            a string, or the observable that drives it (an empty
            observable is seeded with the title-cased name). Defaults
            to None, meaning ``to_title_case(name)`` at visit time.
        heading_command (Command | None): Heading click command, of
            either kind. Defaults to None.
        incoming_converter (Callable[[Any], str] | Omitted): Converter
            for values written into the column. Defaults to ``OMIT``,
            keeping the tree's current one.
        outgoing_converter (Callable[[str], Any] | Omitted): Converter
            for values read out of the column. Defaults to ``OMIT``,
            keeping the tree's current one.
        width (int | Omitted): Column width in pixels. Defaults to
            ``OMIT``, meaning leave unchanged.
        minwidth (int | Omitted): Minimum width in pixels. Defaults to
            ``OMIT``, meaning leave unchanged.
        stretch (bool | Omitted): Whether the column absorbs extra
            width. Defaults to ``OMIT``, meaning leave unchanged.
        anchor (Anchor | Omitted): Cell value positioning. Defaults to
            ``OMIT``, meaning leave unchanged.
        default (Any): Value for rows inserted without this column.
            Defaults to ``OMIT``, meaning no default.
        default_factory (Callable[[], Any] | None): Called per insert
            for a default value; ignored when ``default`` is set, but
            still required to be callable either way. Defaults to
            None.
        bound_name (str | None): Extra alias ``insert()`` accepts for
            the column. Defaults to None, meaning the name alone.

    Raises:
        TypeError: If :attr:`default_factory` is set and not callable.
    """

    name: str
    displayed: bool | Omitted = OMIT
    heading_text: str | ObservableStr | None = None  # None -> to_title_case(name) at visit
    heading_command: Command | None = None
    incoming_converter: Callable[[Any], str] | Omitted = OMIT
    outgoing_converter: Callable[[str], Any] | Omitted = OMIT
    width: int | Omitted = OMIT
    minwidth: int | Omitted = OMIT
    stretch: bool | Omitted = OMIT
    anchor: Anchor | Omitted = OMIT
    default: Any = OMIT
    default_factory: Callable[[], Any] | None = None
    bound_name: str | None = None  # extra alias accepted by insert(); None -> name only

    def __post_init__(self) -> None:
        """Reject a non-callable :attr:`default_factory` at the call site."""
        self._check_factory()

    def _check_factory(self) -> None:
        """Raise unless :attr:`default_factory` is unset or callable.

        Checked whether or not :attr:`default` is set: a factory that
        cannot be called is a mistake either way, and one shadowed by a
        default today outlives the default that hid it.

        Raises:
            TypeError: If :attr:`default_factory` is set and not
                callable.
        """
        if self.default_factory is not None and not callable(self.default_factory):
            raise TypeError(
                f"default_factory must be callable, not {type(self.default_factory).__name__}"
            )

    def visit(self, tree: Tree, /) -> None:
        """Apply this spec to a live tree that already has the column.

        Registers the name alias, default, and converters, then pushes
        display options onto the column. Only explicitly set options
        are applied, heading text excepted: it falls back to
        ``to_title_case(name)``, and given as an observable it takes
        over the heading, an empty one seeded with that title-cased
        name first. ``self`` is not mutated and may be applied to any
        number of trees.

        An option only Tk can reject — an anchor string, a width — is
        not caught before writing starts, so a spec applied by hand can
        leave a half-configured column. :meth:`Tree.add_column` rolls
        its own back out instead.

        Args:
            tree (Tree): The tree wrapper to configure; its Treeview
                must already know a column named :attr:`name`.

        Raises:
            KeyError: If the tree has no column named :attr:`name`.
            TypeError: If :attr:`default_factory` is set and not
                callable. Re-checked here rather than trusted from
                construction, since the fields are writable.
            ValueError: If :attr:`bound_name` is another column's name
                or already aliases a different column — resolution
                consults the alias table first, so the write would
                silently shadow the other column.
            tk.TclError: If Tk rejects an option's value.
        """
        self._check_factory()
        column = tree.column(self.name)
        if column is None:
            raise KeyError(f"no column named {self.name!r} on this tree")
        alias = self.bound_name or self.name
        if alias != self.name and any(col.name == alias for col in tree.columns):
            raise ValueError(f"bound_name {alias!r} is another column's name")
        bound_to = tree._column_bnames.get(alias)
        if bound_to is not None and bound_to != self.name:
            raise ValueError(f"{alias!r} is already bound to column {bound_to!r}")
        tree._column_bnames[alias] = self.name
        if self.default is not OMIT:
            tree._column_default_values[self.name] = self.default
        elif self.default_factory is not None:
            tree._column_default_factories[self.name] = self.default_factory
        if self.displayed is not OMIT:
            column.displayed = self.displayed
        heading = self.heading_text
        if isinstance(heading, ObservableStr):
            if not heading.value:
                heading.value = to_title_case(self.name)
            column.heading.text_observable = heading
        else:
            column.heading.text = heading if heading is not None else to_title_case(self.name)
        if self.heading_command is not None:
            column.heading.command = self.heading_command
        if self.incoming_converter is not OMIT:
            column.incoming_converter = self.incoming_converter
        if self.outgoing_converter is not OMIT:
            column.outgoing_converter = self.outgoing_converter
        if self.width is not OMIT:
            column.width = self.width
        if self.minwidth is not OMIT:
            column.minwidth = self.minwidth
        if self.stretch is not OMIT:
            column.stretch = self.stretch
        if self.anchor is not OMIT:
            column.anchor = self.anchor
