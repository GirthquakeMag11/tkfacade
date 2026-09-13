"""The Treeview wrapper proper: :class:`Tree` and its option helpers.

:class:`Tree` wraps a ``ttk.Treeview`` behind typed :class:`TreeRow`
and :class:`TreeColumn` handles, with columns addressed by name rather
than position and cell values translated through per-column
converters. :func:`_show_param` and :func:`~tkfacade._utils.select_param` fold the
wrapper's boolean options into Tk's composite ``show`` and
``selectmode`` literals.
"""

import concurrent.futures
import contextlib
import tkinter as tk
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from tkinter import ttk
from typing import Any, Final, Literal, Unpack, cast

from .._command import dispatch_command
from .._params import TreeColumnOptions
from .._sentinels import OMIT, Omitted
from .._subscription import Subscription
from .._types import Command
from .._utils import select_param
from ..events import ACTIVATED
from ..look import Look
from ..media import ImageInput, ImageWrapper, PhotoImage
from ..observable import ObservableStr
from ..scroll import AbstractScrollable, ScrollbarSpec
from ..widget import BaseWidget
from ._column import TreeColumn, TreeColumnSpec
from ._row import TreeRow
from ._types import ROOT, ColumnConverters, Region, ShowParam

_HEADING_OPTIONS: Final[tuple[str, ...]] = ("text", "image", "anchor", "command")
"""The heading options a reconfigure has to carry across, in Tk's own spelling.

Every option ``heading()`` both reports and accepts. It also reports ``state``
and then rejects it as an unknown option, so replaying what it hands back
verbatim fails; this is the filtered set that survives the round trip.
"""

_BODY_OPTIONS: Final[tuple[str, ...]] = ("width", "minwidth", "stretch", "anchor")
"""The column body options a reconfigure has to carry across.

Every option ``column()`` both reports and accepts; ``id`` is reported
too but is the name itself, not an option to write back.
"""


def _show_param(tree: bool, headings: bool) -> ShowParam:
    """Translate two booleans into Tk's ``show`` option literal.

    Args:
        tree (bool): Whether the tree column (``#0``) is visible.
        headings (bool): Whether column headings are visible.

    Returns:
        The matching :data:`ShowParam`; ``""`` when both are False.
    """
    match tree, headings:
        case True, True:
            return "tree headings"
        case True, False:
            return "tree"
        case False, True:
            return "headings"
        case False, False:
            return ""
        case _:
            raise ValueError((tree, headings))


