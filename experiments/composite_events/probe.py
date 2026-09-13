"""Witness how events reach a wrapper whose widget holds the real one.

Run with::

    xvfb-run -a uv run python -m experiments.composite_events.probe

Several wrappers are a frame with the working widget inside it —
`TextBox`, `Tree`, `Listbox`, `TitleEntry`, the scales, and `Surface`
with every media display built on it. `BaseWidget.bind` binds the
frame, and Tk delivers an event to the widget it happened in, then
runs that widget's bindtags: the widget, its class, the toplevel, and
``all``. The parent frame is in none of them, so nothing a user does
inside such a wrapper reaches a subscriber.

The proposed repair puts the frame's own path into each inner widget's
bindtags, letting Tk route the events and leaving `bind`, `unbind` and
the dispatch untouched. Delivery that way is easy to witness; three
things about it are not, and this probe settles them: whether a
consumer's ``break`` still suppresses the inner widget's class
behaviour when it arrives by the routed tag, whether the tag's
position in the chain decides that, and whether delivery stays exactly
once. It also pins what the repair depends on — what
``Event.widget`` answers, that unbinding still works, and that a raw
binding already on an inner widget keeps running with a routed tag
ahead of it.

Keystrokes are avoided throughout. An earlier attempt tested
suppression with ``<KeyPress>`` and failed at baseline: the keystroke
never landed even with nothing subscribed, focus under a headless
server defeating the test rather than the mechanism. A click on a text
widget moves its insert cursor through the class binding, which is
observable without focus and is what these checks read.

Expectations are the behavior witnessed on Tk 8.6.14 (threaded Tcl,
X11), CPython 3.14. A FAIL is a finding. Every check prints its
verdict; the exit status is the number that failed.
"""

import sys
import tkinter as tk
from tkinter import ttk

Report = tuple[bool, str]


def rig() -> tuple[tk.Tk, ttk.Frame, tk.Text]:
    """A realized frame holding a text widget, the shape of every composite."""
    root = tk.Tk()
    root.geometry("400x200")
    frame = ttk.Frame(root)
    frame.grid(row=0, column=0, sticky="nsew")
    text = tk.Text(frame, width=40, height=6)
    text.insert("1.0", "\n".join(f"line {index}" for index in range(20)))
    text.grid(row=0, column=0, sticky="nsew")
    root.update()
    return root, frame, text


def route(inner: tk.Misc, host: tk.Misc, /, *, at_head: bool = True) -> None:
    """Put ``host``'s path into ``inner``'s bindtags, at one end or the other."""
    tags = inner.bindtags()
    inner.bindtags((str(host), *tags) if at_head else (tags[0], str(host), *tags[1:]))


def check_an_inner_event_reaches_nobody_unrouted() -> Report:
    """The defect: a click inside the composite runs none of the frame's bindings."""
    root, frame, text = rig()
    heard: list[str] = []
    frame.bind("<Button-1>", lambda _event: heard.append("frame"), add="+")
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    inner_heard = list(heard)
    frame.event_generate("<Button-1>", x=1, y=1)
    root.update()
    tags = text.bindtags()
    root.destroy()
    ok = inner_heard == [] and heard == ["frame"] and str(frame) not in tags
    return ok, (
        f"a click on the inner widget was heard {len(inner_heard)} times and one on "
        f"the frame {len(heard)}; the inner chain is {tags!r} -- the frame is not in it"
    )


def check_a_routed_tag_delivers() -> Report:
    """With the frame's path in the chain, the inner click arrives."""
    root, frame, text = rig()
    heard: list[str] = []
    frame.bind("<Button-1>", lambda _event: heard.append("frame"), add="+")
    route(text, frame)
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    tags = text.bindtags()
    root.destroy()
    ok = heard == ["frame"] and tags[0] == str(frame)
    return ok, (f"heard {heard!r} once through the routed tag; the chain is now {tags!r}")


