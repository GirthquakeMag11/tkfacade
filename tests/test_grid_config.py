"""The :class:`~tkfacade.widget.GridConfig` merge algebra and view semantics.

A config is a deferred bundle: everything below except the ``visit``
test runs without a Tk interpreter, because accumulating and merging
options must not require the widget they will eventually configure.
"""

from typing import Any

import pytest

import tkfacade
from tkfacade.widget import GridConfig, GridElementConfig


def _config(**columns: dict[str, Any]) -> GridConfig:
    """Build a config with per-column options from ``cN``-style kwargs.

    Args:
        **columns (dict[str, Any]): Option dicts keyed ``c<index>``,
            e.g. ``c0={"weight": 1}`` for column 0.

    Returns:
        The populated config.
    """
    config = GridConfig()
    for key, options in columns.items():
        view = config.column(int(key.removeprefix("c")))
        for name, value in options.items():
            view[name] = value
    return config


def test_hard_update_merges_per_option_per_index() -> None:
    """``hard_update`` adds other's options without erasing siblings.

    The merge granularity is the contract worth pinning: a naive dict-replace merge would satisfy "other wins" while silently dropping column 0's stored minsize the moment other configures the same column for any reason. Both options are read back because losing the sibling is exactly the regression this guards against.
    """
    base = _config(c0={"minsize": 100})
    incoming = _config(c0={"weight": 1})

    base.hard_update(incoming)

    assert base.column(0).minsize == 100
    assert base.column(0).weight == 1


def test_hard_update_conflicts_go_to_other() -> None:
    """On a directly contested option, ``hard_update`` takes other's value.

    The companion to the merge test: same method, opposite question — when both sides set the same option, which survives. propagate rides along because the container-wide flags follow a separate code path from the per-index tables and False must still win over True (the guard is ``is not None``, not truthiness).
    """
    base = _config(c0={"weight": 1})
    base.propagate = True
    incoming = _config(c0={"weight": 5})
    incoming.propagate = False

    base.hard_update(incoming)

    assert base.column(0).weight == 5
    assert base.propagate is False


def test_soft_update_fills_gaps_only() -> None:
    """``soft_update`` keeps self's values and fills only unset options.

    soft_update is hard_update's mirror, and the interesting cases are the three fills at different depths: a contested option (kept), a gap inside an existing column (filled), and a whole missing column (adopted). One test covers all three because they exercise the same loop's three branches, and a regression in any branch shows up as its own failing assertion.
    """
    base = _config(c0={"weight": 1})
    base.anchor = "nw"
    incoming = _config(c0={"weight": 5, "minsize": 40}, c1={"pad": 2})
    incoming.anchor = "se"

    base.soft_update(incoming)

    assert base.column(0).weight == 1
    assert base.column(0).minsize == 40
    assert base.column(1).pad == 2
    assert base.anchor == "nw"


def test_or_mutates_neither_operand() -> None:
    """``|`` returns a merged config and leaves both operands unchanged.

    ``__or__`` is documented as copy-then-hard_update; the failure mode is an implementation that forgets the copy and mutates left in place, which every call site composing configs would feel. The identity assertions distinguish that from returning a correct but aliased operand.
    """
    left = _config(c0={"weight": 1})
    right = _config(c0={"weight": 5})

    merged = left | right

    assert merged.column(0).weight == 5
    assert left.column(0).weight == 1
    assert right.column(0).weight == 5
    assert merged is not left and merged is not right


def test_ior_mutates_left_in_place() -> None:
    """``|=`` merges into the left operand and preserves its identity.

    The in-place half of the operator pair: callers accumulate layout fragments with ``|=`` and rely on the bound name still being the same object (views built from it beforehand write into it). Identity is the assertion that separates ``__ior__`` from a rebinding ``__or__``.
    """
    config = _config(c0={"minsize": 100})
    original = config

    config |= _config(c0={"weight": 1})

    assert config is original
    assert config.column(0).minsize == 100
    assert config.column(0).weight == 1


def test_copy_is_one_level_deep() -> None:
    """``copy`` detaches the per-index tables but shares leaf values.

    Pins the documented boundary of the shallow copy: writes into a clone's per-index dict must not leak back (the tables are copied), yet the stored values themselves are shared, not duplicated. A list leaf is used because identity is the only observable difference between "table copied" and "everything copied" — int leaves would pass either way under interning.
    """
    shared_leaf = [1, 2]
    config = GridConfig()
    config.column(0)["pad"] = shared_leaf

    clone = config.copy()
    clone.column(0)["weight"] = 9

    assert config.column(0).weight is None
    assert clone.column(0)["pad"] is shared_leaf


