""":class:`~tkfacade.LabelFrame`: a frame with a caption on its border.

Everything :class:`~tkfacade.Frame` is, plus a caption saying what the
group inside is for. The inherited half is tested here too, whole:
this is the first widget built on the container seam, and the four
properties it inherits are the half that would break quietly if that
seam were wrong.
"""

import tkinter as tk

import pytest

import tkfacade

pytestmark = pytest.mark.gui


def test_it_is_a_frame_and_answers_the_inherited_contract(window: tkfacade.Window) -> None:
    """The four properties a frame carries work on a captioned one.

    The seam this widget is the first to use: Frame builds whatever its _widget_type names, and ttk.LabelFrame answers every option a frame's properties read even though it is not a ttk.Frame — the two are siblings under ttk.Widget. A seam that had gone wrong would surface right here, in the inherited half.
    """
    group = tkfacade.LabelFrame(window, "Group", relief="groove", padding=8, width=120, height=60)

    assert group.relief == "groove"
    assert group.padding == (8,)
    assert group.width == 120
    assert group.height == 60

    group.relief = "flat"
    group.padding = 2

    assert group.relief == "flat"
    assert group.padding == (2,)


def test_a_string_caption_round_trips(window: tkfacade.Window) -> None:
    """The caption is set at construction and afterwards.

    The ordinary case, read back through Tk rather than through a remembered copy. A frame built with no caption answers the empty string, which is the next test's starting point.
    """
    group = tkfacade.LabelFrame(window, "Sound")

    assert group.caption == "Sound"

    group.caption = "Display"

    assert group.caption == "Display"
    assert str(group._tk.cget("text")) == "Display"


def test_a_widget_caption_replaces_the_string_and_gives_it_back(
    window: tkfacade.Window,
) -> None:
    """A widget shows in place of the text, and clearing it restores the text.

    One slot, one setting, in both directions. Tk keeps a string and a widget as two options with the widget shadowing the string — witnessed, clearing the widget brings the old string back — so a wrapper exposing both would hand a caller two controls for one visible thing, which is the shape ScrollbarPolicy was rejected for. Reading the caption answers whichever is showing, and assigning either replaces the other.
    """
    enabled = tkfacade.Checkbutton(window, "Enabled")
    group = tkfacade.LabelFrame(window, "Sound")
    group.grid(row=0, column=0)
    window._tk.update()

    group.caption = enabled

    assert group.caption is enabled
    assert str(group._tk.cget("labelwidget")) == str(enabled._tk)

    group.caption = "Sound again"

    assert group.caption == "Sound again"
    assert str(group._tk.cget("labelwidget")) == ""


def test_a_widget_caption_stays_the_callers_widget(window: tkfacade.Window) -> None:
    """The captioning widget is displayed, not adopted.

    A caption widget built as a sibling — which is why the constructor can take one at all, the frame not needing to exist first — and it remains entirely the caller's. It hears its own events and answers its own state, so a checkbutton captioning a group it enables works as a checkbutton, which is the whole reason for supporting a widget here.
    """
    enabled = tkfacade.Checkbutton(window, "Enabled")
    group = tkfacade.LabelFrame(window, caption=enabled)
    group.grid(row=0, column=0)
    window._tk.update()
    heard: list[str] = []
    enabled.bind(tkfacade.Press(tkfacade.MouseButton.LEFT), lambda _event: heard.append("clicked"))

    enabled._tk.event_generate("<Button-1>", x=2, y=2)
    window._tk.update()

    assert heard == ["clicked"]
    assert enabled.checked is False
    enabled.invoke()
    assert enabled.checked is True


def test_the_caption_moves_around_the_border(window: tkfacade.Window) -> None:
    """caption_position places the caption, and refuses what Tk refuses.

    The twelve places EdgePosition names, and the one it does not: a caption is on a border, and a border has no centre — Tk refuses "center" outright. The refusal is Tk's own and is left to it rather than duplicated, since the type already excludes the value and only a caller ignoring it can get there.
    """
    group = tkfacade.LabelFrame(window, "Group")
    started = group.caption_position

    group.caption_position = "se"

    assert started == "nw"
    assert group.caption_position == "se"

    with pytest.raises(tk.TclError):
        group.caption_position = "center"  # type: ignore[assignment]


def test_it_masters_and_lays_out_children(window: tkfacade.Window) -> None:
    """A captioned frame contains a layout like any other.

    The half that makes it a container rather than a decoration: a child built with the group as its parent is mastered by it, laid out inside it, and reachable through the mapping the wrapper proxies. Worth pinning because the caption occupies part of the border, which is exactly where a container's geometry could have gone wrong.
    """
    group = tkfacade.LabelFrame(window, "Group", padding=4)
    group.grid(row=0, column=0)
    inside = tkfacade.Button(group, "Press")
    inside.grid(row=0, column=0)
    window._tk.update()

    assert str(inside._tk.winfo_parent()) == str(group._tk)
    assert inside._tk.winfo_ismapped()
    assert group.children[str(inside._tk).rsplit(".", 1)[-1]] is inside._tk
