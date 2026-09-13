"""Shared aliases, constants, and the converter pair for the tree subpackage.

:class:`ColumnConverters` is the one name here the package's ``__init__``
holds back. It is bookkeeping: the carrier :class:`Tree` keys by column
name, of no use to a caller who is not the tree itself. Converters are
asked for and installed through :attr:`TreeColumn.incoming_converter`
and :attr:`TreeColumn.outgoing_converter`, or declared on a
:class:`TreeColumnSpec`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from .._types import SelectParam

ROOT: Final[str] = ""
"""The invisible root item's iid; parent of all top-level rows."""

type Region = Literal["heading", "separator", "tree", "cell", "nothing"]
"""Kind of Treeview element at a screen coordinate (``identify_region``)."""

type ShowParam = Literal["tree", "headings", "tree headings", ""]
"""Tk's ``show`` option: which optional Treeview elements are visible."""

__all__ = ["ROOT", "ColumnConverters", "Region", "SelectParam", "ShowParam"]
"""``SelectParam`` is re-exported from the shared vocabulary rather than
defined here: every widget offering a selection over rows speaks it, so it
moved to ``_types.py`` when the listbox became the second to do so. The
name stays reachable as ``tkfacade.tree.SelectParam``, which the API
documents."""


def _identity(value: str) -> str:
    """Return ``value`` unchanged; the default outgoing converter."""
    return value


@dataclass(slots=True)
class ColumnConverters:
    """Per-column translation between Python values and Tk's cell strings.

    Attributes:
        incoming (Callable[[Any], str]): Applied to values written into
            cells. Defaults to :class:`str`.
        outgoing (Callable[[str], Any]): Applied to values read out of
            cells. Defaults to identity.
    """

    incoming: Callable[[Any], str] = str
    outgoing: Callable[[str], Any] = _identity
