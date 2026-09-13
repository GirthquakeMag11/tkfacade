"""Events reaching a wrapper built from a frame and the widgets inside it.

Several wrappers are that shape, and until this was repaired none of
them heard anything a user did inside them: `BaseWidget.bind` binds the
frame, and Tk runs an event through the bindtags of the widget it
happened in — the widget, its class, the toplevel, ``all`` — which
never contain the parent. Each composite now routes its parts, and this
suite holds the repair in place: the delivery it restores, the
resolution that names the right wrapper, and an audit that fails a
future composite which forgets.

The mechanism is `experiments/composite_events/`'s.
"""

import inspect

import pytest

import tkfacade
from tkfacade.widget import BaseWidget, Widget

pytestmark = pytest.mark.gui

WORDS = ("alpha", "beta", "gamma")


def _build_every_widget(window: tkfacade.Window) -> dict[str, Widget]:
    """One of every widget a caller can lay out, ready to be walked.

    Tk itself says a menu is not part of the window's event surface. Every ordinary descendant carries the toplevel in its bindtags -- a sizegrip nested two frames deep reads ('...sizegrip', 'TSizegrip', '.', 'all') -- while a popped menu reads ('...menu', 'Menu', 'all') with the toplevel dropped. A menu is its own surface, posted under a grab, and what a user does in one reaches the facade as the row's command or its observable, which is a better channel than a raw event. Routing the wrapper's tag in would put menu clicks through the menubutton's subscribers as though the button had been clicked, and would let a consumer -- whose completion suppresses Tk's default action -- stop a row from ever activating.
    """
    return {
        "Button": tkfacade.Button(window, "go"),
        "Checkbutton": tkfacade.Checkbutton(window, "tick"),
        "ChoiceBox": tkfacade.ChoiceBox(window, WORDS),
        "ChoiceButtons": tkfacade.ChoiceButtons(window, WORDS),
        "ChoiceSpinner": tkfacade.ChoiceSpinner(window, WORDS),
        "Combobox": tkfacade.Combobox(window, suggestions=WORDS),
        "Entry": tkfacade.Entry(window),
        "FloatScale": tkfacade.FloatScale(window, start=0.0, end=1.0),
        "FloatSpinbox": tkfacade.FloatSpinbox(window, minimum=0.0, maximum=1.0),
        "Frame": tkfacade.Frame(window),
        "ImageDisplay": tkfacade.ImageDisplay(window, width=32, height=32),
        "ImageLabel": tkfacade.ImageLabel(window),
        "IntScale": tkfacade.IntScale(window, start=0, end=10),
        "IntSpinbox": tkfacade.IntSpinbox(window, minimum=0, maximum=10),
        "ItemBasedProgressBar": tkfacade.ItemBasedProgressBar(
            window, orient="horizontal", length=60, maximum=4
        ),
        "LabelFrame": tkfacade.LabelFrame(window, "Group"),
        "Listbox": tkfacade.Listbox(window, WORDS),
        "MediaPlayer": tkfacade.MediaPlayer(window, width=32, height=32),
        "Menubutton": tkfacade.Menubutton(window, "File"),
        "OptionMenu": tkfacade.OptionMenu(window, WORDS),
        "PercentageBasedProgressBar": tkfacade.PercentageBasedProgressBar(
            window, orient="horizontal", length=60
        ),
        "PanedFrame": tkfacade.PanedFrame(window),
        "Separator": tkfacade.Separator(window),
        "StackFrame": tkfacade.StackFrame(window),
        "Table": tkfacade.Table(window, columns=(tkfacade.TreeColumnSpec(name="n"),)),
        "TabFrame": tkfacade.TabFrame(window),
        "TextBox": tkfacade.TextBox(window),
        "TextLabel": tkfacade.TextLabel(window, text="text"),
        "TitleEntry": tkfacade.TitleEntry(window, title="Title"),
        "Tree": tkfacade.Tree(window, columns=(tkfacade.TreeColumnSpec(name="n"),)),
    }


NOT_BUILT = frozenset(
    {
        # abstract: a caller lays out an implementation, never these
        "AbstractMediaDisplay",
        "AbstractMultiFrame",
        "AbstractScale",
        "AbstractScrollable",
        "AbstractSpinbox",
        "AbstractTextInterface",
        "Surface",
        # the video display needs a native backend, and reaches its
        # routing through Surface, which ImageDisplay covers here
        "VideoDisplay",
        # windows, not widgets laid out inside one
        "Root",
        "Window",
        # a window's own top row, not something laid out inside one: Tk
        # refuses to pack or place a menu at all, and does not show the
        # menu it is given -- it clones it, and a binding firing from
        # that clone reports a path nametowidget cannot resolve, so the
        # bar has no routable event surface to audit
        "Menubar",
    }
)
"""Widget classes the roster does not build, each for a stated reason."""


NOT_ROUTED: dict[str, frozenset[str]] = {
    "Menubutton": frozenset({"Menu"}),
    "OptionMenu": frozenset({"Menu"}),
}
"""Tk classes each wrapper deliberately leaves unrouted, by the reason above."""


