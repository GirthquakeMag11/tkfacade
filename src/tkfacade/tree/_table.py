"""A flat, spreadsheet-like Tree: no child rows, click-to-sort headings."""

import bisect
import concurrent.futures
import contextlib
import tkinter as tk
from collections.abc import Mapping, Sequence
from dataclasses import replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Unpack

from .._command import dispatch_command
from .._params import TreeColumnOptions
from .._types import Command
from ..look import Look
from ..media import ImageInput
from ..observable import ObservableStr
from ..scroll import ScrollbarSpec
from ._column import TreeColumn, TreeColumnSpec
from ._row import TreeRow
from ._tree import Tree
from ._types import ROOT

if TYPE_CHECKING:
    from .._subscription import Subscription
    from ..widget import BaseWidget
    from ._column import TreeColumnHeading


class SortingMode(StrEnum):
    """A heading's sort state; each value is its arrow glyph (or none).

    U+25B2/U+25BC (▲/▼, Unicode 1.1) were chosen over U+2BC5/U+2BC6
    (⯅/⯆, Unicode 7.0) for near-universal default-font coverage — and
    checked by rendering both at the interpreter's default UI font, the
    discipline from `media/_player.py`, before the choice was settled.
    A codepoint the font lacks comes out as a hollow box, and
    no width measurement reveals either.
    """

    NONE = ""
    ASCENDING = "▲"
    DESCENDING = "▼"


