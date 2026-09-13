"""The :class:`~tkfacade.Window` wrapper: geometry writes, limits, and teardown.

The centerpiece is the requested-geometry memo — the fix for the
ledger's old model case, where several writes within one mainloop
iteration dropped each other's dimensions. Everything here needs a
live window, so the suite rides the ``window`` fixture and carries the
``gui`` marker.
"""

import gc
import io
import threading
import time
import tkinter as tk
from collections.abc import Callable

import pytest
from PIL import Image

import tkfacade
from tkfacade.widget import BaseWidget
from tkfacade.window import Root, get_root

pytestmark = pytest.mark.gui


def _png() -> bytes:
    """An 8x8 solid red PNG, as encoded bytes."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_geometry_writes_within_one_iteration_all_land(
    window: tkfacade.Window, pump: Callable[[tk.Misc | BaseWidget], None]
) -> None:
    """Four single-axis writes with no pump between them all survive.

    The regression test for the memo. Until Tk applies a geometry request it keeps reporting the old size, so before the fix each single-axis setter filled its gaps from that stale report and undid its predecessor — the second write here would have reverted the first. Four writes, one per axis, prove every setter fills gaps from the requested memo; the reads come after one pump because the contract is what the window ends up with, not what Tk reports mid-flight.
    """
    window.width = 512
    window.height = 384
    window.x_position = 60
    window.y_position = 80
    pump(window)

    assert window.width == 512
    assert window.height == 384
    assert window.x_position == 60
    assert window.y_position == 80


def test_configure_clears_the_memo(
    window: tkfacade.Window, pump: Callable[[tk.Misc | BaseWidget], None]
) -> None:
    """After Tk answers, a later write fills its gaps from the live report.

    The memo's other half: it must be forgotten once a <Configure> arrives, or a size the user has since dragged away from would be silently re-requested. The pump between the write groups delivers the <Configure> that clears the memo, so the second width write proves a post-memo gap-fill takes height from Tk's (now true) report rather than from a stale request.
    """
    window.width = 512
    window.height = 384
    pump(window)

    window.width = 200
    pump(window)

    assert window.width == 200
    assert window.height == 384


def test_geometry_getters_return_construction_values_before_tk_applies(root: Root) -> None:
    """The four getters answer with the constructor's values, not Tk's ``1x1+0+0`` placeholder.

    Tk answers 1x1+0+0 for every toplevel until the window manager applies its first geometry request, and the getters called _dimensions directly — so a freshly built Window(width=300) read width == 1. The setters already prefer the _requested memo for gap-filling; the getters now do the same, falling through to Tk once the memo has been cleared by a Configure event.
    """
    window = tkfacade.Window(root=root, width=300, height=200, x_position=80, y_position=90)

    assert window.width == 300
    assert window.height == 200
    assert window.x_position == 80
    assert window.y_position == 90


def test_read_modify_write_preserves_increments_across_reads(root: Root) -> None:
    """Adding 100 to width twice gives 500, not 101, when the memo still holds.

    Before the fix, `window.width` read Tk's 1x1+0+0 placeholder, so both writes computed 1+100=101 — the first increment was lost because the getter answered 1 where the setter had just written 400. The getter now prefers the memo, so the second read sees the first write's 400 and adds 100.
    """
    window = tkfacade.Window(root=root, width=300)

    window.width = window.width + 100
    window.width = window.width + 100

    assert window.width == 500


def test_title_defaults_to_the_class_name(root: Root) -> None:
    """A window built without a title is titled after its class.

    The default is ``type(self).__name__``, not the literal "Window", so a subclass gets its own name for free — this pins the mechanism on the base class where it is cheap to observe. Built directly rather than via the window fixture because the fixture always passes a title.
    """
    window = tkfacade.Window(root=root)

    assert window.title == "Window"


def test_size_limit_setters_preserve_the_other_axis(window: tkfacade.Window) -> None:
    """Writing one min/max axis leaves its partner untouched.

    Tk's wm minsize/maxsize only take both axes at once, so each single-axis property setter must read the other axis and pass it back through. min_height is written *after* min_width and both are re-read because the failure mode is the second write resetting the first axis to a default — the same clobber shape the geometry memo guards against, on a path the memo does not cover.
    """
    window.min_width = 120
    window.min_height = 90
    window.max_width = 800

    assert window.min_width == 120
    assert window.min_height == 90
    assert window.max_width == 800


def test_resizable_setters_preserve_the_other_axis(window: tkfacade.Window) -> None:
    """Writing one resizable axis leaves its partner untouched.

    Same read-modify-write contract as the size limits, on the remaining wm pair. Only one axis is written because the interesting assertion is the *unwritten* one: height must still hold Tk's default of resizable after width's setter passed it through. Identity rather than truthiness on purpose: wm resizable answers Tcl's 0/1 ints, and the properties promise real bools — an int leaking through satisfies any truthiness check while breaking every ``is False`` caller.
    """
    window.resizable_width = False

    assert window.resizable_width is False
    assert window.resizable_height is True


def test_destroy_unregisters_from_the_root(root: Root) -> None:
    """A destroyed window leaves the root's registry, its sibling stays.

    Window.destroy is rem_child plus Tk destroy, in that order; a wrapper that only destroyed the toplevel would leave the root's strong reference pinning the dead wrapper (and its icon) alive. The sibling exists so this pins unregistration specifically, separate from the last-window root cascade that test_root covers.
    """
    window = tkfacade.Window(title="doomed", root=root)
    keeper = tkfacade.Window(title="keeper", root=root)

    window.destroy()

    assert root.windows == (keeper,)
    assert not root.destroyed


def test_worker_threads_are_answered_while_the_mainloop_runs(root: Root) -> None:
    """``mainloop_running`` and ``get_root`` answer a worker mid-loop, promptly.

    run_mainloop used to enter the blocking loop inside GLOBAL_LOCK, so a worker's get_root or mainloop_running parked until the application exited — and the poll then answered False for a loop that was running when it was asked, which is exactly what the True here refutes. This is the suite's one real mainloop: only a genuinely running loop can show the lock being held across it, so the destroy is scheduled before entry and ends the loop by the last-window cascade. The join runs before the assertions so a scheduling hiccup surfaces as an empty answer list, not a race.
    """
    window = tkfacade.Window(title="t", root=root)
    answers: list[tuple[bool, bool]] = []

    def worker() -> None:
        time.sleep(0.15)
        running = window.mainloop_running()
        shared = get_root() is not None
        answers.append((running, shared))

    probe = threading.Thread(target=worker, daemon=True)
    window._tk.after(600, window.destroy)
    probe.start()
    window.run_mainloop()
    probe.join(timeout=2)

    assert answers == [(True, True)]


def test_a_bad_icon_leaves_no_window_behind(root: Root) -> None:
    """A failing icon decode raises before the window exists or registers.

    The constructor used to register on the root and build the live toplevel first and decode the icon last, so a bad path raised out of a call whose caller holds no reference — leaving a phantom window registered and on screen, and blocking the root's last-window teardown forever. Both halves of the leak are pinned: the registry through the public windows tuple, and the toplevel itself through the root's child count, because either alone could pass if the other regressed. The keeper window keeps the root alive so the assertion runs against a live registry rather than a cascading teardown.
    """
    keeper = tkfacade.Window(title="keeper", root=root)
    toplevels = len(root._tk.winfo_children())

    with pytest.raises(OSError):
        tkfacade.Window(title="doomed", icon="/nonexistent/icon.png", root=root)

    assert root.windows == (keeper,)
    assert len(root._tk.winfo_children()) == toplevels


def test_a_failure_after_the_toplevel_builds_unwinds_it(root: Root) -> None:
    """A raise between build and finish destroys the toplevel and registers nothing.

    The icon-ordering fix moved the decode ahead of the build, but registration still preceded it and every fallible step after the BaseWindow call could leave a live toplevel plus a phantom wrapper in root.windows — one whose every use raised AttributeError. The constructor now registers last and unwinds the toplevel on any raise in between; the smuggled string is the runtime-sourced bad value mypy cannot rule out, chosen to fail at Tk inside that window. The keeper keeps the unwind's last-window cascade from tearing the fixture root down with the doomed toplevel.
    """
    keeper = tkfacade.Window(title="keeper", root=root)
    toplevels = len(root._tk.winfo_children())

    with pytest.raises(tk.TclError):
        tkfacade.Window(title="doomed", root=root, max_width="nope")  # type: ignore[arg-type]

    assert root.windows == (keeper,)
    assert len(root._tk.winfo_children()) == toplevels


def test_window_destroy_is_idempotent_in_every_ordering(root: Root) -> None:
    """A second destroy is a no-op, around the last-window cascade too.

    Double destroy of a non-last window was already silent (Tcl ignores destroying a gone path on a live interpreter), but the last window's first destroy cascades the whole interpreter down, and Tk's destroy on a dead application raises — so the no-op became a TclError in exactly one ordering: shutdown code destroying its windows after the user beat it to the close button. All three orderings are driven — non-last twice, last twice, and titlebar-close then wrapper destroy, the realistic race — and the destroyed reads pin that the guard skips only the Tk call, never the cascade itself. get_root heals a fresh root for the third leg because the second killed the first.
    """
    first = tkfacade.Window(title="first", root=root)
    last = tkfacade.Window(title="last", root=root)

    first.destroy()
    first.destroy()
    last.destroy()
    last.destroy()

    assert root.destroyed

    healed = get_root()
    closed = tkfacade.Window(title="closed", root=healed)
    closed._tk.tk.call(str(closed._tk.protocol("WM_DELETE_WINDOW")))
    closed.destroy()

    assert healed.destroyed


def test_a_failed_construction_leaves_its_root_standing(root: Root) -> None:
    """The unwind of a sole doomed window does not take the caller's root.

    The unwind called BaseWindow.destroy, which runs the last-toplevel cascade — and with no other window alive that cascade killed the interpreter, so the "leaves nothing behind" promise also took something the caller made before the call: their root, silently dead, every retry raising "application has been destroyed". The suite's other unwind tests build a keeper window for exactly that reason; this one deliberately does not, because the bare root IS the exposed case. The retry is the cost refuted, and the child count pins that the toplevel itself still unwound — the fix must skip the cascade, not the destruction.
    """
    with pytest.raises(tk.TclError):
        tkfacade.Window(title="doomed", root=root, max_width="nope")  # type: ignore[arg-type]

    registered = root.windows
    assert not root.destroyed
    assert registered == ()
    assert len(root._tk.winfo_children()) == 0

    retry = tkfacade.Window(title="retry", root=root)

    assert root.windows == (retry,)


def test_a_window_icon_round_trips_as_a_wrapper(root: Root) -> None:
    """A window answers None until given an icon, then with the wrapper it scaled.

    The property's contract, and the one place it deliberately departs from TreeRow.image: window_icon is a transformation — a fixed 64x64 thumbnail — so the wrapper answered with is its result, never the caller's source. That last assertion is the whole point of saying so in the docstring, and it is why identity is asserted negatively here where the tree asserts it positively. The bare window is what stops the getter passing vacuously by answering with something regardless.
    """
    bare = tkfacade.Window(title="bare", root=root)
    iconed = tkfacade.Window(title="iconed", icon=_png(), root=root)
    source = tkfacade.small_icon(_png())

    built = iconed.icon
    iconed.icon = source

    assert bare.icon is None
    assert isinstance(built, tkfacade.ImageWrapper)
    assert isinstance(iconed.icon, tkfacade.ImageWrapper)
    assert iconed.icon is not built
    assert iconed.icon is not source


def test_a_window_icon_survives_collection(root: Root) -> None:
    """An icon set from a temporary is still a live Tk image after a collect.

    The sizegrip is reached as a window setting rather than a widget: the only place one is any use is this corner of this window, so there is nothing to construct and nothing to place. What follows tests the window's side of that, and the awkward half of it is stacking — the grip is built with the window, so everything laid out afterwards is a younger sibling that would otherwise take the corner.  Not tested: that dragging the grip resizes anything. There is no window manager under xvfb, so such a test would witness the harness rather than the widget. The gating that Tk's own Press proc reads is what is checked instead.
    """
    window = tkfacade.Window(title="iconed", icon=_png(), root=root)
    icon = window.icon
    assert icon is not None
    name = str(icon.photo_for(root._tk))
    del icon

    gc.collect()

    assert name in {str(each) for each in root.tk.call("image", "names")}


def _grips(window: tkfacade.Window) -> list[tk.Misc]:
    """Every sizegrip Tk holds under this window."""
    return [child for child in window._tk.winfo_children() if child.winfo_class() == "TSizegrip"]


def test_a_window_has_no_sizegrip_unless_asked(root: Root) -> None:
    """The default is off, and nothing is built."""
    window = tkfacade.Window(root=root)

    assert window.sizegrip is False
    assert _grips(window) == []


def test_asking_for_a_sizegrip_builds_one(root: Root) -> None:
    """Constructing with the flag puts a real grip under the window."""
    window = tkfacade.Window(root=root, sizegrip=True)

    assert window.sizegrip is True
    assert len(_grips(window)) == 1


def test_a_sizegrip_can_be_taken_away_and_put_back(root: Root) -> None:
    """The property is live both ways, and idempotent either way."""
    window = tkfacade.Window(root=root)

    window.sizegrip = True
    assert window.sizegrip is True and len(_grips(window)) == 1

    window.sizegrip = True  # already true: nothing built, nothing raised
    assert len(_grips(window)) == 1

    window.sizegrip = False
    assert window.sizegrip is False and _grips(window) == []

    window.sizegrip = False  # already false: nothing destroyed
    assert _grips(window) == []

    window.sizegrip = True
    assert len(_grips(window)) == 1


def test_toggling_the_sizegrip_does_not_pile_up_handlers(root: Root) -> None:
    """The lift handler is bound once with the window, not once per grip.

    Binding it alongside each grip looked tidier and leaked: ``add="+"``
    appends, so five creations left five handlers on one event.
    """
    window = tkfacade.Window(root=root)
    for _ in range(4):
        window.sizegrip = True
        window.sizegrip = False
    window.sizegrip = True

    assert window._tk.bind("<Map>").count("_raise_sizegrip") == 1


def test_the_sizegrip_sits_in_the_corner_and_follows_a_resize(root: Root) -> None:
    """It is placed against the bottom-right, so it tracks the window."""
    window = tkfacade.Window(root=root, width=400, height=300, sizegrip=True)
    window._tk.update()
    grip = _grips(window)[0]

    assert grip.winfo_x() + grip.winfo_width() == 400
    assert grip.winfo_y() + grip.winfo_height() == 300

    window.width = 520
    window.height = 380
    window._tk.update()

    assert grip.winfo_x() + grip.winfo_width() == 520
    assert grip.winfo_y() + grip.winfo_height() == 380


def test_the_sizegrip_stays_on_top_of_content_built_after_it(root: Root) -> None:
    """The regression guard: a younger sibling must not take the corner.

    Without the lift this fails — witnessed while designing it, a frame
    gridded after construction owned the grip's own pixel.
    """
    window = tkfacade.Window(root=root, width=400, height=300, sizegrip=True)
    content = tkfacade.Frame(window)
    content.grid(row=0, column=0, sticky="nsew")
    window.grid_rowconfigure(0, weight=1)
    window.grid_columnconfigure(0, weight=1)
    window._tk.update()

    grip = _grips(window)[0]
    spot_x = window._tk.winfo_rootx() + grip.winfo_x() + 5
    spot_y = window._tk.winfo_rooty() + grip.winfo_y() + 5

    assert str(window._tk.winfo_containing(spot_x, spot_y)) == str(grip)


def test_the_sizegrip_reaches_the_window_over_a_late_overlay(root: Root) -> None:
    """A widget placed over the corner long after still loses it."""
    window = tkfacade.Window(root=root, width=400, height=300, sizegrip=True)
    window._tk.update()
    grip = _grips(window)[0]

    latecomer = tkfacade.Frame(window, width=60, height=60)
    latecomer.place(relx=1.0, rely=1.0, anchor="se")
    window._tk.update()

    spot_x = window._tk.winfo_rootx() + grip.winfo_x() + 5
    spot_y = window._tk.winfo_rooty() + grip.winfo_y() + 5

    assert str(window._tk.winfo_containing(spot_x, spot_y)) == str(grip)


def test_a_window_subscriber_hears_the_grip_without_any_routing(root: Root) -> None:
    """No routing is written for the grip, and none is needed.

    Tk runs an event through the bindtags of the widget it happened in
    — the widget, its class, the toplevel, ``all`` — and the toplevel
    is this window. So a composite's routing problem never arises here.
    """
    window = tkfacade.Window(root=root, sizegrip=True)
    window._tk.update()
    grip = _grips(window)[0]

    seen: list[tkfacade.Event] = []
    window.bind(tkfacade.PointerEnter(), seen.append)
    grip.event_generate("<Enter>")

    assert len(seen) == 1
    assert seen[0].widget is window


def test_a_sizegrip_goes_with_the_window_it_belongs_to(root: Root) -> None:
    """Destroying the window takes the grip; nothing is left standing.

    A second window is kept alive on purpose: destroying the last one
    on a root cascades that root down, and the interpreter with it, so
    there would be nothing left to ask about the grip.
    """
    window = tkfacade.Window(root=root, sizegrip=True)
    tkfacade.Window(root=root)
    grip = _grips(window)[0]

    window.destroy()

    assert not grip.winfo_exists()