def _unrouted_parts(widget: Widget, excused: frozenset[str] = frozenset()) -> list[str]:
    """The widget's own descendants that are neither wrappers nor routed to it.

    Args:
        widget (Widget): The wrapper to walk.
        excused (frozenset[str]): Tk class names left unrouted on
            purpose, per :data:`NOT_ROUTED`; a part of such a class is
            skipped along with everything under it.
    """
    host = str(widget._tk)
    loose: list[str] = []
    pending = list(widget._tk.winfo_children())
    while pending:
        part = pending.pop()
        if part.winfo_class() in excused:
            continue
        try:
            widget.nametowrapper(part)
        except KeyError, Exception:
            if host not in part.bindtags():
                loose.append(str(part))
            pending.extend(part.winfo_children())
    return loose


def test_every_widget_routes_the_parts_it_is_built_from(window: tkfacade.Window) -> None:
    """No wrapper holds a part whose events would reach nobody.

    The audit that makes the rule enforceable rather than remembered: a wrapper's events are the events of everything it is made of, so any descendant that is not itself a wrapper must carry the routing tag. A composite built later that forgets fails here instead of shipping deaf, which is the failure this whole repair exists to answer — the original went unnoticed because no test ever bound an inner-widget event on a composite.
    """
    built = _build_every_widget(window)
    window._tk.update()

    unrouted = {
        name: _unrouted_parts(widget, NOT_ROUTED.get(name, frozenset()))
        for name, widget in built.items()
    }

    assert {name: loose for name, loose in unrouted.items() if loose} == {}


def test_the_roster_covers_every_widget_a_caller_can_lay_out(
    window: tkfacade.Window,
) -> None:
    """Every exported widget is either built above or excused by name.

    The other half of the enforcement, and the half that is easy to forget: an audit is only as good as its roster. A new widget must be built above or excused here by name with a reason, so it cannot slip past the routing check by simply not being in the list.
    """
    exported = {
        name
        for name in dir(tkfacade)
        if not name.startswith("_")
        and inspect.isclass(getattr(tkfacade, name))
        and issubclass(getattr(tkfacade, name), BaseWidget)
    }

    assert exported - NOT_BUILT == set(_build_every_widget(window))


def test_a_click_inside_a_composite_reaches_a_subscriber(window: tkfacade.Window) -> None:
    """The delivery the repair restores, on the widget that first showed the defect.

    A click where a user actually clicks — on the text area, not the frame's one-pixel border, which was the only place a subscriber could be reached before. The event names the box rather than the text widget inside it: what a caller bound to is what they hear about, and the widget the event happened in is a private part they were never given.
    """
    box = tkfacade.TextBox(window, "hello", width=30, height=4)
    box.grid(row=0, column=0)
    window._tk.update()
    heard: list[tkfacade.Event] = []
    box.bind(tkfacade.Press(tkfacade.MouseButton.LEFT), heard.append)

    box._text.event_generate("<Button-1>", x=10, y=10)
    window._tk.update()

    assert len(heard) == 1
    assert heard[0].widget is box


def test_a_selection_reaches_a_subscriber_on_a_tree_and_a_list(
    window: tkfacade.Window,
) -> None:
    """The virtual events these widgets fire now reach the facade.

    The claim the earlier design made and had to withdraw: a tree's selection is reachable through the facade. It is now, and so is a list's, which is what lets either be used without reaching past the wrapper to the private widget inside it.
    """
    tree = tkfacade.Table(window, columns=(tkfacade.TreeColumnSpec(name="n"),))
    for index in range(3):
        tree.insert(n=str(index))
    tree.grid(row=0, column=0)
    box = tkfacade.Listbox(window, WORDS)
    box.grid(row=1, column=0)
    window._tk.update()
    from_tree: list[tkfacade.Event] = []
    from_list: list[tuple[str, ...]] = []
    tree.bind(tkfacade.Virtual(tkfacade.VirtualEvent.TREEVIEW_SELECT), from_tree.append)
    box.bind(
        tkfacade.Virtual(tkfacade.VirtualEvent.TREEVIEW_SELECT),
        lambda _event: from_list.append(box.selected_items),
    )

    tree.select(list(tree)[1])
    box.select(2)
    window._tk.update()

    assert len(from_tree) == 1
    assert from_tree[0].widget is tree
    assert from_list == [("gamma",)]


def test_a_window_binding_still_names_the_innermost_wrapper(
    window: tkfacade.Window,
) -> None:
    """Resolving outward does not cost the precision window bindings had.

    The regression the resolution change could have caused. A window hears its descendants because the toplevel is in every chain, and before the repair the event named whatever wrapper was registered for the exact widget — a button, or None for a composite's private part. Walking outward to the nearest wrapper keeps the button answering as itself while making the part answer as the box that owns it.
    """
    button = tkfacade.Button(window, "go")
    button.grid(row=0, column=0)
    box = tkfacade.TextBox(window, "hello", width=20, height=3)
    box.grid(row=1, column=0)
    window._tk.update()
    named: list[object] = []
    window.bind(tkfacade.Press(tkfacade.MouseButton.LEFT), lambda event: named.append(event.widget))

    button._tk.event_generate("<Button-1>", x=2, y=2)
    box._text.event_generate("<Button-1>", x=10, y=10)
    window._tk.update()

    assert named == [button, box]