class _HeadingSortCommander:
    """Sole owner of one Table column's heading.

    Renders the base text plus the sort arrow and cycles the sort when
    the heading is clicked. A user-supplied heading command or text
    observable is composed rather than clobbered: the command runs
    after each click-driven sort cycle, and the observable drives the
    base text, with the arrow suffix re-applied on every external
    write.
    """

    if TYPE_CHECKING:
        _coord: _HeadingSortCoordinator
        _mode: SortingMode
        _base: str
        _col: TreeColumn
        _head: TreeColumnHeading
        _user_observable: ObservableStr | None
        _user_watch: Subscription | None
        _user_command: Command | None
        _user_command_tasks: set[concurrent.futures.Future[Any]]

    def __init__(
        self,
        column: TreeColumn,
        coord: _HeadingSortCoordinator,
        /,
        *,
        user_observable: ObservableStr | None = None,
        user_command: Command | None = None,
    ) -> None:
        """Take over the column's heading and render the initial text.

        The heading's current text (or the observable's value, when
        given and non-empty) becomes the base text, and the heading's
        click command is replaced with the sort cycle.

        Args:
            column (TreeColumn): The column whose heading to own.
            coord (_HeadingSortCoordinator): Notified when this
                commander takes the active sort.
            user_observable (ObservableStr | None): User observable
                driving the base text. Defaults to None.
            user_command (Command | None): User command run after each
                click-driven sort cycle, of either kind. Defaults to
                None.
        """
        self._coord = coord
        self._col = column
        self._head = column.heading
        self._mode = SortingMode.NONE
        self._user_command = user_command
        self._user_command_tasks = set()
        self._user_observable = user_observable
        self._user_watch = None
        if user_observable is not None:
            self._base = user_observable.value or self._head.text
            if not user_observable.value:
                user_observable.value = self._base
        else:
            self._base = self._head.text
        self._head.command = self.cycle
        self.render()
        if user_observable is not None:
            self._user_watch = user_observable.watch(self._on_user_write)

    def adopt_observable(self, observable: ObservableStr | None, /) -> None:
        """Install (or remove) the user observable driving the base text.

        Any prior observable's watch is cancelled first. A new
        observable's value becomes the base text — an empty one is
        seeded with the current base instead, the same promise the
        spec doors keep — and the heading re-renders, arrow intact.
        None removes the observable and the heading keeps its last
        base.

        Args:
            observable (ObservableStr | None): The driving observable,
                or None to release the current one.
        """
        if self._user_watch is not None:
            self._user_watch.cancel()
            self._user_watch = None
        self._user_observable = observable
        if observable is None:
            self.render()
            return
        self._base = observable.value or self._base
        if not observable.value:
            observable.value = self._base
        self._user_watch = observable.watch(self._on_user_write)

    def _on_user_write(self, value: str, /) -> None:
        """Adopt the observable's new value as base text and re-render."""
        self._base = value
        with contextlib.suppress(tk.TclError):
            self.render()

    def _update(self, mode: SortingMode, /) -> None:
        """Enter ``mode``, sort the rows, then render and claim — or none.

        Any mode but NONE sorts first and only then renders the arrow
        and claims the active sort: sorting compares converted values
        and can raise before any row moves, and a claim committed
        first would leave the arrow vouching for an order the rows do
        not have — with every other commander already reset — while
        the next index-less insert bisects an unsorted list. On a
        failed sort the mode rolls back to what it was, which is still
        truthful: nothing moved, so whatever order (and arrow) held
        before still holds.
        """
        if mode is SortingMode.NONE:
            self._mode = mode
            self.render()
            return
        previous = self._mode
        self._mode = mode
        try:
            self._sort()
        except BaseException:
            self._mode = previous
            raise
        self.render()
        self._coord.report_update(self)

    def _sort(self) -> None:
        """Sort the tree by this column in the current direction."""
        Tree.sort_rows(self._col.tree, self._col, self._mode is SortingMode.ASCENDING)

    @property
    def mode(self) -> SortingMode:
        """The sort this heading currently shows."""
        return self._mode

    @property
    def ascending(self) -> bool:
        """Whether the column is sorted smallest first."""
        return self._mode is SortingMode.ASCENDING

    @property
    def descending(self) -> bool:
        """Whether the column is sorted largest first."""
        return self._mode is SortingMode.DESCENDING

    @property
    def active(self) -> bool:
        """Whether this heading holds the table's sort."""
        return self._mode is not SortingMode.NONE

    @property
    def column(self) -> TreeColumn:
        """The column whose heading this commands."""
        return self._col

    def cycle(self) -> None:
        """Advance the sort on heading click, then run the user command.

        A first click sorts descending; further clicks toggle between
        descending and ascending. A sort whose key won't convert
        — cells the table's own ``clear`` and omitted-column leaves
        blank — stands the sort down without raising: a Tk callback
        that escapes is swallowed, and ``_cell_changed`` already
        follows the same catch-and-retire posture for the write path.
        """
        try:
            if self._mode is SortingMode.ASCENDING:
                self._update(SortingMode.DESCENDING)
            elif self._mode is SortingMode.DESCENDING:
                self._update(SortingMode.ASCENDING)
            else:
                self._update(SortingMode.DESCENDING)
        except Exception:
            self._coord.stand_down()
            return
        if self._user_command is not None:
            dispatch_command(
                self._head._treeview,
                self._user_command,
                self._user_command_tasks,
                f"the heading command of column {self._col.name!r}",
            )

    def set_mode_descending(self) -> None:
        """Show the descending arrow, claim the sort, and sort the rows."""
        self._update(SortingMode.DESCENDING)

    def set_mode_ascending(self) -> None:
        """Show the ascending arrow, claim the sort, and sort the rows."""
        self._update(SortingMode.ASCENDING)

    def set_mode_none(self) -> None:
        """Clear the arrow without re-sorting the rows."""
        self._update(SortingMode.NONE)

    def dispose(self) -> None:
        """Give the heading up: unbind the click, drop the watch, restore the text.

        Leaves the heading as a commander never owned it, so a column
        that outlives its commander stops cycling a sort nothing is
        tracking.
        """
        if self._user_watch is not None:
            self._user_watch.cancel()
            self._user_watch = None
        self._mode = SortingMode.NONE
        with contextlib.suppress(tk.TclError):
            self._head.command = None
            self.render()

    def render(self) -> None:
        """Write the base text — plus the arrow while sorting — to the heading."""
        text = self._base
        if self._mode is not SortingMode.NONE:
            text = f"{text} {self._mode}"
        self._head._treeview.heading(self._head._name, text=text)