def check_delivery_is_exactly_once() -> Report:
    """One event fires one subscriber once, from either the inner widget or the frame."""
    root, frame, text = rig()
    heard: list[str] = []
    frame.bind("<Button-1>", lambda event: heard.append(str(event.widget)), add="+")
    route(text, frame)
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    from_inner = len(heard)
    frame.event_generate("<Button-1>", x=1, y=1)
    root.update()
    from_frame = len(heard) - from_inner
    root.destroy()
    ok = from_inner == 1 and from_frame == 1
    return ok, (
        f"the inner widget delivered {from_inner} time(s) and the frame {from_frame}; "
        "the routed tag adds a road, not a duplicate"
    )


def check_a_toplevel_binding_does_not_double_with_a_routed_tag() -> Report:
    """A composite in a window fires the window's subscriber once, not twice."""
    root, frame, text = rig()
    heard: list[str] = []
    root.bind("<Button-1>", lambda _event: heard.append("toplevel"), add="+")
    route(text, frame)
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    count = len(heard)
    root.destroy()
    ok = count == 1
    return ok, (
        f"the toplevel's subscriber ran {count} time(s) -- the toplevel is already in "
        "every chain, and routing to the frame does not put it there twice"
    )


def check_break_from_a_head_tag_suppresses_the_class_binding() -> Report:
    """A consumer's break, arriving by a head-inserted tag, stops the widget's own act."""
    root, frame, text = rig()
    text.mark_set("insert", "1.0")
    route(text, frame)
    frame.bind("<Button-1>", lambda _event: "break", add="+")
    text.event_generate("<Button-1>", x=60, y=40)
    root.update()
    landed = str(text.index("insert"))
    root.destroy()
    ok = landed == "1.0"
    return ok, (
        f"the insert cursor sat at {landed!r} after a click a class binding would have "
        "moved it with -- break from the frame's tag reached the class binding"
        if ok
        else f"the cursor moved to {landed!r}: break did NOT suppress the class binding"
    )


def check_break_from_a_second_place_tag_also_suppresses() -> Report:
    """The same, with the tag after the inner widget's own rather than before it."""
    root, frame, text = rig()
    text.mark_set("insert", "1.0")
    route(text, frame, at_head=False)
    frame.bind("<Button-1>", lambda _event: "break", add="+")
    text.event_generate("<Button-1>", x=60, y=40)
    root.update()
    landed = str(text.index("insert"))
    tags = text.bindtags()
    root.destroy()
    ok = landed == "1.0"
    return ok, (
        f"with the chain {tags!r} the cursor sat at {landed!r} -- either position "
        "carries a consumer's verdict"
        if ok
        else f"with the chain {tags!r} the cursor moved to {landed!r}: only the head "
        "position carries a consumer's verdict"
    )


def check_an_observer_does_not_suppress() -> Report:
    """A subscriber returning nothing leaves the widget's own behaviour alone."""
    root, frame, text = rig()
    text.mark_set("insert", "1.0")
    route(text, frame)
    seen: list[str] = []
    frame.bind("<Button-1>", lambda _event: seen.append("observed"), add="+")
    text.event_generate("<Button-1>", x=60, y=40)
    root.update()
    landed = str(text.index("insert"))
    root.destroy()
    ok = seen == ["observed"] and landed != "1.0"
    return ok, (
        f"the observer ran and the cursor still moved to {landed!r} -- observing costs "
        "the widget nothing, which is what makes the consumer's verdict meaningful"
    )


def check_a_raw_binding_on_the_inner_widget_survives_routing() -> Report:
    """A binding already on an inner widget keeps running with a routed tag ahead."""
    root, frame, text = rig()
    order: list[str] = []
    text.bind("<Button-1>", lambda _event: order.append("inner"), add="+")
    route(text, frame)
    frame.bind("<Button-1>", lambda _event: order.append("frame"), add="+")
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    root.destroy()
    ok = order == ["frame", "inner"]
    return ok, (
        f"both ran, in the order {order!r} -- an existing inner binding is not lost, "
        "though a head tag now runs before it (the VideoPlayer seek-scale case)"
    )


