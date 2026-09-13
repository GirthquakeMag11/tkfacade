"""The :class:`~tkfacade.widget.PlaceConfig` protocol conformance and empty state.

Place gives a master no options at all, so this config carries nothing
and ``visit`` applies nothing. What is under test is that the empty
case still answers the whole :class:`AbstractConfig` protocol, and that
``visit`` really is inert rather than merely untested.
"""

import pytest

import tkfacade
from tkfacade.widget import PlaceConfig


def test_merges_and_operators_return_the_expected_objects() -> None:
    """Every merge yields a ``PlaceConfig``, in place or copied as documented.

    An empty config is exactly where a protocol gets implemented wrongly without anyone noticing: a merge that returned None, or an ``__or__`` that handed back an operand, would break composition the moment a caller chained on the result, and no state assertion could catch it because there is no state. Identity is therefore the whole test. ``__ior__`` is called by name rather than through ``|=`` because the statement form rebinds, which would hide a method returning None.
    """
    config = PlaceConfig()
    other = PlaceConfig()

    assert config.hard_update(other) is config
    assert config.soft_update(other) is config
    assert config.__ior__(other) is config

    merged = config | other

    assert isinstance(merged, PlaceConfig)
    assert merged is not config and merged is not other


def test_copies_are_distinct_objects() -> None:
    """``copy`` and ``deepcopy`` each return a new, independent config.

    ``AbstractConfig.copy``/``deepcopy`` delegate to the dunders, and a stateless ``__deepcopy__`` that forgot ``memo[id(self)] = new`` would still pass — nothing here recurses. The contract worth pinning is the one ``__or__`` depends on: a copy is a new object, never self.
    """
    config = PlaceConfig()

    shallow = config.copy()
    deep = config.deepcopy()

    assert isinstance(shallow, PlaceConfig)
    assert isinstance(deep, PlaceConfig)
    assert shallow is not config
    assert deep is not config


@pytest.mark.gui
def test_visit_leaves_the_master_and_its_children_untouched(window: tkfacade.Window) -> None:
    """``visit`` changes nothing about a master or where its children sit.

    The no-op is a documented contract, not an accident of there being no fields, so it is asserted rather than assumed — a later visit that reset or re-applied anything would be a silent regression. A really placed child is the subject because place stores its options on the child rather than the master, so the child's own info dict is the only place a stray write could show. The values are arbitrary but non-default: comparing against Tk's own defaults would pass even if visit had cleared them. The read-back of ``before`` guards the comparison itself — two empty dicts would compare equal and turn the real assertion vacuous, which is the one way this test could go green while testing nothing. It reads through ``int`` because Tk answers ``place_info`` with strings here, and :data:`PadValue` admits either.
    """
    child = tkfacade.StackFrame(window)
    child.place(x=17, y=23, width=40, height=50)
    placed = child.place_info()
    before = dict(placed)

    PlaceConfig().visit(window)

    assert int(placed["x"]) == 17 and int(placed["y"]) == 23
    assert dict(child.place_info()) == before
