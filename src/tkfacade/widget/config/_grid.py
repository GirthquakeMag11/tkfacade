"""Deferred grid configuration: the master half, and the slave half beside it."""

import copy
import tkinter as tk
from typing import TYPE_CHECKING, Any, Literal, Self, Unpack, cast

from ..._params import GridSetOptions
from ..._types import Anchor, Pad, PadValue, Sticky
from .._base import BaseWidget
from ._base import AbstractConfig, AbstractSetConfig

if TYPE_CHECKING:
    from .._widget import ContainerWidget, Widget


class GridElementConfig:
    """A live view onto column or row entries of a :class:`GridConfig`.

    Writes through the view land directly in the owning config's
    tables, so the view stays valid as the config grows. Built by
    :meth:`GridConfig.column` and :meth:`GridConfig.row`, not directly.

    Not a collection: the subscript takes ``"weight"``, ``"minsize"``
    and ``"pad"`` and nothing else, and ``len()``, iteration and ``in``
    all refuse. Build a dict from the three properties where one is
    wanted.
    """

    if TYPE_CHECKING:
        _data: dict[int, dict[str, Any]]
        _indexes: tuple[int, ...]
        _multi: bool

    __slots__ = ("_data", "_indexes", "_multi")

    __iter__ = None
    """Not iterable, and not by omission.

    Leaving it out would hand ``iter`` and ``in`` to Python's legacy
    iteration protocol, which subscripts with 0, 1, 2 … and meets
    :meth:`__getitem__`'s ``KeyError`` for a key no caller wrote.
    ``None`` is what makes both refuse in the terms they should.
    """

    def __init__(
        self,
        parent: GridConfig,
        _type: Literal["col", "row"],
        index: int | str | list[int] | tuple[int, ...],
    ) -> None:
        """Bind the view to entries of ``parent``.

        Args:
            parent (GridConfig): The config whose column or row table
                the view reads and writes.
            _type (Literal["col", "row"]): Which table to bind —
                ``"col"`` for columns, ``"row"`` for rows.
            index (int | str | list[int] | tuple[int, ...]): The index
                or indexes viewed. A string is stripped and parsed as
                one int; a sequence of two or more indexes makes the
                view multi-index, while a length-one sequence behaves
                like a single index. The sequence is snapshotted, so
                mutating it afterwards does not move the view.

        Raises:
            ValueError: If ``_type`` is neither ``"col"`` nor
                ``"row"``, or ``index`` is a sequence naming no index
                at all.
        """
        if _type == "col":
            self._data = parent._columnconfigure
        elif _type == "row":
            self._data = parent._rowconfigure
        else:
            raise ValueError(_type)

        if isinstance(index, str):
            self._indexes = (int(index.strip()),)
        elif isinstance(index, int):
            self._indexes = (index,)
        else:
            # snapshotted: a live reference would let a mutated caller list move the write side
            self._indexes = tuple(index)
        if not self._indexes:
            raise ValueError("index must name at least one index")

        self._multi = len(self._indexes) > 1

    def __setitem__(self, key: str, value: Any) -> None:
        """Store ``value`` for ``key`` on every viewed index.

        Assigning ``None`` clears it: the stored option is removed, so
        merges treat it as never set and :meth:`GridConfig.visit`
        skips it. Clearing an option that was never set is a no-op.

        Raises:
            KeyError: If ``key`` is not ``"minsize"``, ``"pad"`` or
                ``"weight"``.
        """
        if key not in ("minsize", "pad", "weight"):
            raise KeyError(key)
        for idx in self._indexes:
            if value is None:
                payload = self._data.get(idx)
                if payload is not None:
                    payload.pop(key, None)
                    if not payload:
                        del self._data[idx]
            else:
                self._data.setdefault(idx, {})[key] = value

    def __getitem__(self, key: str) -> Any | tuple[Any, ...]:
        """Read ``key`` from the viewed entries.

        A multi-index view returns a tuple in index order; a single
        index returns the bare value. Unset options read as ``None``.

        Raises:
            KeyError: If ``key`` is not ``"minsize"``, ``"pad"`` or
                ``"weight"``.
        """
        if key not in ("minsize", "pad", "weight"):
            raise KeyError(key)
        if self._multi:
            return tuple(self._data.get(idx, {}).get(key) for idx in self._indexes)
        return self._data.get(self._indexes[0], {}).get(key)

    @property
    def weight(self) -> int | tuple[int | None, ...] | None:
        """The pending weight option, or ``None`` when unset.

        Assigning ``None`` clears it. A view over several indexes
        reads as a tuple in index order.
        """
        return self["weight"]

    @weight.setter
    def weight(self, value: int | None) -> None:
        self["weight"] = value

    @property
    def minsize(self) -> int | tuple[int | None, ...] | None:
        """The pending minsize option, or ``None`` when unset.

        Assigning ``None`` clears it. Stored values are coerced
        through ``int()`` on read; a view over several indexes reads
        as a tuple in index order.
        """
        pv = self["minsize"]

        def conv(v: Any) -> int | None:
            if v is None:
                return None
            return int(v)

        if isinstance(pv, tuple):
            return tuple(conv(v) for v in pv)
        else:
            return conv(pv)

    @minsize.setter
    def minsize(self, value: int | None) -> None:
        self["minsize"] = value

    @property
    def pad(self) -> int | tuple[int | None, ...] | None:
        """The pending pad option, or ``None`` when unset.

        Assigning ``None`` clears it. A view over several indexes
        reads as a tuple in index order.
        """
        return self["pad"]

    @pad.setter
    def pad(self, value: int | None) -> None:
        self["pad"] = value


