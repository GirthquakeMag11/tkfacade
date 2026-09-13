""":class:`~tkfacade.media.MediaVariables`: the bundle's own value semantics.

The displays it belongs to need libmpv and a real display; the bundle
does not — it is a frozen dataclass of observables, which need no
interpreter at all — so its contract is testable on its own, with no
fixture and no ``gui`` marker anywhere. That freedom is itself part of
what the observable conversion bought.
"""

import pytest

from tkfacade import ObservableBool, ObservableFloat, ObservableInt
from tkfacade.media import MediaVariables


def _bundle() -> MediaVariables:
    """A bundle of ten fresh, unattached observables."""
    return MediaVariables(
        auto_size=ObservableBool(False),
        duration=ObservableFloat(0.0),
        loop=ObservableBool(False),
        media_height=ObservableInt(0),
        media_width=ObservableInt(0),
        muted=ObservableBool(False),
        obstructed=ObservableBool(True),
        paused=ObservableBool(True),
        position=ObservableFloat(0.0),
        volume=ObservableFloat(100.0),
    )


def test_a_bundle_is_hashable_and_compares_by_identity() -> None:
    """A bundle can key a dict, and only equals itself.

    Hashing is the half that broke in the variable era: the frozen dataclass derived __hash__ from its fields, and tk.Variable defines __eq__ without __hash__, so hash(bundle) raised TypeError naming a Tk class the caller never mentioned — which is why the class carries eq=False. Observables hash by identity natively, but the pin stays: putting a bundle in a dict and a set is the shape a caller reaches for, and the two-bundle inequality is what holds identity semantics specifically, since field-wise equality would separate these two anyway.
    """
    bundle = _bundle()
    other = _bundle()

    assert {bundle: "display"}[bundle] == "display"
    assert bundle in {bundle}
    assert bundle == bundle
    assert bundle != other


def test_a_bundle_is_still_frozen() -> None:
    """Assigning a field raises rather than swapping the live observable.

    Dropping eq=True to recover the hash must not drop frozen with it: the observables are live and a display's watches already hang off them, so replacing the attribute would silently detach those watches while leaving the display writing to the old observable. The guard is asserted on the message rather than the exact class because FrozenInstanceError is a dataclasses detail, and what a caller actually meets is the refusal.
    """
    bundle = _bundle()

    with pytest.raises(Exception, match="cannot assign to field"):
        bundle.volume = ObservableFloat(0.0)  # type: ignore[misc]