def test_deepcopy_shares_nothing() -> None:
    """``deepcopy`` duplicates option values as well as the tables.

    The counterpart boundary: deepcopy's one observable difference from copy is leaf independence, so that is the whole test. Equality first, identity second — a deepcopy that dropped the value entirely would otherwise pass the identity check by returning None.
    """
    leaf = [1, 2]
    config = GridConfig()
    config.column(0)["pad"] = leaf

    clone = config.deepcopy()

    assert clone.column(0)["pad"] == [1, 2]
    assert clone.column(0)["pad"] is not leaf


def test_column_and_row_hand_back_the_public_view_type() -> None:
    """``column`` and ``row`` answer with the exported ``GridElementConfig``.

    Both methods are public and used to answer with a private class, so their signatures named something a caller could not import, annotate a variable with, or look up. The import at the top of this module is half the assertion — collection fails outright if the name stops being exported — and isinstance is the other half, for the case where the export survives but the methods start building something else. Both accessors are checked because each constructs its view independently, one per table.
    """
    config = GridConfig()

    column_view = config.column(0)
    row_view = config.row(0)

    assert isinstance(column_view, GridElementConfig)
    assert isinstance(row_view, GridElementConfig)


def test_a_view_is_no_kind_of_collection() -> None:
    """``len``, iteration and ``in`` refuse; the subscript still reads and writes.

    The view's settled shape. Its three keys are named in its signature, so there is nothing for a length or a key walk to report that a reader does not already have — but leaving __iter__ merely undefined is not the same as refusing: Python would fall back to the legacy iteration protocol, subscript with 0, and surface __getitem__'s KeyError for a key no caller wrote. __iter__ = None is what turns all three into a TypeError naming the real problem, and these assertions are what stop it being deleted as dead code. The write-then-read is the other half: a class that refused everything would pass the first three checks while breaking the view's whole purpose.
    """
    view = GridConfig().column(0)

    with pytest.raises(TypeError):
        len(view)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        list(view)  # type: ignore[call-overload]
    with pytest.raises(TypeError):
        _ = "weight" in view  # type: ignore[operator]

    view["weight"] = 1

    assert view["weight"] == 1


def test_view_rejects_unknown_options() -> None:
    """A column view raises ``KeyError`` for any key but minsize/pad/weight.

    ``sticky`` is the deliberate probe: it is a real grid option, just not a column-configure one, so a typo'd or misplaced option would otherwise sit silently in the table until ``visit`` handed it to Tk — far from where the mistake was made. Both access directions are checked because get and set validate independently.
    """
    view = GridConfig().column(0)

    with pytest.raises(KeyError):
        view["sticky"] = "nsew"
    with pytest.raises(KeyError):
        view["sticky"]


def test_multi_index_view_reads_tuples_and_writes_all() -> None:
    """A multi-index view writes every index and reads back a tuple.

    The single/multi split is the API's one shape-changing behavior: the same property answers a bare value or a tuple depending on how the view was built. Reading index 1 pins that a ranged write touches only the named indexes — (0, 2) is a pair, not a span.
    """
    config = GridConfig()
    config.column((0, 2)).weight = 3

    assert config.column((0, 2)).weight == (3, 3)
    assert config.column(0).weight == 3
    assert config.column(2).weight == 3
    assert config.column(1).weight is None


def test_string_index_is_parsed() -> None:
    """A string index configures the same entry as its integer form.

    Tk itself accepts string indexes, so the config does too; the padded " 3 " input pins the documented strip-then-parse rather than an exact str-to-int cast. Written through the string form and read through the int form so the assertion fails if the two land in different entries.
    """
    config = GridConfig()
    config.column(" 3 ").weight = 1

    assert config.column(3).weight == 1


def test_minsize_coerces_on_read() -> None:
    """``minsize`` reads back as an ``int`` whatever raw value was stored.

    minsize is the one property with a read-side conversion (Tk screen distances arrive as strings), and the docstring commits to coercing on read rather than on write. Storing a string pins that the raw value survives storage untouched and converts only when read; the isinstance check makes the coercion explicit rather than inferred from equality.
    """
    config = GridConfig()
    config.column(0)["minsize"] = "40"

    assert config.column(0).minsize == 40
    assert isinstance(config.column(0).minsize, int)


def test_anchor_and_propagate_clear_with_none() -> None:
    """``anchor`` and ``propagate`` start unset and clear back to ``None``.

    None doubles as "unset" and "clear this" for the container-wide flags, and visit skips a None — so a clear that failed to stick would make a stale anchor reappear on the next apply. The round-trip through real values proves clearing works from a set state, not just that the defaults are None.
    """
    config = GridConfig()
    assert config.anchor is None
    assert config.propagate is None

    config.anchor = "nw"
    config.propagate = False
    config.anchor = None
    config.propagate = None

    assert config.anchor is None
    assert config.propagate is None


