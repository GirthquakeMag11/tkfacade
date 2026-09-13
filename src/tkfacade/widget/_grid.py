"""The grid facet: typed delegation to Tk's grid geometry manager."""

import tkinter as tk
from types import EllipsisType
from typing import TYPE_CHECKING, Any, Self, cast, overload

from .._params import GridSetOptions
from .._types import Anchor, GridInfo, Pad, PadValue, Sticky
from ._base import BaseWidget

if TYPE_CHECKING:
    from ._widget import Widget

_GRID_DEFAULTS: dict[str, Any] = {
    "column": 0,
    "columnspan": 1,
    "row": 0,
    "rowspan": 1,
    "ipadx": 0,
    "ipady": 0,
    "padx": 0,
    "pady": 0,
    "sticky": "nsew",
}
"""Options a first :meth:`GridWidget.grid` placement fills in when unnamed."""


class GridContainerWidget(BaseWidget):
    """Container half of the grid facet: managing the grid this widget masters.

    Delegates the ``grid_*`` methods every Tk widget carries — column
    and row configuration, propagation, slave queries. The other role,
    being a slave placed in a master's grid, is :class:`GridWidget`;
    toplevel wrappers stop here, since a toplevel is managed by the
    window manager and can never be a grid slave.
    """

    __slots__ = ()

    def grid_bbox(
        self,
        column: int | None = None,
        row: int | None = None,
        col2: int | None = None,
        row2: int | None = None,
    ) -> tuple[int, int, int, int] | None:
        """Return the bounding box of a range of grid cells.

        Delegates to :meth:`tkinter.Misc.grid_bbox`.

        Args:
            column (int | None): Starting column. Defaults to None,
                meaning the whole grid; must be given together with
                ``row``.
            row (int | None): Starting row. Defaults to None; must be
                given together with ``column``.
            col2 (int | None): Ending column, inclusive. Defaults to
                None, meaning the same as ``column``; requires
                ``column`` and ``row``.
            row2 (int | None): Ending row, inclusive. Defaults to
                None, meaning the same as ``row``; requires ``column``
                and ``row``.

        Returns:
            A ``(x, y, width, height)`` tuple in pixels; an empty
            range reports a zero-sized box. None only if Tk reports
            nothing, which current Tk does not do.

        Raises:
            ValueError: If only one of ``column``/``row`` is given, or
                ``col2``/``row2`` without both.
        """
        if column is None and row is None:
            if col2 is not None or row2 is not None:
                raise ValueError("col2 and row2 require column and row")
            return self._tk.grid_bbox()
        if column is None or row is None:
            raise ValueError("column and row must be given together")
        if col2 is not None or row2 is not None:
            # tkinter forwards the end cell only when both halves are given, so the missing half is filled in
            col2 = col2 if col2 is not None else column
            row2 = row2 if row2 is not None else row
        return self._tk.grid_bbox(column, row, col2, row2)  # type: ignore[arg-type]

    def grid_location(self, x: str | float, y: str | float) -> tuple[int, int]:
        """Return the grid cell under a master-relative coordinate.

        Delegates to :meth:`tkinter.Misc.grid_location`.

        Args:
            x (str | float): Horizontal coordinate, in any form Tk
                accepts (e.g. pixels or ``"2c"``).
            y (str | float): Vertical coordinate, likewise.

        Returns:
            The ``(column, row)`` at the point; points outside the
            grid clamp to the nearest edge.
        """
        return self._tk.grid_location(x, y)

    def grid_size(self) -> tuple[int, int]:
        """Return the dimensions of the grid.

        Delegates to :meth:`tkinter.Misc.grid_size`.

        Returns:
            A ``(columns, rows)`` count of the columns and rows
            currently occupied by managed slaves.
        """
        return self._tk.grid_size()

    def grid_slaves(self, row: int | None = None, column: int | None = None) -> tuple[Widget, ...]:
        """Return the wrappers of the widgets managed by this grid.

        Reads :meth:`tkinter.Misc.grid_slaves` and answers the
        wrappers among the slaves, per the traversal rule
        (:func:`~tkfacade.widget._widget.wrappers_among`): what the
        facade did not build — a raw tkinter slave, a composite's own
        internals — is not named.

        Args:
            row (int | None): Restrict to this row. Defaults to None,
                meaning all rows.
            column (int | None): Restrict to this column. Defaults to
                None, meaning all columns.

        Returns:
            The matching wrappers, in reverse stacking order.
        """
        from ._widget import wrappers_among

        return wrappers_among(self._tk.grid_slaves(row, column))

    @overload
    def grid_propagate(self) -> bool: ...
    @overload
    def grid_propagate(self, flag: bool) -> None: ...
    def grid_propagate(self, flag: bool | None = None) -> bool | None:
        """Query or set whether the master resizes to fit its grid contents.

        Delegates to :meth:`tkinter.Misc.grid_propagate`.

        Args:
            flag (bool | None): Enable or disable propagation.
                Defaults to None, meaning query without changing.

        Returns:
            The current setting if ``flag`` is None; otherwise None.
        """
        if flag is None:
            return bool(self._tk.grid_propagate())
        self._tk.grid_propagate(flag)
        return None

    @overload
    def grid_anchor(self) -> str: ...
    @overload
    def grid_anchor(self, anchor: Anchor) -> None: ...
    def grid_anchor(self, anchor: Anchor | None = None) -> str | None:
        """Query or set how the grid is positioned within its master.

        Setting delegates to :meth:`tkinter.Misc.grid_anchor`; querying
        goes to the interpreter directly, since the tkinter method
        discards Tcl's result. Matters only when the master is larger
        than its grid contents require.

        Args:
            anchor (Anchor | None): New anchor position. Defaults to
                None, meaning query without changing.

        Returns:
            The current anchor if ``anchor`` is None; otherwise None.
        """
        if anchor is None:
            # tkinter's grid_anchor drops Tcl's result, so the query goes to the interpreter directly
            return str(self.tk.call("grid", "anchor", str(self._tk)))
        self._tk.grid_anchor(anchor)
        return None

    @overload
    def grid_columnconfigure(
        self, index: int | str | list[int] | tuple[int, ...]
    ) -> dict[str, Any]: ...
    @overload
    def grid_columnconfigure(
        self, index: int | str | list[int] | tuple[int, ...], cnf: str
    ) -> Any: ...
    @overload
    def grid_columnconfigure(
        self,
        index: int | str | list[int] | tuple[int, ...],
        cnf: dict[str, Any] | None = None,
        *,
        minsize: PadValue = ...,
        pad: PadValue = ...,
        weight: int = ...,
    ) -> None: ...
    def grid_columnconfigure(
        self,
        index: int | str | list[int] | tuple[int, ...],
        cnf: dict[str, Any] | str | None = None,
        **kw: Any,
    ) -> Any:
        """Query or set a grid column's layout options.

        Delegates to :meth:`tkinter.Misc.grid_columnconfigure`.

        Args:
            index (int | str | list[int] | tuple[int, ...]): Column
                index or indices; ``"all"`` covers every column in
                use.
            cnf (dict[str, Any] | str | None): A single option name to
                query, or a dict of options to set, merged with
                keyword options. Defaults to None.
            minsize (PadValue): Minimum column width.
            pad (PadValue): Extra padding added to the column's width.
            weight (int): Relative share of extra space the column
                receives when the master grows.
            **kw (Any): Additional column options, equivalent to
                passing them via ``cnf``.

        Returns:
            All of the column's options as a dict if called with only
            ``index``; the named option's value if ``cnf`` is a
            string; otherwise None, when setting.

        Raises:
            TclError: If Tcl rejects an option, value, or index.
        """
        return self._tk.grid_columnconfigure(index, cnf if cnf is not None else {}, **kw)  # type: ignore[arg-type]

    @overload
    def grid_rowconfigure(
        self, index: int | str | list[int] | tuple[int, ...]
    ) -> dict[str, Any]: ...
    @overload
    def grid_rowconfigure(
        self, index: int | str | list[int] | tuple[int, ...], cnf: str
    ) -> Any: ...
    @overload
    def grid_rowconfigure(
        self,
        index: int | str | list[int] | tuple[int, ...],
        cnf: dict[str, Any] | None = None,
        *,
        minsize: PadValue = ...,
        pad: PadValue = ...,
        weight: int = ...,
    ) -> None: ...
    def grid_rowconfigure(
        self,
        index: int | str | list[int] | tuple[int, ...],
        cnf: dict[str, Any] | str | None = None,
        **kw: Any,
    ) -> Any:
        """Query or set a grid row's layout options.

        Delegates to :meth:`tkinter.Misc.grid_rowconfigure`.

        Args:
            index (int | str | list[int] | tuple[int, ...]): Row index
                or indices; ``"all"`` covers every row in use.
            cnf (dict[str, Any] | str | None): A single option name to
                query, or a dict of options to set, merged with
                keyword options. Defaults to None.
            minsize (PadValue): Minimum row height.
            pad (PadValue): Extra padding added to the row's height.
            weight (int): Relative share of extra space the row
                receives when the master grows.
            **kw (Any): Additional row options, equivalent to passing
                them via ``cnf``.

        Returns:
            All of the row's options as a dict if called with only
            ``index``; the named option's value if ``cnf`` is a
            string; otherwise None, when setting.

        Raises:
            TclError: If Tcl rejects an option, value, or index.
        """
        return self._tk.grid_rowconfigure(index, cnf if cnf is not None else {}, **kw)  # type: ignore[arg-type]