def check_unbinding_the_frame_stops_the_routed_road_too() -> Report:
    """Removing the frame's binding silences the inner widget as well."""
    root, frame, text = rig()
    heard: list[str] = []
    funcid = frame.bind("<Button-1>", lambda _event: heard.append("frame"), add="+")
    route(text, frame)
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    before = len(heard)
    frame.unbind("<Button-1>", funcid)
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    root.destroy()
    ok = before == 1 and len(heard) == 1
    return ok, (
        f"heard {before} time(s) while bound and {len(heard) - before} after unbinding "
        "-- the subscription bookkeeping needs no change"
    )


def check_the_event_names_the_inner_widget_not_the_frame() -> Report:
    """The delivered event reports where it happened, which no wrapper answers for."""
    root, frame, text = rig()
    reported: list[str] = []
    frame.bind("<Button-1>", lambda event: reported.append(str(event.widget)), add="+")
    route(text, frame)
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    inner_path, frame_path = str(text), str(frame)
    root.destroy()
    ok = reported == [inner_path]
    return ok, (
        f"the event named {reported!r}, which is the inner widget and not {frame_path!r} "
        "-- so the facade must walk up to the wrapper that owns it, or answer None"
    )


def check_a_master_walk_finds_the_owning_frame() -> Report:
    """Walking up from the reported widget reaches the frame a wrapper would hold."""
    root, frame, text = rig()
    found: list[str] = []

    def walk(event: tk.Event[tk.Misc]) -> None:
        widget: tk.Misc | None = event.widget
        while widget is not None and str(widget) != str(frame):
            widget = getattr(widget, "master", None)
        found.append(str(widget) if widget is not None else "nothing")

    frame.bind("<Button-1>", walk, add="+")
    route(text, frame)
    text.event_generate("<Button-1>", x=10, y=10)
    root.update()
    expected = str(frame)
    root.destroy()
    ok = found == [expected]
    return ok, (
        f"the walk from the inner widget reached {found!r} -- the resolution the "
        "dispatch needs, in place of giving up at the first miss"
    )


CHECKS: tuple[tuple[str, object], ...] = (
    ("unrouted, an inner event is lost", check_an_inner_event_reaches_nobody_unrouted),
    ("a routed tag delivers", check_a_routed_tag_delivers),
    ("delivery is exactly once", check_delivery_is_exactly_once),
    (
        "a toplevel binding does not double",
        check_a_toplevel_binding_does_not_double_with_a_routed_tag,
    ),
    ("break from a head tag suppresses", check_break_from_a_head_tag_suppresses_the_class_binding),
    ("break from a second-place tag too", check_break_from_a_second_place_tag_also_suppresses),
    ("an observer suppresses nothing", check_an_observer_does_not_suppress),
    ("a raw inner binding survives", check_a_raw_binding_on_the_inner_widget_survives_routing),
    ("unbinding stops the routed road", check_unbinding_the_frame_stops_the_routed_road_too),
    ("the event names the inner widget", check_the_event_names_the_inner_widget_not_the_frame),
    ("a master walk finds the owner", check_a_master_walk_finds_the_owning_frame),
)


def main() -> int:
    """Run every check, print each verdict, and return the failure count."""
    probe = tk.Tk()
    print(
        f"Tk {probe.tk.call('info', 'patchlevel')}, "
        f"threaded Tcl {probe.tk.call('set', 'tcl_platform(threaded)')}, "
        f"{sys.platform}"
    )
    probe.destroy()
    failures = 0
    for name, check in CHECKS:
        ok, detail = check()  # type: ignore[operator]
        failures += 0 if ok else 1
        print(f"{name:38s} {'ok  ' if ok else 'FAIL'}  {detail}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