class _HeadingSortCoordinator:
    """Registry of one commander per column, tracking the active sort.

    When a commander takes the sort, every other commander is reset to
    NONE so only one heading shows an arrow.
    """

    if TYPE_CHECKING:
        _commanders: dict[str, _HeadingSortCommander]
        _active_commander: _HeadingSortCommander | None

    def __init__(self) -> None:
        """Start with no commanders and no active sort."""
        self._commanders = {}
        self._active_commander = None

    def active_column(self) -> TreeColumn | None:
        """Return the column holding the sort, or None when none does."""
        if self._active_commander:
            return self._active_commander.column
        return None

    def active_mode(self) -> SortingMode:
        """Return the active sort's direction; NONE when no sort is active."""
        if self._active_commander:
            return self._active_commander.mode
        return SortingMode.NONE

    def add_commander(
        self,
        column: TreeColumn,
        /,
        *,
        user_observable: ObservableStr | None = None,
        user_command: Command | None = None,
    ) -> None:
        """Register a commander for ``column`` unless one already exists.

        ``user_observable`` and ``user_command`` are passed through to
        :class:`_HeadingSortCommander`; re-adding a column is a no-op,
        so an existing commander's state is never clobbered.
        """
        if column.name not in self._commanders:
            self._commanders[column.name] = _HeadingSortCommander(
                column, self, user_observable=user_observable, user_command=user_command
            )

    def rem_commander(self, column: TreeColumn, /) -> None:
        """Dispose of and forget ``column``'s commander, if any.

        The active-sort slot is cleared when that commander held it.
        """
        commander = self._commanders.pop(column.name, None)
        if commander is None:
            return
        commander.dispose()
        if self._active_commander is commander:
            self._active_commander = None

    def report_update(self, commander: _HeadingSortCommander, /) -> None:
        """Make ``commander`` the active sort; reset all others to NONE."""
        self._active_commander = commander
        for other in self._commanders.values():
            if other is not commander:
                other.set_mode_none()

    def stand_down(self) -> None:
        """Retire the active sort, clearing its arrow but not the row order.

        For a placement the sort did not choose: the rows keep whatever
        order they have been put in, and no heading goes on claiming
        they are sorted by it.
        """
        if self._active_commander is not None:
            self._active_commander.set_mode_none()
            self._active_commander = None