class GridConfig(AbstractConfig["ContainerWidget"]):
    """Deferred options for a grid container.

    Accumulates ``grid_columnconfigure`` / ``grid_rowconfigure``
    payloads plus the container-wide anchor and propagate flags.
    Unset options stay ``None`` (or absent) and are skipped by
    :meth:`visit`, so applying a config only ever touches what was
    explicitly set.
    """

    if TYPE_CHECKING:
        _columnconfigure: dict[int, dict[str, Any]]
        _rowconfigure: dict[int, dict[str, Any]]
        _anchor: Anchor | None
        _propagate: bool | None

    __slots__ = ("_anchor", "_columnconfigure", "_propagate", "_rowconfigure")

    def __init__(self) -> None:
        """Start empty: no per-index options, anchor and propagate unset."""
        self._columnconfigure = {}
        self._rowconfigure = {}
        self._anchor = None
        self._propagate = None

    def __copy__(self) -> Self:
        """Return an independent copy one level deep; leaf values are shared."""
        new = type(self)()
        new._columnconfigure = {k: dict(v) for k, v in self._columnconfigure.items()}
        new._rowconfigure = {k: dict(v) for k, v in self._rowconfigure.items()}
        new._anchor = self._anchor
        new._propagate = self._propagate
        return new

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        """Return a fully independent copy; option values are deep-copied too."""
        new = type(self)()
        memo[id(self)] = new
        new._columnconfigure = copy.deepcopy(self._columnconfigure, memo)
        new._rowconfigure = copy.deepcopy(self._rowconfigure, memo)
        new._anchor = self._anchor
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

    @property
    def anchor(self) -> Anchor | None:
        """The pending anchor option; ``None`` means unset.

        Assigning ``None`` clears it.
        """
        return self._anchor

    @anchor.setter
    def anchor(self, anchor: Anchor | None) -> None:
        self._anchor = anchor

    def hard_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``, ``other`` winning on conflicts.

        Per-index dicts merge option by option, so ``other`` setting a
        column's weight does not erase that column's stored minsize.

        Returns:
            ``self``, mutated in place.
        """
        if other._propagate is not None:
            self._propagate = other._propagate
        if other._anchor is not None:
            self._anchor = other._anchor

        for k, v in other._columnconfigure.items():
            if k not in self._columnconfigure:
                self._columnconfigure[k] = dict(v)
            else:
                self._columnconfigure[k].update(v)

        for k, v in other._rowconfigure.items():
            if k not in self._rowconfigure:
                self._rowconfigure[k] = dict(v)
            else:
                self._rowconfigure[k].update(v)

        return self

    def soft_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``, ``self`` winning on conflicts.

        Gaps are filled per option, per index, so a half-configured
        column still picks up the rest from ``other``.

        Returns:
            ``self``, mutated in place.
        """
        if self._propagate is None:
            self._propagate = other._propagate
        if self._anchor is None:
            self._anchor = other._anchor

        for k, v in other._columnconfigure.items():
            if k not in self._columnconfigure:
                self._columnconfigure[k] = dict(v)
            else:
                for sk, sv in v.items():
                    if sk not in self._columnconfigure[k]:
                        self._columnconfigure[k][sk] = sv

        for k, v in other._rowconfigure.items():
            if k not in self._rowconfigure:
                self._rowconfigure[k] = dict(v)
            else:
                for sk, sv in v.items():
                    if sk not in self._rowconfigure[k]:
                        self._rowconfigure[k][sk] = sv

        return self

    def visit(self, master: ContainerWidget, /) -> None:
        """Apply the accumulated options to a live master.

        Args:
            master (ContainerWidget): The wrapper whose grid container
                receives the options.
        """
        for index, payload in self._columnconfigure.items():
            master.grid_columnconfigure(index, **payload)
        for index, payload in self._rowconfigure.items():
            master.grid_rowconfigure(index, **payload)
        if self._anchor is not None:
            master.grid_anchor(self._anchor)
        if self._propagate is not None:
            master.grid_propagate(self._propagate)

    def column(self, index: int | str | list[int] | tuple[int, ...], /) -> GridElementConfig:
        """Return a view for setting options on column(s) ``index``.

        Writes through the view are stored in this config, deferred
        like any directly-set option.

        Args:
            index (int | str | list[int] | tuple[int, ...]): One
                column index — a string is parsed as an int — or a
                sequence of several to configure at once.

        Returns:
            A :class:`GridElementConfig` over the named column(s).

        Raises:
            ValueError: If ``index`` is a sequence naming no index at
                all.
        """
        return GridElementConfig(self, "col", index)

    def row(self, index: int | str | list[int] | tuple[int, ...], /) -> GridElementConfig:
        """Return a view for setting options on row(s) ``index``.

        Writes through the view are stored in this config, deferred
        like any directly-set option.

        Args:
            index (int | str | list[int] | tuple[int, ...]): One row
                index — a string is parsed as an int — or a sequence
                of several to configure at once.

        Returns:
            A :class:`GridElementConfig` over the named row(s).

        Raises:
            ValueError: If ``index`` is a sequence naming no index at
                all.
        """
        return GridElementConfig(self, "row", index)


