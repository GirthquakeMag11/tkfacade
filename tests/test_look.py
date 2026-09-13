"""The look: routing, the see-what-you-set guarantee, sharing, and the door.

The styling rulings' claims (2026-08-27), each pinned: a look accepts
the whole vocabulary and applies per widget kind only what was measured
to act; a value holds in every situation unless a situation layer says
otherwise, whatever the theme's own state maps prefer; editing a worn
look repaints every wearer; None reverts; a name outside the vocabulary
is refused; one look serves one interpreter at a time. Assertions read
back through ``ttk.Style.lookup``, the same resolution the renderer
uses, rather than pixels — the probe already established that lookup
and rendering agree for the measured options.
"""

from tkinter import ttk

import pytest

import tkfacade
from conftest import Pump
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def test_a_look_routes_each_widget_kind_its_measured_subset(
    window: tkfacade.Window, pump: Pump
) -> None:
    """One look dresses a button and a table, each taking only its own.

    The intelligent-application ruling in one frame: the look holds an option only a treeview honours beside one both kinds do, and each wearer takes exactly the measured intersection — the button's minted style never hears of rowheight. The routing data is the probe's verdicts, so this also pins that the *StyleOptions sets reach the runtime as sets and not just as annotations.
    """
    look = tkfacade.Look(background="#102030", rowheight=44)
    button = tkfacade.Button(window, "go")
    table = tkfacade.Table(window, columns=(tkfacade.TreeColumnSpec(name="n"),))

    button.look = look
    table.look = look

    style = ttk.Style(window._tk)
    button_style = str(button._tk.cget("style"))
    assert style.lookup(button_style, "background") == "#102030"
    assert style.lookup(button_style, "rowheight") == ""
    treeview_style = str(table._treeview.cget("style"))
    assert style.lookup(treeview_style, "background") == "#102030"
    assert str(style.lookup(treeview_style, "rowheight")) == "44"


def test_a_base_value_beats_the_themes_own_state_maps(window: tkfacade.Window, pump: Pump) -> None:
    """What you set is what you see, in states the theme maps against you.

    The facade's main value over raw ttk. Every theme Tk ships maps foreground for the disabled state on the root style, and a map beats a configure from anywhere up the chain — so a caller writing plain configuration loses silently in exactly this state. The look writes its base through the map layer with a match-everything entry, so the disabled lookup answers the caller, not the theme.
    """
    look = tkfacade.Look(foreground="#123456")
    button = tkfacade.Button(window, "go")
    button.look = look

    style = ttk.Style(window._tk)
    worn = str(button._tk.cget("style"))
    assert style.lookup(worn, "foreground") == "#123456"
    assert style.lookup(worn, "foreground", ["disabled"]) == "#123456"


def test_a_situation_layer_wins_only_in_its_situation(window: tkfacade.Window, pump: Pump) -> None:
    """A situation value overrides the base there and nowhere else.

    The two layers' precedence as the rulings state it: situation entries ride ahead of the catch-all in one first-match map, so the disabled value holds exactly there while every unnamed situation — active included — falls through to the base.
    """
    look = tkfacade.Look(foreground="#111111")
    look.disabled.foreground = "#999999"
    button = tkfacade.Button(window, "go")
    button.look = look

    style = ttk.Style(window._tk)
    worn = str(button._tk.cget("style"))
    assert style.lookup(worn, "foreground") == "#111111"
    assert style.lookup(worn, "foreground", ["disabled"]) == "#999999"
    assert style.lookup(worn, "foreground", ["active"]) == "#111111"