class Tree(AbstractScrollable, Collection[TreeRow]):
    """A ttk.Treeview wrapped with typed column and row handles.

    Rows surface as :class:`TreeRow` and columns as
    :class:`TreeColumn` — thin views over the widget's iids and column
    names, so handles stay valid across restructuring. Columns are
    addressed by name, never display position, and may carry
    converters that translate between Python values and the strings Tk
    stores. Every method taking a row accepts the :class:`TreeRow` or
    its bare iid; a row belonging to another tree raises ``KeyError``
    wherever it is offered.

    The collection face is the tree's rows: a row is reached through
    :meth:`row`, never by subscript. :meth:`__iter__` and
    :meth:`__len__` both speak for the attached rows in screen order,
    while :meth:`__contains__` answers for every row Tk still holds,
    detached ones included.

    Images are given as :data:`~tkfacade.ImageInput` wherever one is
    accepted — on a row (:attr:`TreeRow.image`, :meth:`insert`), on a
    column heading (:attr:`~tkfacade.tree.TreeColumnHeading.image`), and on
    a tag (:meth:`configure_tag`) — and the tree retains each one, so
    an image set through it is not garbage-collected out of the widget.

    The underlying Tk widget is a ``ttk.Frame`` holding the Treeview
    and any scrollbars, so geometry management targets the whole
    assembly.

    Appearance comes from the ``Treeview`` style, and ``Treeview.Heading``
    for the column headings. Row text is styled through tags rather than
    options, and row height through the style alone (`hazards/tkinter.md`,
    *Styling*).
    """

    __slots__ = (
        "_column_bnames",
        "_column_default_factories",
        "_column_default_values",
        "_column_observables",
        "_column_watches",
        "_converters",
        "_detached",
        "_heading_command_tasks",
        "_heading_commands",
        "_heading_dispatchers",
        "_heading_images",
        "_images",
        "_tag_images",
        "_treeview",
    )

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        columns: Sequence[TreeColumnSpec] = (),
        show_tree_column: bool = False,
        show_column_headings: bool = True,
        selection_enabled: bool = True,
        selection_extended: bool = False,
        height: int = 32,
        vertical_scrollbar: bool | ScrollbarSpec = True,
        horizontal_scrollbar: bool | ScrollbarSpec = False,
        look: Look | None = None,
    ) -> None:
        """Build the tree, its scrollbars, and its initial columns.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the tree
                is created inside.
            columns (Sequence[TreeColumnSpec]): Column declarations,
                applied in order via :meth:`TreeColumnSpec.visit`.
                Defaults to ``()``.
            show_tree_column (bool): Whether the tree column (``#0``)
                is visible. Defaults to False, meaning a flat table
                look.
            show_column_headings (bool): Whether column headings are
                visible. Defaults to True.
            selection_enabled (bool): Whether rows can be selected at
                all. Defaults to True.
            selection_extended (bool): Whether multiple rows may be
                selected at once; ignored when ``selection_enabled``
                is False. Defaults to False.
            height (int): Rows visible without scrolling. Defaults to
                32.
            vertical_scrollbar (bool | ScrollbarSpec): Whether a vertical scrollbar
                sits in the right gutter. Defaults to True.
            horizontal_scrollbar (bool | ScrollbarSpec): Whether a horizontal
                scrollbar sits in the bottom gutter. Defaults to
                False.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If two columns share a name — the uniqueness
                :meth:`add_column` enforces thereafter — or if every
                column is declared hidden — Tk requires at least one
                displayed column, the invariant :meth:`hide_column`
                keeps thereafter.
        """
        ordered = tuple(columns)
        names = tuple(col.name for col in ordered)
        for index, name in enumerate(names):
            if name in names[:index]:
                raise ValueError(f"column {name!r} is declared twice")
        self._tk: ttk.Frame = ttk.Frame(self._as_master(parent))
        shown = tuple(col.name for col in ordered if col.displayed is not False)
        if names and not shown:
            raise ValueError(
                "every column is declared hidden, and Tk requires at least one displayed"
            )
        self._treeview: ttk.Treeview = ttk.Treeview(
            self._tk,
            columns=names,
            displaycolumns=shown if len(shown) < len(names) else "#all",
            show=_show_param(tree=show_tree_column, headings=show_column_headings),
            selectmode=select_param(enabled=selection_enabled, extended=selection_extended),
            height=height,
        )
        self._build_gutters(
            self._treeview, vertical=vertical_scrollbar, horizontal=horizontal_scrollbar
        )
        self._images: dict[str, ImageWrapper] = {}
        self._heading_images: dict[str, ImageWrapper] = {}
        self._tag_images: dict[str, ImageWrapper] = {}
        self._heading_commands: dict[str, Command] = {}
        self._heading_dispatchers: dict[str, Callable[[], None]] = {}
        self._heading_command_tasks: set[concurrent.futures.Future[Any]] = set()
        self._converters: dict[str, ColumnConverters] = {}
        self._detached: dict[str, tuple[str, int]] = {}
        self._column_bnames: dict[str, str] = {}
        self._column_default_values: dict[str, Any] = {}
        self._column_default_factories: dict[str, Callable[[], Any]] = {}
        self._column_observables: dict[str, ObservableStr] = {}
        self._column_watches: dict[str, Subscription] = {}
        for col in ordered:
            col.visit(self)
        for col in ordered:
            self._ensure_heading_dispatcher(col.name)
        super().__init__()
        self._route_events(self._treeview, *self._scroll_bars.values())
        if look is not None:
            self.look = look

    def __iter__(self) -> Iterator[TreeRow]:
        """Iterate over every attached row, in screen order."""
        return self.walk(ROOT)

    def __contains__(self, item: object) -> bool:
        """Whether ``item`` — a row or a bare iid — exists in the tree.

        A :class:`TreeRow` is checked for identity, not just its iid:
        another tree's row answers False however its iid reads, since
        Tk hands every tree the same generated ``I001``, ``I002``, …
        names and row identity includes the tree.
        """
        owner = getattr(item, "tree", None)
        if owner is not None and owner is not self:
            return False
        iid = getattr(item, "iid", item)
        return isinstance(iid, str) and self._treeview.exists(iid)

    def __len__(self) -> int:
        """The number of attached rows."""
        return sum(1 for _ in self._iter_subtree(ROOT, include_start=False))

    def _converters_for(self, name: str, /) -> ColumnConverters:
        """Return the named column's converter pair, created on first use.

        The registry entry itself, handed back live: mutating it
        installs converters for the column, which is what
        :attr:`TreeColumn.incoming_converter` and its outgoing twin
        write through. Those are where a caller says what it wants;
        this is the bookkeeping underneath them.

        Args:
            name (str): The column's formal name.

        Returns:
            The column's live converter pair.
        """
        return self._converters.setdefault(name, ColumnConverters())

    def _resolve_image(self, arg: ImageInput, /) -> tuple[ImageWrapper, PhotoImage]:
        """Adapt an image source into the wrapper to retain and the handle Tk takes.

        The one funnel every image this tree accepts passes through —
        a row's, a column heading's, a tag's. A wrapper handed in is
        answered with as given rather than copied, so rows sharing an
        icon share its pixels and its Tk handle; anything else is
        loaded into a new wrapper that owns its own pixels.

        Args:
            arg (ImageInput): The image source; anything
                :class:`~tkfacade.media.ImageWrapper` accepts. Callers spell
                "no image" themselves, since a row and a heading clear
                on None where :meth:`configure_tag` leaves the option
                alone.

        Returns:
            The wrapper to store, and its first frame as a handle on
            this tree's interpreter. An animation contributes frame 0
            only — a Treeview cell has nothing that plays one.
        """
        wrapper = arg if isinstance(arg, ImageWrapper) else ImageWrapper(arg)
        return wrapper, wrapper.photo_for(self._treeview)

    def _release_heading_observable(self, name: str, /) -> None:
        """Cancel the named column's heading watch, if any.

        Idempotent, so teardown order does not matter — and pure
        Python, where the trace it replaced could meet a dead
        interpreter.
        """
        watch = self._column_watches.pop(name, None)
        if watch is None:
            return
        self._column_observables.pop(name)
        watch.cancel()

    def _row(self, iid: str, /) -> TreeRow:
        """Wrap ``iid`` as a :class:`TreeRow` without existence checks.

        Internal fast path for iids already known to be valid.
        """
        return TreeRow(self, iid)

    def _move(
        self,
        row: TreeRow | str,
        parent: TreeRow | str = ROOT,
        index: int | Literal["end"] = "end",
    ) -> None:
        """Perform the move itself, without whatever :meth:`move` means to a subclass.

        The mechanism behind :meth:`move`, split from it so that this
        class's own reordering — :meth:`sort_rows` — does not go
        through an override written for the caller's sake.
        :class:`Table`'s ``move`` retires the active sort, which a sort
        putting its own rows in order must not trigger.
        """
        iid = self._iid(row)
        self._detached.pop(iid, None)
        self._treeview.move(iid, self._iid(parent), index)

    def _iter_subtree(self, iid: str, *, include_start: bool = True) -> Iterator[str]:
        """Yield ``iid`` and all attached descendants, depth-first pre-order.

        :data:`ROOT` is never yielded even when ``include_start`` is
        True — the root sentinel is not a real item.

        Args:
            iid (str): The subtree's top item.
            include_start (bool): Whether ``iid`` itself leads the
                walk. Defaults to True.

        Yields:
            Each iid, in screen order.
        """
        if include_start and iid != ROOT:
            yield iid
        for child in self._treeview.get_children(iid):
            yield from self._iter_subtree(child)

    def _iter_detached_iids(self) -> Iterator[str]:
        """Yield every detached row's iid, its own descendants included.

        Enumerated from the detach record, since the root's children do
        not include detached rows. Rows detached by reaching past the
        wrapper into :attr:`treeview` are on no record and cannot be
        found at all, and a record left stale the same way is skipped
        rather than walked.

        Yields:
            Each iid, in detach order.
        """
        for iid in self._detached:
            if self._treeview.exists(iid):
                yield from self._iter_subtree(iid)

    def _iter_every_iid(self) -> Iterator[str]:
        """Yield every item's iid, detached subtrees included.

        Repeats an iid only where the wrapper has been bypassed: a row
        reattached through :attr:`treeview` directly keeps its detach
        record and is then reachable both ways. Detaching a child
        before its parent does not do it — Tk unlinks a detached row
        from its parent's child list, so walking the parent never
        reaches it a second time. Callers wanting each row once
        collect into something keyed by iid.

        Yields:
            Each iid; attached rows first, in screen order.
        """
        yield from self._iter_subtree(ROOT)
        yield from self._iter_detached_iids()

    def _reconfigure_columns(self, names: Sequence[str], /) -> None:
        """Replace the tree's columns with ``names``, keeping cells and headings.

        Tk drops every cell, heading and body option when ``columns``
        is reconfigured, so all three are snapshotted first and written
        back by name — for detached rows as well as attached ones. A
        column named in ``names`` but new to the tree comes out blank;
        one absent from ``names`` loses its values, which is how a
        dropped column is discarded. Hidden columns stay hidden.

        Args:
            names (Sequence[str]): The tree's new column names, in
                logical order.

        Raises:
            ValueError: If ``names`` is non-empty but every one of
                them is hidden — the zero-displayed state the
                constructor and :meth:`hide_column` refuse — checked
                before anything is touched.
        """
        disp = self._treeview.cget("displaycolumns")
        items: tuple[str, ...] = (disp,) if isinstance(disp, str) else tuple(str(d) for d in disp)
        explicit = items != ("#all",)
        surviving = tuple(name for name in items if name in set(names))
        if explicit and names and not surviving:
            raise ValueError(
                "every remaining column is hidden, and Tk requires at least one displayed"
            )
        snapshot = {
            iid: dict(cast(dict[str, str], self._treeview.set(iid)))
            for iid in self._iter_every_iid()
        }
        existing = {col.name for col in self.columns}
        headings = {
            name: {
                option: cast(dict[str, str], self._treeview.heading(name))[option]
                for option in _HEADING_OPTIONS
            }
            for name in names
            if name in existing
        }
        bodies = {
            name: {
                option: cast(dict[str, Any], self._treeview.column(name))[option]
                for option in _BODY_OPTIONS
            }
            for name in names
            if name in existing
        }
        if explicit:
            self._treeview["displaycolumns"] = surviving if surviving else "#all"
        self._treeview["columns"] = tuple(names)
        if explicit and surviving:
            self._treeview["displaycolumns"] = surviving
        for iid, values in snapshot.items():
            for name in names:
                self._treeview.set(iid, name, values.get(name, ""))
        for name, options in headings.items():
            self._treeview.heading(name, **options)
        for name, options in bodies.items():
            self._treeview.column(name, **options)
        for name in names:
            self._ensure_heading_dispatcher(name)

    # -------
    # Columns
    # -------

    @property
    def columns(self) -> tuple[TreeColumn, ...]:
        """All logical columns, in logical (declaration) order."""
        names = cast(tuple[str, ...], self._treeview.cget("columns") or ())
        return tuple(TreeColumn(self, name) for name in names)

    @property
    def displayed_columns(self) -> tuple[TreeColumn, ...]:
        """The live display order as a tuple; ``#all`` resolves to logical order.

        Normalizes Tk's arity-dependent return (a bare string for one
        column, a tuple otherwise) into a uniform tuple.
        """
        disp = self._treeview.cget("displaycolumns")
        items: tuple[str, ...] = (disp,) if isinstance(disp, str) else tuple(str(d) for d in disp)
        if items == ("#all",):
            return self.columns
        return tuple(TreeColumn(self, name) for name in items)

    # ----
    # Rows
    # ----

    @property
    def rows(self) -> tuple[TreeRow, ...]:
        """Every attached row, depth-first pre-order (screen order)."""
        return tuple(self.walk())

    @property
    def roots(self) -> tuple[TreeRow, ...]:
        """The top-level rows, in order."""
        return tuple(self._row(iid) for iid in self._treeview.get_children(ROOT))

    @property
    def displayed_rows(self) -> tuple[TreeRow, ...]:
        """The rows actually rendered: attached, with every ancestor open.

        Collapsed subtrees are attached but not rendered — that gap
        is what distinguishes this from :attr:`rows`.
        """

        def visible(iid: str) -> Iterator[str]:
            for child in self._treeview.get_children(iid):
                yield child
                if self._treeview.item(child, "open"):
                    yield from visible(child)

        return tuple(self._row(iid) for iid in visible(ROOT))

    # ---------
    # Selection
    # ---------

    @property
    def selection(self) -> tuple[TreeRow, ...]:
        """The currently selected rows, in tree order.

        Tk answers with a depth-first pre-order walk of the tree, not
        with the order in which rows were selected.
        """
        return tuple(self._row(iid) for iid in self._treeview.selection())

    @property
    def focus(self) -> TreeRow | None:
        """The row with keyboard focus, or None. Distinct from selection."""
        iid = self._treeview.focus()
        return self._row(iid) if iid else None

    @focus.setter
    def focus(self, row: TreeRow | str) -> None:
        self._treeview.focus(self._iid(row))

    # -------
    # Columns
    # -------

    def column(self, key: str | int, /) -> TreeColumn | None:
        """Look up a column by name or logical index.

        String keys are first resolved through the bound-name alias
        table, so a column stays reachable under the name it was
        declared with. Negative indices count from the end.

        Args:
            key (str | int): The column's name (or alias) or logical
                index.

        Returns:
            The matching :class:`TreeColumn`, or None when nothing
            matches.

        Raises:
            TypeError: If ``key`` is neither str nor int.
        """
        columns = self.columns
        if isinstance(key, str):
            if key in self._column_bnames:
                key = self._column_bnames[key]
            return next((col for col in columns if col.name == key), None)
        if isinstance(key, int):
            if -len(columns) <= key < len(columns):
                return columns[key]
            return None
        raise TypeError(f"column key must be str or int, not {type(key).__name__}")

    def column_index(self, name: str, /) -> int:
        """Return the named column's logical (declaration-order) index.

        The name goes through the bound-name alias table first, as in
        :meth:`column`, so a column answers to the name it was
        declared with either way.

        Args:
            name (str): The column's formal name, or an alias bound to
                it.

        Returns:
            The zero-based logical index.

        Raises:
            ValueError: If no column answers to ``name``.
        """
        names = cast(tuple[str, ...], self._treeview.cget("columns") or ())
        resolved = self._column_bnames.get(name, name)
        if resolved not in names:
            raise ValueError(f"no column named {name!r} on this tree")
        return names.index(resolved)

    def hide_column(self, key: str | int, /) -> TreeColumn | None:
        """Remove a column from the display without dropping its data.

        Only ``displaycolumns`` is edited: the column, its cell
        values, and its registrations are untouched, and
        :meth:`show_column` restores display membership. An
        already-hidden column is left alone.

        Args:
            key (str | int): The column's name or logical index.

        Returns:
            The affected :class:`TreeColumn`, or None when nothing
            matches.

        Raises:
            ValueError: If the column is the last one displayed — Tk
                requires at least one.
        """
        target = self.column(key)
        if target is None:
            return None
        displayed = self.displayed_columns
        if target in displayed:
            if len(displayed) == 1:
                raise ValueError(
                    f"cannot hide {target.name!r}: it is the last displayed "
                    "column, and Tk requires at least one"
                )
            self._treeview["displaycolumns"] = tuple(col.name for col in displayed if col != target)
        return target

    def show_column(self, key: str | int, /) -> TreeColumn | None:
        """Re-display a hidden column.

        The column rejoins the display at its logical position among
        the currently shown columns, not at the end. An
        already-visible column is left alone.

        Args:
            key (str | int): The column's name or logical index.

        Returns:
            The affected :class:`TreeColumn`, or None when nothing
            matches.
        """
        target = self.column(key)
        if target is None:
            return None
        displayed = self.displayed_columns
        if target not in displayed:
            self._treeview["displaycolumns"] = tuple(
                col.name for col in sorted((target, *displayed), key=lambda c: c.index)
            )
        return target

    def add_column(
        self,
        name: str,
        index: int | None = None,
        /,
        **options: Unpack[TreeColumnOptions],
    ) -> TreeColumn:
        """Append (or insert) a column, preserving existing cells and headings.

        Every row's cells survive the reconfigure, detached rows
        included, as does every existing column's heading — both via
        :meth:`_reconfigure_columns`. Configuration goes through
        :meth:`TreeColumnSpec.visit`; the new column's cells start
        empty whatever position it takes. A call that raises leaves
        the tree unchanged: what the spec itself can check is rejected
        before the reconfigure, and an option only Tk can reject rolls
        the added column back out.

        Args:
            name (str): The new column's logical name.
            index (int | None): Logical position to insert at.
                Defaults to None, meaning append.
            **options (Unpack[TreeColumnOptions]): The column's
                configuration, each key a field of
                :class:`TreeColumnSpec`, which documents them and
                supplies the defaults. ``displayed`` is the one
                exception, defaulting to True here rather than to the
                spec's "leave it as it is": a column being added to a
                tree whose displayed set is already narrowed would
                otherwise arrive hidden.

        Returns:
            The new live column.

        Raises:
            ValueError: If a column named ``name`` already exists.
            TypeError: If ``default_factory`` is not callable.
            tk.TclError: If Tk rejects an option's value; the column
                is rolled back out first.
        """
        options.setdefault("displayed", True)
        spec = TreeColumnSpec(name=name, **options)
        names = [col.name for col in self.columns]
        if name in names:
            raise ValueError(f"column {name!r} already exists")
        names.insert(len(names) if index is None else index, name)
        # list.insert clamps, so the true position is read back rather than recomputed
        position = names.index(name)
        self._reconfigure_columns(names)
        try:
            spec.visit(self)
        except BaseException:
            # dropped by logical index, not name: a name resolves through the alias table
            self.drop_column(position)
            raise
        return TreeColumn(self, name)

    def drop_column(self, key: str | int) -> None:
        """Remove a column and all its registrations, keeping other data.

        Converters, name aliases, defaults, the retained heading image,
        and the heading stringvar are all evicted; no-op when ``key``
        names no column. The dropped column's values are discarded,
        while every surviving column keeps its own in every row —
        detached rows included — and its heading, via
        :meth:`_reconfigure_columns`.

        Args:
            key (str | int): The column's name or logical index.

        Raises:
            ValueError: If every remaining column would be hidden —
                the zero-displayed state the constructor and
                :meth:`hide_column` refuse. Nothing is changed:
                registrations are evicted only after the reconfigure
                succeeds, so a refused drop drops nothing.
        """
        column = self.column(key)
        if column is None:
            return
        name = column.name
        self._reconfigure_columns([col.name for col in self.columns if col.name != name])
        self._converters.pop(name, None)
        self._heading_images.pop(name, None)
        self._heading_commands.pop(name, None)
        self._heading_dispatchers.pop(name, None)
        self._release_heading_observable(name)
        self._column_default_values.pop(name, None)
        self._column_default_factories.pop(name, None)
        for alias in [k for k, v in self._column_bnames.items() if v == name]:
            del self._column_bnames[alias]

    # ----
    # Rows
    # ----

    def row(self, key: str | int, /) -> TreeRow | None:
        """Look up a row by iid or screen-order index.

        Integer keys index into :attr:`rows` — depth-first pre-order,
        i.e. what the user sees — not insertion order. Negative
        indices count from the end.

        Args:
            key (str | int): The row's iid or its screen-order index.

        Returns:
            The matching :class:`TreeRow`, or None when nothing
            matches.

        Raises:
            TypeError: If ``key`` is neither str nor int.
        """
        if isinstance(key, str):
            return self._row(key) if self._treeview.exists(key) else None
        if isinstance(key, int):
            rows = self.rows
            if -len(rows) <= key < len(rows):
                return rows[key]
            return None
        raise TypeError(f"row key must be str or int, not {type(key).__name__}")

    def hide_row(self, key: str | int, /) -> TreeRow | None:
        """Detach the row at ``key`` from the display.

        Lookup sugar over :meth:`detach`: the row's data survives and
        its position is remembered for :meth:`show_row`.

        Args:
            key (str | int): The row's iid or screen-order index.

        Returns:
            The affected :class:`TreeRow`, or None when nothing
            matches.
        """
        if (row := self.row(key)) is not None:
            self.detach(row)
        return row

    def show_row(self, key: str | int, /) -> TreeRow | None:
        """Reattach the row at ``key`` near its remembered position.

        Lookup sugar over :meth:`reattach`; rows never hidden through
        :meth:`hide_row`/:meth:`detach` are left alone.

        Args:
            key (str | int): The row's iid. An int indexes attached
                rows only, so it can never address a hidden row —
                only iid addressing is useful here.

        Returns:
            The affected :class:`TreeRow`, or None when nothing
            matches.
        """
        if (row := self.row(key)) is not None:
            self.reattach(row)
        return row

    def sort_rows(self, column: TreeColumn, ascending: bool = True, recurse: bool = False) -> None:
        """Sort top-level rows by their converted value in ``column``.

        Comparison happens *converted* — through the column's outgoing
        converter — so e.g. a numeric converter sorts numerically;
        converted values that do not order against each other raise
        from ``sorted``. Only attached top-level rows participate —
        :attr:`roots` excludes detached rows.

        Args:
            column (TreeColumn): The column whose values order the
                rows.
            ascending (bool): Sort direction. Defaults to True,
                meaning smallest first.
            recurse (bool): Whether every row's children are sorted
                the same way, all the way down. Defaults to False.

        Raises:
            KeyError: If ``column`` belongs to another tree — column
                names are caller-chosen and two trees built from one
                spec list share every name, so a foreign handle would
                silently sort by whatever same-named column this tree
                holds. The same refusal a foreign row gets.
        """
        if column.tree is not self:
            raise KeyError(column)
        name = column.name
        ordered_roots = sorted(
            self.roots,
            key=lambda row: row[name],
            reverse=not ascending,
        )
        for index, row in enumerate(ordered_roots):
            self._move(row, ROOT, index)
            if recurse:
                row.sort_children(column, ascending, recurse)

    # ---------
    # Insertion
    # ---------

    def insert(
        self,
        iid: str | None = None,
        *,
        text: str = "",
        image: ImageInput | None = None,
        parent: TreeRow | str = ROOT,
        index: int | Literal["end"] = "end",
        is_open: bool = False,
        tags: str | tuple[str, ...] = (),
        values: Mapping[str, Any] | None = None,
        **value_kwargs: Any,
    ) -> TreeRow:
        """Insert a new item and return its :class:`TreeRow`.

        Column data is keyword-addressable: pass a ``values`` mapping,
        column-name keyword arguments, or both — keywords win on
        conflict. Names go through the bound-name alias table, column
        defaults fill anything unspecified, and each value passes
        through its column's incoming converter; columns still
        unaccounted for get ``""``, and names matching no declared
        column are silently discarded. Columns whose names collide
        with insert's own parameters must be passed via ``values``.

        Args:
            iid (str | None): Item id for the new row. Defaults to
                None, meaning Tk generates one; a duplicate raises
                ``tk.TclError``.
            text (str): Text for the tree column (``#0``). Defaults
                to ``""``.
            image (ImageInput | None): Image for the tree column;
                anything :class:`~tkfacade.media.ImageWrapper` accepts, a
                wrapper included — which is stored as given rather than
                copied. Defaults to None, meaning no image. What is
                stored is reachable again as :attr:`TreeRow.image`, and
                is referenced strongly, since Tk holds an image only by
                name and the Python object destroys it when collected.
            parent (TreeRow | str): The parent row (or its iid) to
                insert under. Defaults to :data:`ROOT`, the invisible
                root item.
            index (int | Literal["end"]): Position among the parent
                row's children. Defaults to ``"end"``.
            is_open (bool): Whether the new row starts expanded.
                Defaults to False.
            tags (str | tuple[str, ...]): Tags applied to the row.
                Defaults to ``()``.
            values (Mapping[str, Any] | None): Column values by name.
                Defaults to None.
            **value_kwargs (Any): More column values by name; these
                override ``values`` entries on conflict.

        Returns:
            The freshly inserted row.

        Raises:
            KeyError: If ``parent`` is another tree's row.
            tk.TclError: If ``iid`` is already in use.
        """
        parent_iid = self._iid(parent)
        merged: dict[str, Any] = {**(values or {}), **value_kwargs}
        given: dict[str, Any] = {
            self._column_bnames.get(name, name): value for name, value in merged.items()
        }
        defaults: dict[str, Any] = self._column_default_values | {
            name: factory()
            for name, factory in self._column_default_factories.items()
            if name not in given
        }
        normalized: dict[str, Any] = defaults | given
        value_tuple = tuple(
            col.incoming_converter(normalized[col.name]) if col.name in normalized else ""
            for col in self.columns
        )
        wrapper, handle = (None, "") if image is None else self._resolve_image(image)
        final_iid: str = self._treeview.insert(
            parent_iid,
            index,
            iid=iid,
            text=text,
            image=handle,
            open=is_open,
            tags=tags,
            values=value_tuple,
        )
        if wrapper is not None:
            self._images[final_iid] = wrapper
        return self._row(final_iid)

    # -------------------
    # Structural mutation
    # -------------------

    def move(
        self,
        row: TreeRow | str,
        parent: TreeRow | str = ROOT,
        index: int | Literal["end"] = "end",
    ) -> None:
        """Move a row under ``parent`` at ``index``.

        Reparenting and sibling reordering both go through here. Moving
        a detached row re-attaches it at its new position, leaving
        :meth:`reattach` nothing to restore.

        Args:
            row (TreeRow | str): The row (or iid) to move.
            parent (TreeRow | str): The destination parent row (or
                its iid). Defaults to :data:`ROOT`.
            index (int | Literal["end"]): Position among the new
                parent row's children. Defaults to ``"end"``.
        """
        self._move(row, parent, index)

    def detach(self, *rows: TreeRow | str) -> None:
        """Unlink rows from the display without deleting them.

        Each row's former parent and sibling index are recorded so
        :meth:`reattach` can restore it; rows that already have a
        detach record are skipped so the recorded position is never
        overwritten. A detached subtree keeps its data but drops out
        of traversal.

        Args:
            *rows (TreeRow | str): The rows (or iids) to detach.
        """
        for row in rows:
            iid = self._iid(row)
            if iid in self._detached:
                continue
            self._detached[iid] = (
                self._treeview.parent(iid),
                self._treeview.index(iid),
            )
            self._treeview.detach(iid)

    def reattach(self, *rows: TreeRow | str) -> None:
        """Relink previously detached rows near their old positions.

        Rows without a detach record are skipped; a vanished former
        parent row falls back to the root; a stale sibling index is
        clamped to the current end.

        Args:
            *rows (TreeRow | str): The rows (or iids) to restore.
        """
        for row in rows:
            iid = self._iid(row)
            entry = self._detached.pop(iid, None)
            if entry is None:
                continue
            parent_iid, index = entry
            if parent_iid != ROOT and not self._treeview.exists(parent_iid):
                parent_iid = ROOT
            index = min(index, len(self._treeview.get_children(parent_iid)))
            self._treeview.reattach(iid, parent_iid, index)

    # --------
    # Deletion
    # --------

    def delete(self, *rows: TreeRow | str) -> None:
        """Permanently delete rows, cascading to their descendants.

        The cascade reaches detached descendants too, all the way down:
        a row detached from inside a deleted subtree goes with it
        rather than surfacing at the root later. A delete Tk refuses
        changes nothing.

        Args:
            *rows (TreeRow | str): The rows (or iids) to delete.

        Raises:
            KeyError: If any of ``rows`` is another tree's row.
            tk.TclError: If any of ``rows`` names no existing item, or
                names the root item.
        """
        targets = [self._iid(row) for row in rows]
        doomed: set[str] = set()
        detached_targets: list[str] = []
        pending = list(targets)
        while pending:
            for descendant in self._iter_subtree(pending.pop()):
                if descendant in doomed:
                    continue
                doomed.add(descendant)
                for iid, (parent_iid, _index) in self._detached.items():
                    if parent_iid == descendant:
                        detached_targets.append(iid)
                        pending.append(iid)
        if targets:
            self._treeview.delete(*targets, *detached_targets)
        for iid in doomed:
            self._images.pop(iid, None)
            self._detached.pop(iid, None)

    def clear(self) -> None:
        """Delete every row, including detached ones.

        Columns and headings survive. Detached items are enumerated
        explicitly because the root's children do not include them;
        all retained image references are dropped.
        """
        doomed = (*self._treeview.get_children(ROOT), *self._detached)
        self._images.clear()
        self._detached.clear()
        if doomed:
            self._treeview.delete(*doomed)

    # ------
    # Lookup
    # ------

    def exists(self, iid: str) -> bool:
        """Whether an item with ``iid`` currently exists in the tree."""
        return self._treeview.exists(iid)

    # ---------
    # Traversal
    # ---------

    def walk(self, start: TreeRow | str = ROOT) -> Iterator[TreeRow]:
        """Walk the attached descendants of ``start``, depth-first pre-order.

        Lazy — do not mutate the tree mid-walk. Detached subtrees are
        unreachable and thus never yielded.

        Args:
            start (TreeRow | str): The row (or iid) whose subtree to
                walk; not itself yielded. Defaults to :data:`ROOT`.

        Yields:
            Each descendant as a :class:`TreeRow`, in screen order.
        """
        for iid in self._iter_subtree(self._iid(start), include_start=False):
            yield self._row(iid)

    # ---------
    # Selection
    # ---------

    def select(self, *rows: TreeRow | str) -> None:
        """Replace the selection with exactly the given rows."""
        self._treeview.selection_set([self._iid(row) for row in rows])

    def add_to_selection(self, *rows: TreeRow | str) -> None:
        """Add the given rows to the selection, keeping the rest."""
        self._treeview.selection_add([self._iid(row) for row in rows])

    def remove_from_selection(self, *rows: TreeRow | str) -> None:
        """Remove the given rows from the selection, keeping the rest."""
        self._treeview.selection_remove([self._iid(row) for row in rows])

    def toggle_selection(self, *rows: TreeRow | str) -> None:
        """Invert each given row's membership in the selection."""
        self._treeview.selection_toggle([self._iid(row) for row in rows])

    # ---------
    # Scrolling
    # ---------

    def see(self, row: TreeRow | str) -> None:
        """Scroll ``row`` into view, opening its ancestors as needed."""
        self._treeview.see(self._iid(row))

    # -----------
    # Hit testing
    # -----------

    def row_at(self, y: int) -> TreeRow | None:
        """Return the row at vertical pixel ``y``, or None."""
        iid = self._treeview.identify_row(y)
        return self._row(iid) if iid else None

    def column_at(self, x: int) -> TreeColumn | None:
        """Return the logical column at horizontal pixel ``x``, or None.

        ``identify_column`` yields a display-relative ``#N``; this resolves it
        through the live display order back to a logical column. ``#0``
        (the tree column) and out-of-range positions map to None.
        """
        col = self._treeview.identify_column(x)
        if not col or col == "#0":
            return None
        idx = int(col[1:]) - 1
        displayed = self.displayed_columns
        if 0 <= idx < len(displayed):
            return displayed[idx]
        return None

    def region_at(self, x: int, y: int) -> Region:
        """Return the element kind at ``(x, y)``."""
        return self._treeview.identify_region(x, y)

    # -------
    # Tagging
    # -------

    def configure_tag(
        self,
        tag: str,
        *,
        foreground: str | Omitted = OMIT,
        background: str | Omitted = OMIT,
        font: str | tuple[Any, ...] | Omitted = OMIT,
        image: ImageInput | Omitted | None = OMIT,
    ) -> None:
        """Set style options for every row carrying ``tag``.

        Only non-None options are forwarded, so repeated calls layer
        rather than reset. Where two of a row's tags set the same
        option, the one configured here first wins; the order the tags
        sit in on the row (:attr:`TreeRow.tags`) does not enter into
        it. Theme dependent: some platforms ignore tag foreground and
        background.

        Args:
            tag (str): The tag to configure.
            foreground (str | Omitted): Text color. Defaults to
                ``OMIT``, meaning leave unchanged; Tk's own ``""``
                resets it.
            background (str | Omitted): Row background color. Defaults
                to ``OMIT``, meaning leave unchanged; Tk's own ``""``
                resets it.
            font (str | tuple[Any, ...] | Omitted): Font name or spec
                tuple. Defaults to ``OMIT``, meaning leave unchanged;
                Tk's own ``""`` resets it.
            image (ImageInput | None | Omitted): Image shown in the
                tree column; anything :class:`~tkfacade.media.ImageWrapper`
                accepts, a wrapper included — which is stored as given
                rather than copied. Defaults to ``OMIT``, meaning leave
                unchanged; None clears the tag's image, as it does on a
                row and a heading. A given image is referenced strongly;
                unlike a row's, it is held until the tree dies or
                another call clears it, there being no event that
                retires a tag.
        """
        opts: dict[str, Any] = {
            key: value
            for key, value in (
                ("foreground", foreground),
                ("background", background),
                ("font", font),
            )
            if value is not OMIT
        }
        wrapper: ImageWrapper | None = None
        if image is None:
            opts["image"] = ""
        elif image is not OMIT:
            wrapper, opts["image"] = self._resolve_image(image)
        if opts:
            self._treeview.tag_configure(tag, **opts)
        if image is None:
            self._tag_images.pop(tag, None)
        elif wrapper is not None:
            self._tag_images[tag] = wrapper

    def tagged(self, tag: str) -> tuple[TreeRow, ...]:
        """Every row carrying ``tag``, attached rows first, in screen order.

        Tk's own tag search walks down from the root and so cannot see
        a detached row; the detached ones are asked individually
        instead, which costs one round trip each and none at all when
        nothing is detached. They follow the attached matches, in
        detach order.

        Args:
            tag (str): The tag to search for.

        Returns:
            The matching rows.
        """
        matches = [
            *self._treeview.tag_has(tag),
            *(iid for iid in self._iter_detached_iids() if self._treeview.tag_has(tag, iid)),
        ]
        return tuple(self._row(iid) for iid in dict.fromkeys(matches))

    def _set_heading_observable(self, name: str, observable: ObservableStr | None, /) -> None:
        """Install (or release) the observable driving a heading's text.

        The funnel behind :attr:`TreeColumnHeading.text_observable`'s
        setter. A plain tree watches the observable and writes the
        heading text; :class:`~tkfacade.Table` overrides this to hand the
        observable to its sort commander, whose rendering would
        otherwise fight the raw watch over the heading. The watch's
        immediate first call is what syncs the heading at install.

        Args:
            name (str): The column's formal name.
            observable (ObservableStr | None): The driving observable;
                None releases any current one, the heading keeping its
                last text.
        """
        self._release_heading_observable(name)
        if observable is None:
            return

        def _update(value: str) -> None:
            with contextlib.suppress(tk.TclError):
                self._treeview.heading(name, text=value)

        self._column_observables[name] = observable
        self._column_watches[name] = observable.watch(_update)

    def _set_heading_command(self, name: str, command: Command | None, /) -> None:
        """Hold (or drop) a heading's click command, installing its dispatcher.

        The funnel behind :attr:`TreeColumnHeading.command`'s setter.
        A plain tree holds the command itself; :class:`~tkfacade.Table`
        overrides this to compose it into the sort machinery instead of
        letting it replace the sort cycle.

        Tk is given a per-column dispatcher that reads the held command
        at click time and runs it per :func:`.dispatch_command` —
        dual-kind, like every command — so a swap never registers a
        second Tcl command, and None leaves the dispatcher installed
        with nothing to run.

        Args:
            name (str): The column's formal name.
            command (Command | None): The click command; None drops it.
        """
        if command is None:
            self._heading_commands.pop(name, None)
        else:
            self._heading_commands[name] = command
        self._ensure_heading_dispatcher(name)

    def _ensure_heading_dispatcher(self, name: str, /) -> None:
        """Install the column's click dispatcher, once per column.

        Installed whether or not a command is held: the dispatcher
        runs the held command when there is one, then emits
        :data:`~tkfacade.ACTIVATED` on the tree with the column in the
        payload — a heading activation is subscribable with no
        command at all. Wired to Tk exactly once, so a command swap
        never registers a second Tcl command (`hazards/tkinter.md`,
        *Bindings*); a columns reconfigure keeps the wiring alive by
        re-applying the heading snapshot, which carries the command.
        """
        if name in self._heading_dispatchers:
            return

        def dispatch() -> None:
            held = self._heading_commands.get(name)
            if held is not None:
                dispatch_command(
                    self._treeview,
                    held,
                    self._heading_command_tasks,
                    f"the heading command of column {name!r}",
                )
            self.emit(ACTIVATED, {"column": TreeColumn(self, name)})

        self._heading_dispatchers[name] = dispatch
        self._treeview.heading(name, command=dispatch)

    def _get_heading_command(self, name: str, /) -> Command | None:
        """Answer the held heading command; the getter's funnel."""
        return self._heading_commands.get(name)

    def _set_heading_text(self, name: str, text: str, /) -> None:
        """Write a heading's display text; the setter's funnel.

        :class:`~tkfacade.Table` overrides this to route the write into
        the sort commander's base text, whose next render re-applies the
        arrow — where a direct Tk write would strip it.
        """
        self._treeview.heading(name, text=text)

    def _get_heading_text(self, name: str, /) -> str:
        """Read a heading's display text; the getter's funnel."""
        return str(self._treeview.heading(name, "text"))

    def _cell_changed(self, iid: str, name: str | None, /) -> None:
        """Hook: a cell value was written through a public mapping face.

        Called by :meth:`TreeRow.__setitem__`, :meth:`TreeRow.clear`
        (with ``name`` None, meaning every column), and
        :meth:`TreeColumn.__setitem__`, after the write landed. A
        plain tree keeps no order to maintain, so this is a no-op;
        :class:`~tkfacade.Table` overrides it to keep an active sort
        honest.
        """

    def _iid(self, row: TreeRow | str) -> str:
        """Coerce a row-or-iid argument to its raw iid string.

        A bare string is trusted as an iid; a :class:`TreeRow` must be
        this tree's own. Tk generates the same ``I001``, ``I002``, …
        names in every tree, so a foreign handle resolving here would
        silently address whatever same-iid row this tree holds — the
        most destructive callers (``delete``, ``move``, the selection
        methods) all funnel through here.

        Raises:
            KeyError: If ``row`` is another tree's row, matching the
                column lookup path's refusal.
        """
        if isinstance(row, str):
            return row
        if row.tree is not self:
            raise KeyError(row)
        return row.iid