def test_a_per_index_option_clears_with_none() -> None:
    """A ``None`` write unsets the option, leaves siblings, and reopens the gap.

    Reading None back cannot distinguish "cleared" from "stored as None" — the defect this pins against read back None too. soft_update is the observable that can: an option stored as None counts as present and blocks the fill, while a truly unset one is a gap that merge exists to fill. minsize rides along to pin that clearing removes one option, not the whole column entry it lives in.
    """
    config = _config(c0={"weight": 4, "minsize": 10})

    config.column(0).weight = None

    assert config.column(0).weight is None
    assert config.column(0).minsize == 10

    config.soft_update(_config(c0={"weight": 7}))

    assert config.column(0).weight == 7


def test_hard_update_does_not_clear_from_a_cleared_other() -> None:
    """An option cleared in ``other`` leaves self's real value standing.

    The set-then-clear on incoming is the point: a config that never named the option passes under any storage, but one that stored the clear as {"weight": None} handed that None to the merge and erased base's real weight. Cleared must read as unset on the merge path too, or composing a layout from fragments erases options no fragment set.
    """
    base = _config(c0={"weight": 5})
    incoming = _config(c0={"weight": 3})
    incoming.column(0).weight = None

    base.hard_update(incoming)

    assert base.column(0).weight == 5


def test_a_view_refuses_an_empty_index_sequence() -> None:
    """``column`` and ``row`` raise ``ValueError`` on a sequence naming no index.

    An empty sequence used to build a broken view: writes iterated zero indexes and stored nothing, while every read subscripted _indexes[0] and raised IndexError out of the config's internals — far from the empty selection that caused it. Refusing at construction points the error at the selection while it is still on the call stack. Both accessors are checked because each builds its view independently, and both sequence spellings because the guard runs after the type dispatch that distinguishes them from ints and strings.
    """
    config = GridConfig()

    with pytest.raises(ValueError, match="at least one"):
        config.column([])
    with pytest.raises(ValueError, match="at least one"):
        config.row(())


def test_a_view_snapshots_its_index_sequence() -> None:
    """Mutating the list a view was built over does not move the view.

    The sequence branch used to store the caller's list itself while _multi froze at construction, so a list mutated afterwards made the view write to every current index while still reading as single-index — options accumulated for indexes the read side never mentioned. The snapshot makes read and write agree forever: the write lands on column 0 only, and column 1, appended after the view was built, stays untouched.
    """
    indexes = [0]
    config = GridConfig()
    view = config.column(indexes)

    indexes.append(1)
    view.weight = 3

    assert view.weight == 3
    assert config.column(1).weight is None


@pytest.mark.gui
def test_visit_applies_accumulated_options(window: tkfacade.Window) -> None:
    """``visit`` lands every accumulated option on a live master.

    The one Tk-touching method: everything above proves the bundle accumulates correctly, and this proves the bundle actually arrives. Read-back goes through the public wrapper's query form rather than internal state so the test observes what a real caller would. The anchor option is left unasserted: Tk reports it only via a direct interpreter call, and the weight/minsize/propagate trio already covers all three of visit's code paths (column table, row table, flag).
    """
    config = GridConfig()
    config.column(0).weight = 2
    config.column(0).minsize = 55
    config.row(1).weight = 3
    config.propagate = False

    config.visit(window)

    assert window.grid_columnconfigure(0, "weight") == 2
    assert window.grid_columnconfigure(0, "minsize") == 55
    assert window.grid_rowconfigure(1, "weight") == 3
    assert window.grid_propagate() is False


def test_a_config_refuses_an_attribute_it_does_not_declare() -> None:
    """Assigning an undeclared name raises rather than binding a new attribute.

    Every config declares __slots__, and every one of them was decorative: AbstractConfig declared none, so subclasses got a __dict__ anyway and a misspelled option bound a new attribute instead of raising, then did nothing at visit — the silent half of the failure, and the reason the correctly-spelled assignment is checked in the same test. The __dict__ assertion is what pins the cause rather than the symptom: a subclass could satisfy the raise with a hand-written __setattr__ and still be carrying the dict this is really about.
    """
    config = GridConfig()

    with pytest.raises(AttributeError):
        config.anchr = "nw"  # type: ignore[attr-defined]

    config.anchor = "nw"

    assert config.anchor == "nw"
    assert not hasattr(config, "__dict__")
