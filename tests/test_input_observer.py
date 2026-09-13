"""The input observer: held state, the repeat filter, clearing, and chords.

The ruled brief's claims, each pinned: the root records every press
and release so any widget can ask what is held right now; autorepeat's
phantom release/press pairs (same key, same timestamp — the probe's
signature) never move the state; focus leaving the application clears
it, the release being unrecoverable; and the chord condition fires
exactly on its set becoming all-held, over both notification routes —
the command subscriber and the awaitable riding the async core. Events
are driven by ``event_generate``, the route the probe verified
registers identically to the device.
"""

import time
import tkinter as tk

import pytest

import tkfacade
from conftest import Pump
from tkfacade.events import MouseButton
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def _is_x11() -> bool:
    """True when the test display is X11."""
    try:
        probe = tk.Tk()
    except tk.TclError:
        return False
    result = str(probe.tk.call("tk", "windowingsystem")) == "x11"
    probe.destroy()
    return result


def _press(window: tkfacade.Window, keysym: str, stamp: int) -> None:
    window._tk.event_generate(f"<KeyPress-{keysym}>", time=stamp)


def _release(window: tkfacade.Window, keysym: str, stamp: int) -> None:
    window._tk.event_generate(f"<KeyRelease-{keysym}>", time=stamp)


def _flushed(window: tkfacade.Window, pump: Pump) -> None:
    """Let the observer's held-release flush timer run."""
    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline:
        pump(window)
        time.sleep(0.01)


def _armed(window: tkfacade.Window, pump: Pump) -> None:
    """Give the window keyboard focus: Tk drops generated keys without it."""
    window._tk.focus_force()
    pump(window)


def test_the_root_answers_what_is_held(window: tkfacade.Window, pump: Pump, root: Root) -> None:
    """A press reads pressed from anywhere; the release reads released.

    The brief's core sentence: the root records, anything queries. The release is deliberately read only after the flush interval — a release is provisional until the next event disowns it, which is the repeat filter's price and the next test's subject.
    """
    inputs = root.inputs
    _armed(window, pump)
    _press(window, "a", 1000)

    assert inputs.is_pressed("a")
    assert "a" in inputs.pressed_keys

    _release(window, "a", 1100)
    _flushed(window, pump)

    assert not inputs.is_pressed("a")
    assert inputs.pressed_keys == frozenset()


