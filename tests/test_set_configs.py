"""The slave-side configs: merge algebra, replay, and the widened masters.

The child half of a layout gets what the master half has had all
along — `GridSetConfig`, `PackSetConfig` and `PlaceSetConfig` compose
via ``|`` and the hard/soft updates before any widget exists, then
replay through the widget's own placement method, riding Tk's
incremental merge. The widened ``*SetOptions`` master fields are
pinned here too: a dict built around a wrapper places exactly as the
keyword spelling does, which is the promise the dicts were carrying
broken.
"""

import pytest

import tkfacade
from conftest import Pump
from tkfacade.widget import GridSetConfig, PackSetConfig, PlaceSetConfig

pytestmark = pytest.mark.gui


def test_hard_update_lets_the_later_config_win() -> None:
    """``|`` composes: the right side wins conflicts, gaps survive.

    The master configs' algebra verbatim: ``|`` answers a new config, an option the right side never set does not clear the left's, and neither operand is mutated — composition is description, not action.
    """
    base = GridSetConfig(row=1, column=2, sticky="w")
    override = GridSetConfig(column=5)

    merged = base | override

    assert merged.column == 5
    assert merged.row == 1
    assert merged.sticky == "w"
    assert base.column == 2
    assert override.row is None


def test_soft_update_fills_only_the_gaps() -> None:
    """``soft_update`` keeps what is set and adopts what is not.

    The other composition order: a caller's explicit choices survive a defaults bundle applied under them, which is what makes a shared defaults config safe to apply last.
    """
    chosen = PackSetConfig(side="left")
    defaults = PackSetConfig(side="top", fill="x", expand=True)

    chosen.soft_update(defaults)

    assert chosen.side == "left"
    assert chosen.fill == "x"
    assert chosen.expand is True


def test_deepcopy_is_independent_and_none_clears() -> None:
    """A deep copy shares nothing, and assigning None unsets.

    The copy contract and the property surface in one motion: a copy is a separate description, and None reads and writes as "unset" the way every master config's option does.
    """
    original = PlaceSetConfig(x=10, y=20)
    copied = original.deepcopy()
    copied.x = 99
    assert original.x == 10

    original.y = None

    assert original.y is None
    assert copied.y == 20


def test_visit_places_and_revisits_incrementally(window: tkfacade.Window, pump: Pump) -> None:
    """``visit`` places through the widget's own method, Tk merge and all.

    The replay path is the method itself, so everything the method promises holds for a config: the first visit fills the wrapper's defaults, and a later sparse visit changes only what it names — Tk's own incremental merge, not a wipe-and-rewrite.
    """
    button = tkfacade.Button(window, "go")
    GridSetConfig(row=2, column=1, sticky="w").visit(button)
    info = button.grid_info()
    assert (info["row"], info["column"]) == (2, 1)
    assert info["sticky"] == "w"

    GridSetConfig(column=4).visit(button)

    info = button.grid_info()
    assert (info["row"], info["column"]) == (2, 4)
    assert info["sticky"] == "w"


def test_pack_and_place_configs_replay_through_their_methods(
    window: tkfacade.Window, pump: Pump
) -> None:
    """The other two managers' configs place a real widget.

    One leg per manager: each config's visit reaches its own method, and the options land where the manager's own info read reports them — the raw stratum the *Info dicts document.
    """
    host = tkfacade.Frame(window)
    host.grid(row=0, column=0)
    packed = tkfacade.Button(host, "packed")
    PackSetConfig(side="left", padx=3).visit(packed)
    assert packed.pack_info()["side"] == "left"

    placed = tkfacade.Button(host, "placed")
    PlaceSetConfig(x=12, y=7).visit(placed)

    assert str(placed.place_info()["x"]) == "12"
    assert str(placed.place_info()["y"]) == "7"


def test_a_wrapper_valued_master_places_through_dict_and_config_alike(
    window: tkfacade.Window, pump: Pump
) -> None:
    """The widened ``in_`` takes a wrapper wherever the keyword does.

    The widening item's whole point, pinned end to end: the dicts promised "type-checks the same as keyword arguments" while typing their master fields bare tk.Misc, and the cnf path never unwrapped a wrapper at all. Now both doors normalize through _as_master, so a wrapper places identically however it arrives. Tk's own rule stands — a master must descend from the slave's parent, hence the buttons parented to the window — the config's master read answers the wrapper per the traversal rule, and parent still answers the constructor's master, placement being geometry, not ancestry.
    """
    elsewhere = tkfacade.Frame(window)
    elsewhere.grid(row=1, column=0)

    by_dict = tkfacade.Button(window, "dict")
    by_dict.grid({"row": 0, "column": 0, "in_": elsewhere})
    config = GridSetConfig(row=1, column=0, in_=elsewhere)
    by_config = tkfacade.Button(window, "config")
    config.visit(by_config)

    assert str(by_dict.grid_info()["in"]) == str(elsewhere._tk)
    assert str(by_config.grid_info()["in"]) == str(elsewhere._tk)
    assert config.in_ is elsewhere
    assert by_config.parent is window