class GridSetConfig(AbstractSetConfig):
    """The composable twin of :class:`~tkfacade.GridSetOptions`.

    Holds the options :meth:`~tkfacade.widget.Widget.grid` takes —
    the child half of a grid layout — with the merge surface the
    master-side configs have: ``|`` and the hard/soft updates compose
    placements before any widget exists, and :meth:`visit` replays the
    result through the widget's own method, so Tk's incremental merge
    and the first-placement defaults apply exactly as they do to
    keyword arguments. Each option answers ``None`` while unset, and
    assigning ``None`` clears it.
    """

    __slots__ = ()

    def __init__(self, **options: Unpack[GridSetOptions]) -> None:
        """Start from ``options``, any of the method's own.

        Args:
            **options (Unpack[GridSetOptions]): Starting placement
                options, each documented on
                :meth:`~tkfacade.widget.Widget.grid`.
        """
        super().__init__(**options)

    @property
    def column(self) -> int | None:
        """Column to occupy; ``None`` means unset. Assigning ``None`` clears."""
        return cast("int | None", self._get("column"))

    @column.setter
    def column(self, value: int | None) -> None:
        self._set("column", value)

    @property
    def columnspan(self) -> int | None:
        """Number of columns spanned; ``None`` means unset. Assigning ``None`` clears."""
        return cast("int | None", self._get("columnspan"))

    @columnspan.setter
    def columnspan(self, value: int | None) -> None:
        self._set("columnspan", value)

    @property
    def row(self) -> int | None:
        """Row to occupy; ``None`` means unset. Assigning ``None`` clears."""
        return cast("int | None", self._get("row"))

    @row.setter
    def row(self, value: int | None) -> None:
        self._set("row", value)

    @property
    def rowspan(self) -> int | None:
        """Number of rows spanned; ``None`` means unset. Assigning ``None`` clears."""
        return cast("int | None", self._get("rowspan"))

    @rowspan.setter
    def rowspan(self, value: int | None) -> None:
        self._set("rowspan", value)

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
    def sticky(self) -> Sticky | None:
        """Cell edges the widget clings to; ``None`` means unset. Assigning ``None`` clears."""
        return cast("Sticky | None", self._get("sticky"))

    @sticky.setter
    def sticky(self, value: Sticky | None) -> None:
        self._set("sticky", value)

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
        widget.grid(cast(GridSetOptions, dict(self._options)))