def test_autorepeats_phantom_pair_never_moves_the_state(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """A same-key, same-timestamp release/press pair is dropped whole.

    The Hazards fact discharged: X11 delivers a held key's repeats as release/press pairs sharing one timestamp, so raw tracking flickers and an edge-triggered chord would re-fire on every repeat. The pair is consumed without touching the state — the chord's single firing is the proof the edge never dropped.
    """
    inputs = root.inputs
    _armed(window, pump)
    fired: list[bool] = []
    hold = inputs.chord("b")
    hold.subscribe(lambda: fired.append(True))
    _press(window, "b", 2000)
    assert fired == [True]

    _release(window, "b", 2400)
    _press(window, "b", 2400)  # the probe's autorepeat signature
    _flushed(window, pump)

    assert inputs.is_pressed("b")
    assert fired == [True]

    _release(window, "b", 2900)
    _flushed(window, pump)
    assert not inputs.is_pressed("b")
    hold.cancel()


def test_focus_leaving_the_application_clears_the_state(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """FocusOut with focus gone drops every held key and button.

    The stuck-key trap's policy: the release that happens after focus left will never arrive (probe), so held state must drop rather than stick forever. The focus genuinely moves to a second interpreter — another X client, the probe's own scenario — so the FocusOut is real and focus_get honestly answers empty; a focus move *within* the application keeps the state, which the observer checks at idle.
    """
    inputs = root.inputs
    _armed(window, pump)
    _press(window, "c", 3000)
    window._tk.event_generate("<ButtonPress-1>")
    assert inputs.is_pressed("c")
    assert inputs.is_pressed(MouseButton.LEFT)

    thief = Root()
    try:
        held = tkfacade.Window(title="thief", root=thief)
        held._tk.update()
        held._tk.focus_force()
        held._tk.update()
        # under Xvfb Tk's cross-application focus grab empties focus_get
        # without X delivering the FocusOut a window manager would; the
        # event is generated, the focus-empty reading it checks is real
        window._tk.event_generate("<FocusOut>")
        _flushed(window, pump)

        assert not inputs.is_pressed("c")
        assert not inputs.is_pressed(MouseButton.LEFT)
    finally:
        thief.destroy()
    _armed(window, pump)


def test_a_chord_fires_on_its_edge_and_only_there(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """All held at once fires once; partial never; extras do not block.

    Edge-triggering as ruled: the moment the whole set is held, once, with re-arming only after some member releases — and a superset held around the set does not block it, so Control+S fires with X also down. A cancelled chord is out of the observer entirely; the trailing releases just tidy the shared state for the tests after.
    """
    inputs = root.inputs
    _armed(window, pump)
    fired: list[bool] = []
    combo = inputs.chord("Control_L", "s")
    combo.subscribe(lambda: fired.append(True))

    _press(window, "Control_L", 4000)
    assert fired == []
    _press(window, "x", 4050)  # an extra key must not block the set
    _press(window, "s", 4100)
    assert fired == [True]
    complete: bool = combo.held
    assert complete

    _release(window, "s", 4200)
    _flushed(window, pump)
    rearmed: bool = combo.held
    assert not rearmed
    _press(window, "s", 4300)
    assert fired == [True, True]

    combo.cancel()
    _release(window, "s", 4400)
    _flushed(window, pump)
    _press(window, "s", 4500)
    assert fired == [True, True]
    for keysym, stamp in (("Control_L", 4600), ("x", 4610), ("s", 4620)):
        _release(window, keysym, stamp)
    _flushed(window, pump)


def test_the_awaitable_route_completes_on_the_edge(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """``await chord.wait()`` rides the core and lands on completion.

    The macro shape end to end: a coroutine on the root's core awaits the chord and resumes when keys and a mouse button are all down at once — the observer marshalling the completion across the thread wall with the same crossing discipline the rest of the async design uses. The watch route launches the coroutine, being one of the two admission routes the design enumerates.
    """
    inputs = root.inputs
    _armed(window, pump)
    combo = inputs.chord("m", MouseButton.RIGHT)
    landed: list[str] = []

    async def macro(_value: bool) -> None:
        await combo.wait()
        landed.append("fired")

    starter = tkfacade.ObservableBool(False)
    starter.transport_for(window._tk)  # a coroutine watcher needs the interpreter
    subscription = starter.watch(macro)
    deadline = time.monotonic() + 3.0
    pressed = False
    while time.monotonic() < deadline and not landed:
        pump(window)
        if not pressed and combo._waiters:
            # press only once the waiter is parked, or the edge fires
            # into an empty list and nothing ever lands
            _press(window, "m", 5000)
            window._tk.event_generate("<ButtonPress-3>")
            pressed = True
        time.sleep(0.01)

    assert landed == ["fired"]
    subscription.cancel()
    starter.release_transport()
    combo.cancel()
    window._tk.event_generate("<ButtonRelease-3>")
    _release(window, "m", 5100)
    _flushed(window, pump)


@pytest.mark.skipif(not _is_x11(), reason="X11-only: win32 has no Control_R keysym")
def test_a_group_is_met_by_either_variant_and_an_exact_key_is_not(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """A role spelling fires on either physical key; a keysym stays exact.

    The ruled generic identifiers: "Control" means the role, met by either physical key, while "Control_L" keeps meaning that key alone — the right variant satisfied the group twice and left the exact chord unmoved until the left key came down.
    """
    inputs = root.inputs
    _armed(window, pump)
    fired: list[str] = []
    either = inputs.chord(tkfacade.KeyGroup.CONTROL, "s")
    either.subscribe(lambda: fired.append("either"))
    exact = inputs.chord("Control_L", "t")
    exact.subscribe(lambda: fired.append("exact"))

    _press(window, "Control_L", 6000)
    _press(window, "s", 6050)
    assert fired == ["either"]
    for keysym, stamp in (("s", 6100), ("Control_L", 6150)):
        _release(window, keysym, stamp)
    _flushed(window, pump)

    _press(window, "Control_R", 6200)
    _press(window, "s", 6250)
    assert fired == ["either", "either"]
    _press(window, "t", 6300)
    assert fired == ["either", "either"]

    _press(window, "Control_L", 6350)
    assert fired == ["either", "either", "exact"]

    either.cancel()
    exact.cancel()
    for keysym, stamp in (("Control_R", 6400), ("s", 6450), ("t", 6500), ("Control_L", 6550)):
        _release(window, keysym, stamp)
    _flushed(window, pump)


def test_the_caption_derives_from_the_set_and_the_set_is_fixed(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """Display text is derived — groups by role, variants honestly — and frozen.

    The chord is immutable by ruling: the set is fixed at construction — slots leave nothing to hang a change on — so the caption a menu row derives can never drift from the binding it advertises. An exact variant captions as that key alone, never promising its sibling.
    """
    inputs = root.inputs
    combo = inputs.chord("Control", "o")
    left = inputs.chord("Control_L", "o")
    crowded = inputs.chord("s", "Shift", tkfacade.KeyGroup.ALT, "Control", MouseButton.LEFT)

    assert combo.caption == "Ctrl+O"
    assert left.caption == "LeftCtrl+O"
    assert crowded.caption == "Ctrl+Alt+Shift+S+Mouse1"
    assert combo.inputs == frozenset({"Control", "o"})

    with pytest.raises(AttributeError):
        combo.later = "anything"  # type: ignore[attr-defined]

    for chord in (combo, left, crowded):
        chord.cancel()


def test_a_button_event_lands_a_pending_key_release_first(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """A chord cannot fire on a key already up when a click follows it.

    The sweep's finding (2026-08-28): a button event is "the next
    event" a pending release waits on and can never be its autorepeat
    pair, so it applies the release before judging chords.
    """
    inputs = root.inputs
    _armed(window, pump)
    combo = inputs.chord("Control_L", MouseButton.LEFT)
    fired: list[bool] = []
    combo.subscribe(lambda: fired.append(True))

    _press(window, "Control_L", 7000)
    _release(window, "Control_L", 7100)
    window._tk.event_generate("<ButtonPress-1>")

    assert fired == []
    assert not inputs.is_pressed("Control_L")

    combo.cancel()
    window._tk.event_generate("<ButtonRelease-1>")
    pump(window)


def test_is_pressed_answers_a_modifier_named_by_role(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """The one vocabulary holds on both query surfaces, not just chords."""
    inputs = root.inputs
    _armed(window, pump)
    _press(window, "Control_L", 8000)

    assert inputs.is_pressed("Control_L")
    assert inputs.is_pressed(tkfacade.KeyGroup.CONTROL)
    assert inputs.is_pressed("Control")
    assert not inputs.is_pressed(tkfacade.KeyGroup.SHIFT)

    _release(window, "Control_L", 8100)
    _flushed(window, pump)
    assert not inputs.is_pressed(tkfacade.KeyGroup.CONTROL)


def test_wheel_buttons_carry_no_state_on_x11(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """X11's wheel buttons 4 and 5 are not tracked as held.

    The wheel is stateless by design: on x11 it arrives as instantaneous button 4/5 press/release pairs (the scroll probe's record), and a tracker that counted them held would flash phantom state on every scroll tick.
    """
    inputs = root.inputs
    window._tk.event_generate("<ButtonPress-4>")

    assert not inputs.is_pressed(4)
    assert inputs.pressed_buttons == frozenset()

    window._tk.event_generate("<ButtonRelease-4>")
    pump(window)
