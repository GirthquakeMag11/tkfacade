""":class:`~tkfacade.widget.Surface`: geometry requests and obstruction review.

A surface is two nested frames — the outer carries the size request,
the inner is the drawing area — plus an interpreter-wide review that
blanks the inner frame while anything obstructs it. The contracts here
are what a caller observes: the requested size arriving, the drawing
area mapping and unmapping as obstructions come and go. Obstructing
covers are built as raw ``tk`` widgets — handed the window through
:meth:`~tkfacade.widget.BaseWidget._as_master` — and placed over the surface, since
obstruction by widgets tkfacade does not manage is exactly what the review
exists to notice. Everything needs real geometry, so the suite rides
the ``window`` fixture under the ``gui`` marker.
"""

import gc
import tkinter as tk
import weakref

import pytest

import tkfacade
from conftest import Pump
from tkfacade.widget import BaseWidget, Surface
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def _covered(window: tkfacade.Window, surface: Surface) -> tk.Frame:
    """Place a full-window cover over ``surface`` and return it.

    Args:
        window (tkfacade.Window): The window holding the surface.
        surface (Surface): The surface being obstructed.

    Returns:
        The cover frame, placed above the surface.
    """
    cover = tk.Frame(BaseWidget._as_master(window), background="red")
    cover.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    return cover


def test_surface_draws_in_an_unweighted_cell(window: tkfacade.Window, pump: Pump) -> None:
    """A surface in a plain grid cell reaches its requested size and draws.

    The regression test for the ledger's old collapse entry: the requested size lives as minsizes on the outer frame's own grid, and with the drawing area blanked that grid once managed nothing — so the outer requested 1x1 and the review deadlocked, never restoring anywhere a weighted master cell didn't happen to stretch it. The unweighted cell is the arrangement that had never worked. The outer and inner frames are read directly because size and mappedness are the defect's own terms; no public accessor reports them.
    """
    surface = Surface(window, width=200, height=100)
    surface.grid(row=0, column=0)
    pump(window)

    assert (surface._tk.winfo_width(), surface._tk.winfo_height()) == (200, 100)
    assert surface._surface.winfo_ismapped()
    assert not surface.obstructed


def test_surface_added_to_a_live_window_draws(window: tkfacade.Window, pump: Pump) -> None:
    """A surface gridded after the window's first layout pass still draws.

    The same entry's second sub-case, which even a weighted cell could not rescue: gridding into an already-laid-out toplevel left the surface unmapped at 1x1 permanently, so identical code worked or failed depending on whether the window had been pumped yet. The leading pump is the whole point of the test.
    """
    pump(window)
    surface = Surface(window, width=200, height=100)
    surface.grid(row=0, column=0)
    pump(window)

    assert surface._surface.winfo_ismapped()
    assert not surface.obstructed


def test_cover_removal_restores_the_surface(window: tkfacade.Window, pump: Pump) -> None:
    """A placed cover blanks the surface; unplacing it restores it.

    The review's already-working path, pinned so the placeholder and <Destroy> changes can never regress it: obstruction is noticed via the global map/unmap binds, and clearing it by unmapping the cover restores the drawing area. Both directions assert the inner frame's real mapped state alongside the published flag, because blanking is the *effect* and the flag only the report. The reads land in locals because mypy narrows a repeated property expression and would call the second block unreachable.
    """
    surface = Surface(window, width=200, height=100)
    surface.grid(row=0, column=0)
    pump(window)

    cover = _covered(window, surface)
    pump(window)
    covered = surface.obstructed
    covered_mapped = bool(surface._surface.winfo_ismapped())

    cover.place_forget()
    pump(window)
    restored = surface.obstructed
    restored_mapped = bool(surface._surface.winfo_ismapped())

    assert (covered, covered_mapped) == (True, False)
    assert (restored, restored_mapped) == (False, True)


def test_cover_destruction_restores_the_surface(window: tkfacade.Window, pump: Pump) -> None:
    """Destroying an obstructing widget outright restores the surface.

    The regression test for the destroyed-sibling entry: a destroyed widget delivers no <Unmap>, so before the global <Destroy> bind the surface stayed blanked with nothing in front of it until something unrelated queued a review. Identical shape to the removal test above except for how the cover leaves — that one-line difference is the entry.
    """
    surface = Surface(window, width=200, height=100)
    surface.grid(row=0, column=0)
    pump(window)

    cover = _covered(window, surface)
    pump(window)
    covered = surface.obstructed

    cover.destroy()
    pump(window)
    restored = surface.obstructed

    assert (covered, restored) == (True, False)
    assert surface._surface.winfo_ismapped()


def test_size_request_survives_suppression(window: tkfacade.Window, pump: Pump) -> None:
    """``width``/``height`` round-trip and hold while the surface is blanked.

    width/height are documented as requests the master "may grant more — but never less" than; before the placeholder fix that claim failed exactly during suppression, when the request's own grid went empty. Reading the outer frame's real size *while obstructed* pins the repaired half of the claim; the round-trip pins the minsize store both properties read back from.
    """
    surface = Surface(window, width=200, height=100)
    surface.grid(row=0, column=0)
    pump(window)

    surface.width = 240
    surface.height = 120
    assert (surface.width, surface.height) == (240, 120)

    cover = _covered(window, surface)
    pump(window)
    covered = surface.obstructed
    suppressed_size = (surface._tk.winfo_width(), surface._tk.winfo_height())

    cover.destroy()
    pump(window)
    restored = surface.obstructed

    assert (covered, restored) == (True, False)
    assert suppressed_size == (240, 120)