def test_editing_a_worn_look_repaints_every_wearer(window: tkfacade.Window, pump: Pump) -> None:
    """Two widgets share one look; one edit reaches both live.

    The shared half of ruling 1: a look is one appearance many widgets wear, so consistency is an edit in one place. The two wearers are different kinds on purpose — the rewrite must reach every minted kind, not the last one worn.
    """
    look = tkfacade.Look(background="#101010")
    first = tkfacade.Button(window, "first")
    second = tkfacade.Checkbutton(window, "second")
    first.look = look
    second.look = look

    look.background = "#eeeeee"

    style = ttk.Style(window._tk)
    assert style.lookup(str(first._tk.cget("style")), "background") == "#eeeeee"
    assert style.lookup(str(second._tk.cget("style")), "background") == "#eeeeee"


def test_a_cleared_value_returns_the_theme_answer(window: tkfacade.Window, pump: Pump) -> None:
    """Assigning None unsets: the option falls back to the theme's own.

    Unsetting must actually leave: a map written once and merely abandoned would keep answering the old value forever, so the rewrite tracks what it wrote before and clears what left. Asserted as "not ours any more" rather than a literal theme colour, which is the theme's to choose.
    """
    look = tkfacade.Look(background="#0a0b0c")
    button = tkfacade.Button(window, "go")
    button.look = look
    style = ttk.Style(window._tk)
    worn = str(button._tk.cget("style"))
    assert style.lookup(worn, "background") == "#0a0b0c"

    look.background = None

    assert style.lookup(worn, "background") != "#0a0b0c"


def test_none_reverts_a_widget_to_the_base_style(window: tkfacade.Window, pump: Pump) -> None:
    """``look = None`` takes the minted style off the widget.

    The revert door: the widget returns to the library's base style and the property answers None, so wearing is fully reversible and the look itself is untouched for its other wearers.
    """
    look = tkfacade.Look(background="#222222")
    button = tkfacade.Button(window, "go")
    button.look = look
    assert str(button._tk.cget("style"))

    button.look = None

    assert not str(button._tk.cget("style"))
    assert button.look is None


def test_a_name_outside_the_vocabulary_is_refused(window: tkfacade.Window, pump: Pump) -> None:
    """A misspelling raises instead of becoming a value nothing reads.

    The ruling's boundary: a caller may set a real option a widget ignores, but a name that is no styling option at all is a typo, and ttk's own silence about those is exactly what the probe existed to overcome. The situation layer refuses the same way.
    """
    look = tkfacade.Look()

    with pytest.raises(AttributeError):
        look.backgroud = "#222222"
    with pytest.raises(AttributeError):
        look.disabled.colour = "#222222"


def test_parts_dress_their_own_style(window: tkfacade.Window, pump: Pump) -> None:
    """A part section writes the part's style beside the widget's own.

    Ruling 5: one look object carries a compound widget whole. The tab value lands on the minted tab style hanging off the widget's own minted name — the suffix rule the sub-style table records — and the clam-mapped tab background (settable only through the map layer, per the probe) is reachable precisely because every write rides that layer.
    """
    look = tkfacade.Look(background="#303030")
    look.tab.background = "#505050"
    tabs = tkfacade.TabFrame(window)
    tabs.look = look

    style = ttk.Style(window._tk)
    worn = str(tabs._tk.cget("style"))
    assert style.lookup(worn, "background") == "#303030"
    assert style.lookup(f"{worn}.Tab", "background") == "#505050"


def test_a_bank_and_a_scrollable_dress_all_their_principals(
    window: tkfacade.Window, pump: Pump
) -> None:
    """Composites with several themed principals wear the look on each.

    The plural principals rule: a bank's look reaches every button, and a scrollable's reaches its gutter bars — the facade unit dresses as one thing. The text box's classic text widget is skipped, not refused: the look is held (the property answers it) with the incompatible remainder simply not applying, per the ruling.
    """
    look = tkfacade.Look(background="#404040")
    bank = tkfacade.ChoiceButtons(window, ("a", "b"))
    box = tkfacade.TextBox(window, "words")
    bank.look = look
    box.look = look

    assert all(str(b._tk_button.cget("style")) for b in bank.buttons)
    bars = list(box._scroll_bars.values())
    assert bars and all(str(bar.cget("style")) for bar in bars)
    assert box.look is look


