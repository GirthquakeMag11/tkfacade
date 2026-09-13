"""The :class:`~tkfacade.widget.PackConfig` merge algebra and its one option.

A config is a deferred bundle: everything below except the ``visit``
test runs without a Tk interpreter, because accumulating and merging
options must not require the widget they will eventually configure.
"""

import pytest

import tkfacade
from tkfacade.widget import PackConfig


def _config(propagate: bool | None) -> PackConfig:
    """Build a config with ``propagate`` set.

    Args:
        propagate (bool | None): The flag to set; None leaves it unset.

    Returns:
        The populated config.
    """
    config = PackConfig()
    config.propagate = propagate
    return config


def test_hard_update_conflicts_go_to_other() -> None:
    """On a contested propagate, ``hard_update`` takes other's value.

    False beating True is the whole point of this test rather than a True-over-False pairing: propagate is a bool where one of the two values is falsey, so a guard written as ``if other._propagate`` would pass a True-over-False test and silently drop every False here. The guard has to be ``is not None``, and this is what says so.
    """
    base = _config(True)

    base.hard_update(_config(False))

    assert base.propagate is False


def test_hard_update_does_not_clear_from_an_unset_other() -> None:
    """An ``other`` that never set propagate leaves self's value standing.

    The third state, and the one a two-valued mental model loses: unset is not "set to False". Merging an empty config must be a no-op, or every composition with a partially-filled fragment would wipe what came before. False is the stored value because it is the one an unset-means-False bug would leave looking correct.
    """
    base = _config(False)

    base.hard_update(PackConfig())

    assert base.propagate is False


def test_soft_update_fills_only_when_unset() -> None:
    """``soft_update`` keeps self's propagate and fills it only when unset.

    hard_update's mirror, and both directions are asserted in one test because they are the two branches of a single guard: the contested case must keep self's value, the empty case must take other's. A regression in either branch fails its own assertion.
    """
    held = _config(True)
    filled = PackConfig()

    held.soft_update(_config(False))
    filled.soft_update(_config(False))

    assert held.propagate is True
    assert filled.propagate is False


def test_or_mutates_neither_operand() -> None:
    """``|`` returns a merged config and leaves both operands unchanged.

    ``__or__`` is inherited from AbstractConfig as copy-then-hard_update, so what is really under test is that __copy__ produces a genuinely independent object. The identity assertions distinguish a correct merge from one that returned an aliased operand.
    """
    left = _config(True)
    right = _config(False)

    merged = left | right

    assert merged.propagate is False
    assert left.propagate is True
    assert right.propagate is False
    assert merged is not left and merged is not right


def test_ior_mutates_left_in_place() -> None:
    """``|=`` merges into the left operand and preserves its identity.

    The in-place half of the operator pair: callers accumulate layout fragments with ``|=`` and rely on the bound name still being the same object. Identity is the assertion that separates ``__ior__`` from a rebinding ``__or__``.
    """
    config = PackConfig()
    original = config

    config |= _config(False)

    assert config is original
    assert config.propagate is False


def test_copies_are_independent() -> None:
    """A copy carries the value across and does not write back.

    Shallow and deep are one test here, unlike GridConfig's pair, because propagate is a bool: there is no nested container for the two to differ over, so the only contract either can break is writing back through to the original.
    """
    config = _config(True)

    shallow = config.copy()
    deep = config.deepcopy()
    shallow.propagate = False
    deep.propagate = False

    assert config.propagate is True
    assert shallow.propagate is False
    assert deep.propagate is False


def test_propagate_clears_with_none() -> None:
    """Assigning ``None`` returns propagate to unset, not to False.

    None doubles as "never set" and "clear it", and the assertion that matters is the second one: a cleared config must merge like an empty one. Reading the property back only proves the setter stored None; merging proves the rest of the class agrees that None means unset.
    """
    config = _config(False)

    config.propagate = None

    assert config.propagate is None

    absorbing = _config(True)
    absorbing.hard_update(config)

    assert absorbing.propagate is True


@pytest.mark.gui
def test_visit_applies_the_accumulated_option(window: tkfacade.Window) -> None:
    """``visit`` lands the accumulated propagate flag on a live master.

    The one Tk-touching method: everything above proves the bundle accumulates correctly, and this proves the bundle actually arrives. Read-back goes through the wrapper's query overload rather than internal state so the test observes what a real caller would. False is the value applied because Tk's default is True, so a visit that skipped the write entirely would still read True and fail.
    """
    config = PackConfig()
    config.propagate = False

    config.visit(window)

    assert window.pack_propagate() is False