class Table(Tree):
    """A flat, spreadsheet-like :class:`Tree` with click-to-sort headings.

    The tree column is hidden and every row is top-level; creating a
    child row raises TypeError. Clicking a heading sorts descending,
    then toggles direction; the active heading shows an arrow while
    every other heading returns to its bare text. While a sort is
    active, rows inserted without an explicit index are sorted into
    position.

    Appearance is :class:`~tkfacade.Tree`'s: the ``Treeview`` style,
    row text through tags. The sort arrow is the one addition, drawn
    as a leading glyph in the active heading's text.
    """

    __slots__ = ("_heading_coord",)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        columns: Sequence[TreeColumnSpec] = (),
        selection_enabled: bool = True,
        selection_extended: bool = False,
        height: int = 32,
        vertical_scrollbar: bool | ScrollbarSpec = True,
        horizontal_scrollbar: bool | ScrollbarSpec = False,
        look: Look | None = None,
    ) -> None:
        """Build the table and wire a sort commander onto every column.

        Specs are visited inside :meth:`Tree.__init__`, before the
        sort machinery exists, so each spec's heading observable and
        ``heading_command`` are stripped and handed to that column's
        commander instead (see :class:`_HeadingSortCommander`).

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the table
                is created inside.
            columns (Sequence[TreeColumnSpec]): Column declarations,
                in logical order. Defaults to ``()``.
            selection_enabled (bool): Whether rows can be selected.
                Defaults to True.
            selection_extended (bool): Allow multi-row selection.
                Defaults to False.
            height (int): Height of the widget, in rows. Defaults to
                32.
            vertical_scrollbar (bool): Show a vertical scrollbar.
                Defaults to True.
            horizontal_scrollbar (bool): Show a horizontal scrollbar.
                Defaults to False.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        ordered = tuple(columns)
        stripped = tuple(
            replace(
                spec,
                heading_text=None
                if isinstance(spec.heading_text, ObservableStr)
                else spec.heading_text,
                heading_command=None,
            )
            if isinstance(spec.heading_text, ObservableStr) or spec.heading_command is not None
            else spec
            for spec in ordered
        )
        super().__init__(
            parent,
            columns=stripped,
            show_tree_column=False,
            show_column_headings=True,
            selection_enabled=selection_enabled,
            selection_extended=selection_extended,
            height=height,
            vertical_scrollbar=vertical_scrollbar,
            horizontal_scrollbar=horizontal_scrollbar,
        )
        self._heading_coord: _HeadingSortCoordinator = _HeadingSortCoordinator()
        for spec in ordered:
            column = self.column(spec.name)
            assert column is not None
            heading = spec.heading_text
            self._heading_coord.add_commander(
                column,
                user_observable=heading if isinstance(heading, ObservableStr) else None,
                user_command=spec.heading_command,
            )
        if look is not None:
            self.look = look

    def _sort_in(self, row: TreeRow, /) -> None:
        """Move ``row`` to the position the active sort would give it.

        A no-op when no sort is active. The search is a binary one, so
        it relies on the other rows already standing in the active
        sort's order — every placement the sort did not choose retires
        it (:meth:`move`, :meth:`insert` with an explicit index,
        :meth:`reattach`), rather than leaving a sort marked active
        over rows it no longer describes.

        Args:
            row (TreeRow): The row to place. Compared by its converted
                value in the sorted column, so it can raise for the
                same reasons a heading-click sort can.
        """
        if (column := self._heading_coord.active_column()) is None:
            return
        mode = self._heading_coord.active_mode()
        if mode is SortingMode.NONE:
            return

        name = column.name
        value = row[name]
        siblings = [r for r in self.roots if r.iid != row.iid]

        if mode is SortingMode.ASCENDING:
            position = bisect.bisect_right(siblings, value, key=lambda r: r[name])

        elif mode is SortingMode.DESCENDING:
            reversed_pos = bisect.bisect_left(siblings[::-1], value, key=lambda r: r[name])
            position = len(siblings) - reversed_pos

        self._move(row, ROOT, position)

    def _set_heading_observable(self, name: str, observable: ObservableStr | None, /) -> None:
        """Compose a heading text observable into the sort machinery.

        On a commanded column the observable drives the commander's
        *base* text — seeded when empty, arrow re-applied on every
        write, exactly as the spec/:meth:`add_column` doors compose
        it — where the raw watch the plain-Tree funnel installs would
        fight the commander over the heading: the assignment wiping
        the arrow, a click clobbering the user's text with the stale
        base, each later write clobbering back.
        """
        commander = self._heading_coord._commanders.get(name)
        if commander is None:
            super()._set_heading_observable(name, observable)
        else:
            commander.adopt_observable(observable)

    def _set_heading_command(self, name: str, command: Command | None, /) -> None:
        """Compose a heading command into the sort machinery.

        The commander promises a user-supplied command "is composed
        rather than clobbered", and the spec/:meth:`add_column` door
        keeps that promise — this keeps it at the property door too:
        on a commanded column the command becomes the user command
        run after each click-driven sort cycle (None removes it), and
        the cycle itself stays installed. The commander's own
        lifecycle writes pass through here while it is unregistered —
        installing its cycle before registration, restoring at
        dispose after deregistration — and so reach the plain tree's
        funnel, as they must.
        """
        commander = self._heading_coord._commanders.get(name)
        if commander is None:
            super()._set_heading_command(name, command)
        else:
            commander._user_command = command

    def _get_heading_command(self, name: str, /) -> Command | None:
        """Answer what the property door holds: the *user* command.

        On a commanded column the cycle is the machinery, not the
        caller's command — what was assigned is what reads back.
        """
        commander = self._heading_coord._commanders.get(name)
        if commander is None:
            return super()._get_heading_command(name)
        return commander._user_command

    def _set_heading_text(self, name: str, text: str, /) -> None:
        """Route a heading text write into the commander's base.

        On a commanded column the commander is the heading's sole
        owner — it holds the base text and appends the sort arrow on
        render — so a plain Tk write would strip the arrow off an
        active sort and be overwritten on the next render. This routes
        the write into the commander's base the way the observable and
        command doors already do.
        """
        coordinator: _HeadingSortCoordinator | None = getattr(self, "_heading_coord", None)
        if coordinator is None:
            super()._set_heading_text(name, text)
            return
        commander = coordinator._commanders.get(name)
        if commander is None:
            super()._set_heading_text(name, text)
        else:
            commander._base = text
            commander.render()

    def _cell_changed(self, iid: str, name: str | None, /) -> None:
        """Keep an active sort honest over a cell write.

        A write to the actively-sorted column changes the very key the
        arrow vouches for, so the changed row is sorted back into
        place — the same maintenance an index-less insert gets. A
        value the sort cannot order (an unconvertible blank from
        ``clear``, say) retires the sort instead, exactly as a failed
        insert sort-in does: the write itself has already landed, so
        the failure is not re-raised. Writes to unsorted columns, and
        to detached rows, change no displayed order and do nothing.
        """
        column = self._heading_coord.active_column()
        if column is None:
            return
        if name is not None and name != column.name:
            return
        if iid in self._detached:
            return
        try:
            self._sort_in(self._row(iid))
        except Exception:
            self._heading_coord.stand_down()

    def add_column(
        self,
        name: str,
        index: int | None = None,
        /,
        **options: Unpack[TreeColumnOptions],
    ) -> TreeColumn:
        """Append (or insert) a column with sort-aware heading wiring.

        A ``heading_text`` observable and a ``heading_command`` are
        composed into the sort machinery rather than installed
        directly (see :class:`_HeadingSortCommander`), so they are
        withheld from the base call; everything else — a plain-string
        ``heading_text`` included — defers to :meth:`Tree.add_column`,
        which preserves existing cell data.

        Args:
            name (str): The new column's logical name.
            index (int | None): Logical position to insert at.
                Defaults to None, meaning append at the end.
            **options (Unpack[TreeColumnOptions]): The column's
                configuration; see :meth:`Tree.add_column`. A
                ``heading_text`` observable drives the heading's
                *base* text, to which the sort arrow is appended, and
                ``heading_command`` runs after each click-driven sort
                cycle rather than instead of it.

        Returns:
            The new live column.

        Raises:
            ValueError: If a column named ``name`` already exists.
            TypeError: If ``default_factory`` is not callable.
        """
        heading = options.get("heading_text")
        heading_observable = heading if isinstance(heading, ObservableStr) else None
        if heading_observable is not None:
            options.pop("heading_text")
        heading_command = options.pop("heading_command", None)
        column = super().add_column(name, index, **options)
        self._heading_coord.add_commander(
            column, user_observable=heading_observable, user_command=heading_command
        )
        return column

    def drop_column(self, key: str | int) -> None:
        """Remove a column, retiring its sort commander first.

        The commander goes before the column so it can put the heading
        back as it found it; the surviving headings, arrows included,
        are carried across the reconfigure by :meth:`Tree.drop_column`.
        No-op when ``key`` names no column.

        Args:
            key (str | int): The column's name or logical index.
        """
        column = self.column(key)
        if column is None:
            return
        self._heading_coord.rem_commander(column)
        super().drop_column(key)

    def sort_rows(self, column: TreeColumn, ascending: bool = True, recurse: bool = False) -> None:
        """Sort by ``column`` through the heading sort machinery.

        Keeps the arrow indicator and insert-time sorting in step with
        programmatic sorts; a column with no commander falls back to
        :meth:`Tree.sort_rows`. ``recurse`` is moot on a flat table.

        Raises:
            KeyError: If ``column`` belongs to another tree — the
                commander is resolved by bare name, which any table
                built from the same specs shares.
        """
        if column.tree is not self:
            raise KeyError(column)
        commander = self._heading_coord._commanders.get(column.name)
        if commander is None:
            super().sort_rows(column, ascending, recurse)
        elif ascending:
            commander.set_mode_ascending()
        else:
            commander.set_mode_descending()

    def move(
        self,
        row: TreeRow | str,
        parent: TreeRow | str = ROOT,
        index: int | Literal["end"] = "end",
    ) -> None:
        """Reorder a row among the top-level rows, retiring any active sort.

        A move puts the rows in an order the sort did not choose, so
        the sort stands down: the arrow goes, the rows stay where this
        call leaves them, and later inserts append rather than sorting
        in until a sort is asked for again.

        Args:
            row (TreeRow | str): The row (or iid) to move.
            parent (TreeRow | str): Must resolve to the root. Defaults
                to ``ROOT``.
            index (int | Literal["end"]): Target position. Defaults to
                ``"end"``.

        Raises:
            TypeError: If ``parent`` is not the root — a Table has no
                child rows.
        """
        if self._iid(parent) != ROOT:
            raise TypeError("tkfacade.Table does not support child rows")
        super().move(row, parent, index)
        self._heading_coord.stand_down()

    def reattach(self, *rows: TreeRow | str) -> None:
        """Relink previously detached rows, retiring any active sort.

        The restored position is the recorded one, not one the sort
        chose — the same reason :meth:`move` and an explicit-index
        :meth:`insert` retire it — so no heading goes on claiming an
        order the restored row may no longer stand in. A call that
        restores nothing retires nothing.

        Args:
            *rows (TreeRow | str): The rows (or iids) to restore.
        """
        restored = any(self._iid(row) in self._detached for row in rows)
        super().reattach(*rows)
        if restored:
            self._heading_coord.stand_down()

    def insert(
        self,
        iid: str | None = None,
        *,
        text: str = "",
        image: ImageInput | None = None,
        parent: TreeRow | str = ROOT,
        index: int | Literal["end"] | None = None,
        is_open: bool = False,
        tags: str | tuple[str, ...] = (),
        values: Mapping[str, Any] | None = None,
        **value_kwargs: Any,
    ) -> TreeRow:
        """Insert a top-level row, sorting it in when a sort is active.

        With no explicit ``index``, an actively sorted table sorts the
        new row into position; an explicit ``index`` (including an
        explicit ``"end"``) is honored as given, and retires the sort
        for the same reason :meth:`move` does — the row lands where the
        sort would not have put it, so no heading goes on claiming the
        table is ordered by it. Sorting-in compares the new row's
        converted value against the others, so — like a heading-click
        sort — it can raise when the values don't order (e.g. the sort
        column was omitted and its empty cell doesn't convert); the row
        then remains appended at the end and the sort stands down, for
        the same reason as everywhere else — the row stands where the
        sort would not have put it.

        Raises:
            TypeError: If ``parent`` is not the root — a Table has no
                child rows.
        """
        if self._iid(parent) != ROOT:
            raise TypeError("tkfacade.Table does not support the creation of child rows")
        row = super().insert(
            iid,
            text=text,
            image=image,
            parent=parent,
            index="end" if index is None else index,
            is_open=is_open,
            tags=tags,
            values=values,
            **value_kwargs,
        )
        if index is None:
            try:
                self._sort_in(row)
            except BaseException:
                self._heading_coord.stand_down()
                raise
        else:
            self._heading_coord.stand_down()
        return row