def test_interpreter_binds_are_installed_once_however_many_surfaces_come_and_go(
    window: tkfacade.Window,
) -> None:
    """Repeated create-and-destroy cycles leave one set of global handlers.

    The review binds are interpreter-wide and installed by whichever surface is first, guarded by a set of interpreters already bound. That set used to be emptied when the last surface went, so the next surface installed a second set on top and every <Map>, <Unmap> and <Destroy> in the whole application dispatched one more Python callback per cycle. Nothing behaved wrongly — the reviews coalesce — so the symptom was a process getting steadily slower, which is why the count is asserted directly against Tk's own binding script rather than through any observable behaviour. Three cycles rather than two: one repeat could pass on an off-by-one that still grows.
    """

    def handler_lines() -> int:
        script = str(window.tk.call("bind", "all", "<Map>"))
        return len([line for line in script.split("\n") if line.strip()])

    for _ in range(3):
        surface = Surface(window)
        installed = handler_lines()
        surface._tk.destroy()

        assert installed == 1


def test_a_dead_interpreter_leaves_the_registries(window: tkfacade.Window) -> None:
    """Destroying a root evicts its interpreter from the class registries.

    The registry docstring's reason never to remove an entry — unbinding would take unrelated bindings with it — holds only for a live interpreter, and the set grew monotonically: every root an application cycled through pinned its dead TkappType and the whole Tcl interpreter state behind it for process life, invisible in any single-root run and masked in this suite by conftest clearing the set by hand. The membership is asserted before the destroy because a registry that never enrolled the interpreter would pass the eviction half vacuously; destroying the window rather than the root drives the eviction through the same last-window cascade a real application takes.
    """
    other = Root()
    held = tkfacade.Window(root=other)
    try:
        Surface(held)
        interpreter = held._tk.tk
        assert interpreter in Surface._review_bound_to
    finally:
        held.destroy()

    assert interpreter not in Surface._review_bound_to
    assert interpreter not in Surface._review_job


def test_a_scheduled_review_stays_on_its_own_interpreter(
    window: tkfacade.Window, pump: Pump
) -> None:
    """One interpreter's idle review never probes another interpreter's surfaces.

    The pending-review token was scoped per interpreter — "a pending review on one root never suppresses another's" — but the job it queued ran review_all and swept the global registry, so interpreter A's idle callback probed B's widgets at a moment A's event stream chose, before B's geometry pass had settled, running the blank/restore hooks on wrong interim answers. The recording subclass is the only way to see which surfaces a review touched, since a correct review leaves identical observable state; construction-time reviews are drained and cleared first so the assertion isolates the one scheduled pass, and only A's interpreter is pumped because B's never running is exactly the point.
    """
    reviewed: list[str] = []

    class Recording(Surface):
        __slots__ = ("label",)

        def __init__(self, parent: tkfacade.Window, label: str) -> None:
            self.label: str = label
            super().__init__(parent)

        def _surface_review(self) -> None:
            reviewed.append(self.label)
            super()._surface_review()

    Recording(window, "A")
    other = Root()
    held = tkfacade.Window(root=other)
    try:
        Recording(held, "B")
        pump(window)
        pump(held)
        reviewed.clear()

        Surface._schedule_on(window._tk.tk)
        pump(window)

        assert "A" in reviewed
        assert "B" not in reviewed
    finally:
        held.destroy()


def test_a_moving_cover_is_noticed_both_ways(window: tkfacade.Window, pump: Pump) -> None:
    """A mapped widget sliding over the surface blanks it; sliding away restores it.

    Reviews were scheduled from map, unmap, and destroy events only, and a mapped widget moving fires none of them — just its own <Configure>, which nothing watched — so the answer went stale in both directions: the backend kept drawing under a cover dragged onto it and stayed blanked after the cover slid away, until some unrelated event ran a review. The cover is placed *beside* the surface first, already mapped, precisely so the only events the moves produce are the <Configure>s the old binds missed; every other cover test places fresh or destroys, which fires the events that always worked.
    """
    surface = Surface(window, width=200, height=100)
    surface.grid(row=0, column=0)
    pump(window)
    beside = tk.Frame(BaseWidget._as_master(window), background="red", width=220, height=120)
    beside.place(x=400, y=0)
    pump(window)
    clear_before = surface.obstructed

    beside.place(x=0, y=0)
    pump(window)
    covered = surface.obstructed

    beside.place(x=400, y=0)
    pump(window)
    clear_after = surface.obstructed

    assert clear_before is False
    assert covered is True
    assert clear_after is False


def test_a_destroyed_surface_becomes_collectable(window: tkfacade.Window, pump: Pump) -> None:
    """After destroy and a collection, nothing keeps the surface or its variable alive.

    In the variable era the obstruction trace registered a Tcl command on the interpreter wrapping a bound method — a loop rooted in C state that Python's GC cannot traverse — and until teardown removed it, every create/destroy cycle permanently pinned the surface, its BooleanVar, both frame wrappers, and everything a subclass hangs off the class (a VideoDisplay's whole mpv graph included), for the interpreter's whole life. The observable conversion removed that anchor by construction: the watch is pure Python in a cycle the GC traverses, and its cancel is hygiene rather than leak repair. The weakrefs stay as the proof the whole graph still releases, because every behavioral face looks correct either way — registry emptied, reviews stopped — which is exactly how three sweeps missed the original.
    """
    surface = Surface(window, width=200, height=100)
    surface.grid(row=0, column=0)
    pump(window)
    # the Surface itself is slotted without __weakref__, so the graph's
    # release is observed through two members that do take weakrefs:
    # the inner drawing frame and the outer frame wrapper
    dead_inner = weakref.ref(surface._surface)
    dead_frame = weakref.ref(surface._tk)

    surface._tk.destroy()
    pump(window)
    del surface
    gc.collect()

    assert dead_inner() is None
    assert dead_frame() is None