def test_a_look_serves_one_interpreter_at_a_time(window: tkfacade.Window, pump: Pump) -> None:
    """A second live interpreter is refused, the transport rule.

    Styles live per interpreter, so a look's minted names mean nothing on another root; serving both would silently give the second interpreter unstyled names. The refusal mirrors the observables' transport rule, and rebinding after the first interpreter dies is the same allowance — not separately pinned here, the mechanism being the transport's.
    """
    look = tkfacade.Look(background="#151515")
    tkfacade.Button(window, "go").look = look
    other = Root()
    try:
        held = tkfacade.Window(title="other", root=other)
        stranger = tkfacade.Button(held, "far")
        with pytest.raises(RuntimeError):
            stranger.look = look
    finally:
        other.destroy()


def test_the_construction_door_wears_the_look_from_the_start(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``look=`` at construction is the property's other door.

    The two-door shape the library keeps: what the property does live, the constructor option does at birth, both running one path — the option is applied through the same setter, so every rule above holds for it without separate pinning.
    """
    look = tkfacade.Look(background="#313233")

    button = tkfacade.Button(window, "go", look=look)

    assert button.look is look
    assert str(button._tk.cget("style"))


def test_a_scale_wearing_a_look_answers_the_looks_values(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A horizontal scale's worn style resolves to the look, not the theme.

    The look wrote LookN.TScale but the widget wears LookN.Horizontal.TScale. ttk derives a style's parent by stripping the first dotted component — Horizontal.TScale → TScale — which never reaches LookN.TScale. The fix writes the oriented spellings (LookN.Horizontal.TScale, LookN.Vertical.TScale) for every oriented kind, so the style the widget actually wears carries the look's values directly.
    """
    look = tkfacade.Look(troughcolor="#ff0000", background="#00ff00")
    scale = tkfacade.FloatScale(window, start=0.0, end=10.0, look=look)
    scale.grid(row=0, column=0)
    pump(window)

    style = ttk.Style(window._tk)
    worn = str(scale._scale.cget("style"))
    assert style.lookup(worn, "troughcolor") == "#ff0000"
    assert style.lookup(worn, "background") == "#00ff00"


def test_editing_a_look_reaches_an_oriented_wearer(window: tkfacade.Window, pump: Pump) -> None:
    """Changing the look after wear repaints an oriented widget.

    The _rewrite path must also write the oriented spelling, since editing a worn look re-mints every style it wrote before. The same mistargeting applies to _rewrite as to the initial _write.
    """
    look = tkfacade.Look(troughcolor="#ff0000")
    scale = tkfacade.FloatScale(window, start=0.0, end=10.0, look=look)
    scale.grid(row=0, column=0)
    pump(window)
    style = ttk.Style(window._tk)
    worn = str(scale._scale.cget("style"))

    look.troughcolor = "#0000ff"

    assert style.lookup(worn, "troughcolor") == "#0000ff"


def test_clearing_a_value_returns_an_oriented_kind_to_the_theme(
    window: tkfacade.Window, pump: Pump
) -> None:
    """Unsetting troughcolor on a worn look drops it from the oriented style.

    The clearing path also rewrites the oriented name, so the value leaves the widget. Asserted as "not ours any more" per the existing clearing test — the theme colour is the theme's own.
    """
    look = tkfacade.Look(troughcolor="#ff0000")
    scale = tkfacade.FloatScale(window, start=0.0, end=10.0, look=look)
    scale.grid(row=0, column=0)
    pump(window)
    style = ttk.Style(window._tk)
    worn = str(scale._scale.cget("style"))
    assert style.lookup(worn, "troughcolor") == "#ff0000"

    look.troughcolor = None

    assert style.lookup(worn, "troughcolor") != "#ff0000"
