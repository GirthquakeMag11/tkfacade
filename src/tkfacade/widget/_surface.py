"""A self-suppressing drawing area for backends that composite above Tk."""

import tkinter as tk
from contextlib import suppress
from typing import ClassVar

from .._subscription import Subscription
from .._utils import intersects, screen_rect
from ..observable import ObservableBool
from ._base import BaseWidget
from ._widget import Widget


class Surface(Widget):
    """A :class:`Widget` whose drawing area is suppressed while obstructed.

    Two nested frames: the outer holds the size request and is what a
    caller lays out, the inner is the drawing area. Whenever Tk reports
    the outer frame unviewable, not yet sized, or occluded by a
    later-stacked sibling, the inner frame is taken off screen, and put
    back when the obstruction clears. Surfaces are reviewed together at
    idle, once per event-loop pass.
    """

    __slots__ = (
        "_key",
        "_obstructed",
        "_obstructed_state",
        "_obstructed_watch",
        "_placeholder",
        "_surface",
        "_torn_down",
    )

    _surfaces: ClassVar[dict[tuple[object, str], Surface]] = {}
    """Registry of live surfaces, keyed by (interpreter, outer-frame Tk path).

    The interpreter is part of the key because Tk path names are only
    unique within one: two roots each hand their first surface
    ``.!basewindow.!frame``.
    """
    _review_job: ClassVar[dict[object, tuple[tk.Misc, str]]] = {}
    """The pending coalesced review per interpreter: (host widget, ``after`` token)."""
    _review_bound_to: ClassVar[set[object]] = set()
    """The Tk interpreters that already have the global map/unmap binds.

    An interpreter stays here once bound, even after its last surface dies.
    The binds are not removed with it: they were installed with ``add="+"``
    and ``unbind_all`` takes a sequence rather than a handler, so removing
    them would take every *other* ``<Map>``, ``<Unmap>``, ``<Configure>``
    and ``<Destroy>`` binding in the application with them. Leaving them costs one no-op
    scheduling call per event on an interpreter that has no surfaces, and
    keeping the entry is what stops the next surface installing a second
    set on top.

    A *destroyed* interpreter is different: its binds died with it, so
    its entry serves nothing and would pin the dead ``TkappType`` — and
    the Tcl state behind it — for process life, one per root an
    application ever cycles through. The interpreter-wide ``<Destroy>``
    handler evicts the entry when the root itself goes.
    """

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        background: str = "black",
        height: int = 540,
        width: int = 960,
    ) -> None:
        """Build the frame pair and register for obstruction review.

        The first surface on an interpreter also binds global
        ``<Map>``/``<Unmap>``/``<Configure>``/``<Destroy>`` handlers,
        so obstruction by unrelated widgets — arriving, moving,
        resizing, or clearing by destruction — is noticed too.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                surface is created inside.
            background (str): Background color of the drawing area.
                Defaults to ``"black"``.
            height (int): Requested height in pixels. Defaults to
                ``540``.
            width (int): Requested width in pixels. Defaults to
                ``960``.
        """
        self._torn_down: bool = False
        self._tk: tk.Frame = tk.Frame(self._as_master(parent), highlightthickness=0)
        self._placeholder: tk.Frame = tk.Frame(self._tk, width=1, height=1, highlightthickness=0)
        self._placeholder.grid(row=0, column=0)
        self._surface: tk.Frame = tk.Frame(self._tk, background=background, highlightthickness=0)
        self._surface.grid(row=0, column=0, sticky="nsew")
        self._surface.grid_remove()
        self._tk.grid_rowconfigure(0, weight=1, minsize=height)
        self._tk.grid_columnconfigure(0, weight=1, minsize=width)
        self._obstructed_state: bool = True
        self._obstructed: ObservableBool = ObservableBool(True)
        self._obstructed_watch: Subscription = self._obstructed.watch(self._reassert_obstructed)
        self._key: tuple[object, str] = (self._tk.tk, str(self._tk))
        self._route_events(self._surface, self._placeholder)
        self._tk.bind("<Map>", self._schedule, add="+")
        self._tk.bind("<Unmap>", self._schedule, add="+")
        self._tk.bind("<Configure>", self._schedule, add="+")
        self._surface.bind("<Destroy>", self._on_destroy, add="+")
        self._tk.bind("<Destroy>", self._on_destroy, add="+")
        if self._tk.tk not in Surface._review_bound_to:
            interpreter = self._tk.tk

            def _review_interpreter(_event: tk.Event[tk.Misc] | None = None) -> None:
                """Queue a review of ``interpreter``, whatever mapped or unmapped."""
                Surface._schedule_on(interpreter)

            def _forget_interpreter(event: tk.Event[tk.Misc]) -> None:
                """Evict the interpreter's entries once its root is destroyed.

                By path: the root is always ``"."``, and mid-teardown the
                event may carry the bare path where the widget object can
                no longer be resolved.
                """
                if str(event.widget) == ".":
                    Surface._review_bound_to.discard(interpreter)
                    Surface._review_job.pop(interpreter, None)

            self._tk.bind_all("<Map>", _review_interpreter, add="+")
            self._tk.bind_all("<Unmap>", _review_interpreter, add="+")
            self._tk.bind_all("<Destroy>", _review_interpreter, add="+")
            self._tk.bind_all("<Configure>", _review_interpreter, add="+")
            self._tk.bind_all("<Destroy>", _forget_interpreter, add="+")
            Surface._review_bound_to.add(interpreter)
        Surface._surfaces[self._key] = self
        self._schedule()
        super().__init__()

    def _reassert_obstructed(self, _value: bool, /) -> None:
        """Put the true state back whenever anything else writes the observable.

        The observable is published to be watched, not to drive the
        surface with; the review holds the real answer. Writing it back
        settles once more, finds the two agreeing, and stops.
        """
        if self._obstructed.value != self._obstructed_state:
            self._obstructed.value = self._obstructed_state

    def _occluded(self) -> bool:
        """Whether Tk reports any mapped widget overlapping this one.

        Climbs from the outer frame to the toplevel, checking at each
        level only the siblings stacked *after* the branch being
        climbed: those are the ones Tk draws on top.

        Returns:
            True if anything overlaps the surface's area.
        """
        rect = screen_rect(self._tk)
        node: tk.Misc = self._tk
        while not isinstance(node, tk.Wm):
            path = node.winfo_parent()
            if not path:
                return False
            master = node.nametowidget(path)
            above = False
            for sibling in master.winfo_children():
                if sibling is node:
                    above = True
                elif (
                    above
                    and not isinstance(sibling, tk.Wm)
                    and sibling.winfo_ismapped()
                    and intersects(rect, screen_rect(sibling))
                ):
                    return True
            node = master
        return False

    def _on_destroy(self, event: tk.Event[tk.Misc]) -> None:
        """Tear down once, on whichever of the two frames dies first.

        The surface leaves the registry *before* the teardown hook, so
        nothing can schedule a review of a dying widget.

        Args:
            event (tk.Event[tk.Misc]): The ``<Destroy>`` that arrived.
                Ignored unless it names one of this surface's own
                frames, since the binding also sees children.
        """
        if self._torn_down:
            return
        if event.widget is not self._surface and event.widget is not self._tk:
            return
        self._torn_down = True
        Surface._forget(self._key)
        self._obstructed_watch.cancel()
        self._surface_teardown()

    def _surface_blank(self) -> None:
        """Take the surface off the screen; subclasses call ``super()`` first."""
        self._surface.grid_remove()

    def _surface_restore(self) -> None:
        """Put the surface back; subclasses call ``super()`` first.

        Bare ``grid()`` restores the options :meth:`_surface_blank`
        left remembered.
        """
        self._surface.grid()

    def _surface_teardown(self) -> None:
        """Release the surface before Tk frees the window behind it.

        A no-op here — by now the surface is out of the registry and
        no review can reach it. Subclasses call ``super()`` first and
        then terminate whatever was drawing: reversed, the backend
        writes into a freed window and the process segfaults rather
        than raising.
        """

    def _surface_review(self) -> None:
        """Re-evaluate whether the surface may draw, and act on it.

        Idempotent, and so safe to run from an event handler: a review
        finding the state already correct stops. The new state is
        recorded *before* the hooks run, so a hook reaching back into a
        review finds the answer settled rather than recursing. The
        comparison is against that recorded state rather than the
        published variable, so nothing outside can talk the review out
        of running its hooks.
        """
        if self._torn_down or not self._tk.winfo_exists():
            return
        obstructed = not (
            self._tk.winfo_viewable()
            # 1x1 is Tk's placeholder for "geometry has not been computed"
            and self._tk.winfo_width() > 1
            and self._tk.winfo_height() > 1
            and not self._occluded()
        )
        if obstructed == self._obstructed_state:
            return
        self._obstructed_state = obstructed
        self._obstructed.value = obstructed
        if obstructed:
            self._surface_blank()
        else:
            self._surface_restore()

    def _schedule(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Queue one review of this surface's interpreter, for the end of the pass.

        Doubles as the callback for every binding that can change what
        covers what, hence the discarded event.

        Args:
            _event (tk.Event[tk.Misc] | None): The event that prompted
                this, if any. Unused; a review covers the whole
                interpreter.
        """
        Surface._schedule_on(self._tk.tk)

    @property
    def obstructed(self) -> bool:
        """Whether the surface is currently suppressed rather than drawing."""
        return self._obstructed_state

    @property
    def width(self) -> int:
        """The width the surface asks its master for, in pixels.

        A request, not a size: the master may grant more — a weighted
        cell stretches — but never less, which keeps a suppressed surface
        from collapsing to nothing and leaving the review no geometry
        to judge it by.
        """
        return int(self._tk.grid_columnconfigure(0)["minsize"])

    @width.setter
    def width(self, value: int) -> None:
        self._tk.grid_columnconfigure(0, minsize=value)

    @property
    def height(self) -> int:
        """The height the surface asks its master for, in pixels.

        A request, not a size; see :attr:`width`.
        """
        return int(self._tk.grid_rowconfigure(0)["minsize"])

    @height.setter
    def height(self, value: int) -> None:
        self._tk.grid_rowconfigure(0, minsize=value)

    @classmethod
    def _forget(cls, key: tuple[object, str], /) -> None:
        """Drop one registry entry and whatever it was the last of.

        A queued review whose host is no longer a registered surface
        can never run — ``after`` jobs die silently with their widget,
        and with their interpreter — so it is cancelled, dropped, and
        re-queued on a surviving surface. A token left in place would
        block every future review on that interpreter. The global
        map/unmap binds outlive the interpreter's last surface — see
        :attr:`_review_bound_to` for why they must.

        Args:
            key (tuple[object, str]): The entry's registry key.
        """
        if cls._surfaces.pop(key, None) is None:
            return
        interpreter = key[0]
        remaining = [
            surface for (interp, _path), surface in cls._surfaces.items() if interp is interpreter
        ]
        job = cls._review_job.get(interpreter)
        if job is not None and not any(job[0] is surface._tk for surface in remaining):
            with suppress(tk.TclError):
                job[0].after_cancel(job[1])
            del cls._review_job[interpreter]
            if remaining:
                cls._schedule_on(interpreter)

    @classmethod
    def review_all(cls) -> None:
        """Re-evaluate every live surface now, rather than at idle.

        Surfaces review themselves as Tk reports widgets mapping,
        unmapping, and resizing, so this is only needed after a
        stacking change Tk announces no other way — a bare
        :meth:`tkinter.Misc.lift` on a raw widget — or to make the
        result observable inline.
        """
        for key, surface in tuple(cls._surfaces.items()):
            alive = False
            with suppress(tk.TclError):
                alive = bool(surface._tk.winfo_exists())
            if alive:
                surface._surface_review()
            else:
                cls._forget(key)

    @classmethod
    def _review_on(cls, interpreter: object, /) -> None:
        """Review (and garbage-collect) one interpreter's surfaces only.

        The scoped half of :meth:`review_all`, and what a queued review
        runs: an idle callback on one interpreter must not probe
        another's widgets — the other's geometry pass has not
        necessarily settled at a moment this one's event stream chose,
        and under one root per thread the probe would be a cross-thread
        Tcl call.

        Args:
            interpreter (object): The Tcl interpreter whose surfaces
                are reviewed.
        """
        for key, surface in tuple(cls._surfaces.items()):
            if key[0] is not interpreter:
                continue
            alive = False
            with suppress(tk.TclError):
                alive = bool(surface._tk.winfo_exists())
            if alive:
                surface._surface_review()
            else:
                cls._forget(key)

    @classmethod
    def _schedule_on(cls, interpreter: object, /) -> None:
        """Queue one review of ``interpreter``'s surfaces at idle.

        Coalescing is the point: a single page switch fires
        ``<Unmap>`` and ``<Configure>`` on a dozen widgets, and one
        review at idle answers for all of them — after Tk has
        recomputed geometry, the only time the answer is worth
        reading. One token per interpreter, so a pending review on one
        root never suppresses another's.

        Args:
            interpreter (object): The Tcl interpreter whose surfaces
                are to be reviewed. A no-op when none are registered
                on it.
        """
        if interpreter in cls._review_job:
            return
        host = next(
            (
                surface._tk
                for (interp, _path), surface in cls._surfaces.items()
                if interp is interpreter
            ),
            None,
        )
        if host is None:
            return

        def _run_review() -> None:
            cls._review_job.pop(interpreter, None)
            cls._review_on(interpreter)

        with suppress(tk.TclError):
            cls._review_job[interpreter] = (host, host.after_idle(_run_review))
