"""The event enums, held to the Tk grammar they claim to spell.

Binding is the only oracle: whether a name is an event type or a
modifier is decided by where Tk accepts it in a pattern, so the module
carries the ``gui`` marker and drives a live interpreter.
"""

import tkinter as tk

import pytest

import tkfacade
from tkfacade.events import EventModifier, EventType, Key, Substitution

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


def test_every_event_type_member_binds_in_the_type_position(window: tkfacade.Window) -> None:
    """Tk accepts each ``EventType`` member as the type field of a binding.

    The enum's docstring is a bindability claim — "accepted as the type field of a binding" — and membership drifted from it once already: the held-button and Any modifiers sat here and raised on exactly this call. Binding every member is the whole contract in one loop, and a member Tk rejects fails with its own name in the TclError.
    """
    label = tk.Label(window._tk)

    for member in EventType:
        label.bind(f"<{member.value}>", lambda event: None)


def test_event_modifiers_prefix_but_do_not_stand_alone(window: tkfacade.Window) -> None:
    """Each ``EventModifier`` member binds before a type and raises as one.

    Both halves of what makes these modifiers rather than types: the prefix position accepts every member and the type position refuses every member. The refusal half is what keeps the two enums honest — a name valid in both positions would belong in EventType, and Tk, not this library, is the authority the assertion consults.
    """
    label = tk.Label(window._tk)

    for member in EventModifier:
        label.bind(f"<{member.value}-KeyPress>", lambda event: None)
        with pytest.raises(tk.TclError):
            label.bind(f"<{member.value}>", lambda event: None)


@pytest.mark.skipif(not _is_x11(), reason="X11-only: win32 bind parser accepts the Windows trio")
def test_every_key_member_binds_except_the_documented_windows_trio(
    window: tkfacade.Window,
) -> None:
    """On X11 every ``Key`` member binds as a detail, bar the three Windows-only ones.

    The class docstring is a bindability claim like EventType's, but no test ever bound a Key member — which is how three Windows-only keysyms (Win_L, Win_R, App) sat in it reading as portable while X11's bind parser rejects them. The docstring now names that trio and their X11 counterparts, and this loop is the enforcement: every other member must bind on this display, and exactly the documented three must not — a fourth unportable spelling fails the bind leg with its own name in the TclError, and a trio member starting to bind (a future Tk widening its table) fails the raises leg, both flagging the docstring for renewal. The windowingsystem assertion pins that the expectations match the display actually under test.
    """
    label = tk.Label(window._tk)
    windows_only = {Key.LEFT_WINDOWS, Key.RIGHT_WINDOWS, Key.CONTEXT_MENU}

    for member in Key:
        if member in windows_only:
            with pytest.raises(tk.TclError):
                label.bind(f"<KeyPress-{member.value}>", lambda event: None)
        else:
            label.bind(f"<KeyPress-{member.value}>", lambda event: None)


def test_raw_event_dict_matches_a_delivered_event(window: tkfacade.Window) -> None:
    """The TypedDict's keys are exactly what a live event's ``__dict__`` holds.

    The dict claimed to hold a Tk event's fields "exactly as tkinter delivers them" while omitting delta — the one field a <MouseWheel> handler exists to read, assigned unconditionally by tkinter's substitution — so typed consumers were rejected for reading it. The comparison runs against a genuinely delivered event rather than a hand-kept list so the next tkinter field to appear or vanish fails the test instead of the docstring; focus is the one lawful residue, NotRequired because tkinter itself skips it on events that carry none.
    """
    delivered: dict[str, object] = {}
    label = tk.Label(window._tk)
    label.pack()
    label.bind("<Motion>", lambda event: delivered.update(event.__dict__))
    window._tk.update()
    label.event_generate("<Motion>", x=1, y=1)
    window._tk.update()

    from tkfacade.events import RawEventDict

    typed = set(RawEventDict.__annotations__)
    assert delivered, "no event was delivered"
    assert set(delivered) - typed == set()
    assert typed - set(delivered) == {"focus"}


def test_every_substitution_member_is_replaced_by_tk(window: tkfacade.Window) -> None:
    """Tk substitutes each ``Substitution`` member rather than passing it through.

    The enum presents itself as the set of percent codes Tk replaces — down to a comment on the one code that is not one — so a member Tk passes through as a bare letter, or a real substitution missing from the roster, both falsify the reference; %M, a documented substitution for the matched-binding count, was missing exactly that way. An unknown code collapses to its bare letter, which is what the passed-through check detects; %% is excluded because its substitution is the literal "%", indistinguishable from that collapse by value.
    """
    label = tk.Label(window._tk)
    label.pack()
    received: list[str] = []
    window._tk.tk.createcommand("record_substitution", lambda value: received.append(value))
    codes = [member.value for member in Substitution if member is not Substitution.PERCENT]
    script = "; ".join(f"record_substitution {{{code}}}" for code in codes)
    window._tk.tk.call("bind", str(label), "<KeyPress>", script)
    label.focus_force()
    window._tk.update()

    label.event_generate("<KeyPress-a>")
    window._tk.update()

    assert len(received) == len(codes)
    passed_through = [
        code for code, value in zip(codes, received, strict=True) if value == code.lstrip("%")
    ]
    assert passed_through == []