class GridWidget(GridContainerWidget):
    """Grid facet of a wrapper: the container half plus being a slave.

    Adds the slave role — placing this widget in its master's grid —
    which only exists on real ``tk.Widget`` subclasses; hence the
    narrowed ``_tk``.
    """

    if TYPE_CHECKING:
        _tk: tk.Widget

    __slots__ = ("_grid_removed",)

    def grid(
        self,
        cnf: GridSetOptions | None = None,
        *,
        column: int | EllipsisType = ...,
        columnspan: int | EllipsisType = ...,
        row: int | EllipsisType = ...,
        rowspan: int | EllipsisType = ...,
        ipadx: PadValue | EllipsisType = ...,
        ipady: PadValue | EllipsisType = ...,
        padx: Pad | EllipsisType = ...,
        pady: Pad | EllipsisType = ...,
        sticky: Sticky | EllipsisType = ...,
        in_: tk.Misc | BaseWidget | EllipsisType = ...,
        **kw: Any,
    ) -> Self:
        """Place or reconfigure the widget in its master's grid.

        Delegates to :meth:`tkinter.Grid.grid`, and is incremental the
        way Tk itself is: on a widget this grid already manages — or
        one taken off screen by :meth:`grid_remove`, whose remembered
        options Tk restores — only the options named are changed. The
        defaults below apply when the call first places an unmanaged
        widget. Tk offers no way to ask whether an unmanaged widget
        carries remembered options, so a removal made on the raw
        widget behind this wrapper reads as never placed. Also
        available as
        ``grid_configure``, an alias for this method.

        Args:
            cnf (GridSetOptions | None): Grid options, merged with
                keyword options. Defaults to None.
            column (int): Column to occupy, starting at 0. Defaults
                to 0.
            columnspan (int): Number of columns spanned. Defaults to 1.
            row (int): Row to occupy, starting at 0. Defaults to 0.
            rowspan (int): Number of rows spanned. Defaults to 1.
            ipadx (PadValue): Internal horizontal padding. Defaults
                to 0.
            ipady (PadValue): Internal vertical padding. Defaults to 0.
            padx (Pad): External horizontal padding. Defaults to 0.
            pady (Pad): External vertical padding. Defaults to 0.
            sticky (Sticky): Cell edges the widget is stretched or
                anchored to. Defaults to ``"nsew"``.
            in_ (tk.Misc | BaseWidget): Master to grid into, if other
                than the existing master; a wrapper is unwrapped.
            **kw (Any): Additional grid options forwarded to Tcl, for
                options :class:`GridSetOptions` doesn't cover (e.g.
                future Tk versions).

        Returns:
            This wrapper, for call chaining.

        Raises:
            TclError: If Tcl rejects an option or value.
        """
        opts: dict[str, Any] = {}
        if in_ is not ...:
            opts["in_"] = self._as_master(in_)
        named = {
            "column": column,
            "columnspan": columnspan,
            "row": row,
            "rowspan": rowspan,
            "ipadx": ipadx,
            "ipady": ipady,
            "padx": padx,
            "pady": pady,
            "sticky": sticky,
        }
        opts |= {name: value for name, value in named.items() if value is not ...}
        opts |= kw
        removed = getattr(self, "_grid_removed", False)
        if self._tk.winfo_manager() != "grid" and not removed:
            for name, default in _GRID_DEFAULTS.items():
                opts.setdefault(name, default)
        if cnf:
            opts.update(cnf)
        if "in_" in opts:
            opts["in_"] = self._as_master(opts["in_"])
        self._tk.grid(**opts)
        self._grid_removed = False
        return self

    grid_configure = grid

    def grid_remove(self) -> None:
        """Unmap the widget, keeping its grid options for the next :meth:`grid`.

        Delegates to :meth:`tkinter.Grid.grid_remove`. The wrapper
        records the removal, so a later :meth:`grid` is incremental
        over the remembered options exactly as Tk's own bare ``grid``
        is, rather than stamping first-placement defaults over them.
        A widget grid does not currently manage records nothing: Tk's
        ``grid remove`` is a no-op there that leaves no options to
        remember, so recording one would make the next genuine first
        placement skip the wrapper's defaults for a memory that does
        not exist.
        """
        if self._tk.winfo_manager() == "grid":
            self._grid_removed = True
        self._tk.grid_remove()

    def grid_forget(self) -> None:
        """Unmap the widget and discard its grid options.

        Delegates to :meth:`tkinter.Grid.grid_forget`. The next
        :meth:`grid` is a first placement and fills the wrapper's
        defaults in.
        """
        self._grid_removed = False
        self._tk.grid_forget()

    def grid_info(self) -> GridInfo:
        """Return the widget's current grid options.

        Delegates to :meth:`tkinter.Grid.grid_info`.

        Returns:
            The grid options in effect (e.g. ``row``, ``column``,
            ``sticky``), or an empty dict if the widget is not
            grid-managed.
        """
        return cast(GridInfo, self._tk.grid_info())
