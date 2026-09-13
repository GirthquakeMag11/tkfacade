"""The wrapper root: one slot, a wrapper registry, mainloop scheduling, and the master contract.

``Misc`` and ``Widget`` are imported by name rather than reached through a
``tk`` module alias: :class:`BaseWidget` defines a ``tk`` property — tkinter
reads it off a master — which would shadow that alias for every annotation
written after it in the class body.
"""

import asyncio
import concurrent.futures
from collections.abc import Callable, Coroutine, Mapping
from concurrent.futures import Future
from contextlib import suppress
from inspect import iscoroutinefunction
from tkinter import Event as TkEvent
from tkinter import Misc, TclError, Widget
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .._core import launch, resolve_core
from .._report import report
from .._subscription import Subscription
from ..events import EMPTY_PAYLOAD, Event, EventSpec, Virtual

if TYPE_CHECKING:
    import _tkinter


def _int_or_none(value: object) -> int | None:
    """Read one of tkinter's maybe-int fields, whose absent value is ``'??'``."""
    return value if isinstance(value, int) else None


def _snapshot(
    spec: EventSpec,
    widget: BaseWidget | None,
    raw: TkEvent[Misc],
    payload: Mapping[str, object],
) -> Event:
    """Translate tkinter's raw event into the immutable value delivered.

    The one place a raw tkinter event and an :class:`~tkfacade.events.Event`
    meet: the constructor itself takes only plain values, so the
    tkinter-flavored reads — the ``'??'`` stand-ins — are normalized
    here and nowhere else. Position is taken from the packet only for
    the occurrence kinds that happen at the pointer: Tk stuffs the
    pointer's idle position into keyboard packets too, and that is
    device state, not a fact of the keystroke.
    """
    at_pointer = spec.at_pointer
    return Event(
        spec=spec,
        widget=widget,
        payload=payload,
        widget_x=_int_or_none(getattr(raw, "x", None)) if at_pointer else None,
        widget_y=_int_or_none(getattr(raw, "y", None)) if at_pointer else None,
        screen_x=_int_or_none(getattr(raw, "x_root", None)) if at_pointer else None,
        screen_y=_int_or_none(getattr(raw, "y_root", None)) if at_pointer else None,
        time=_int_or_none(getattr(raw, "time", None)),
    )


class _EventSub:
    """One registration on a specification: the subscriber, its role, its standing."""

    __slots__ = ("active", "consume", "is_async", "subscriber", "tasks")

    def __init__(self, subscriber: Callable[[Event], object], consume: bool) -> None:
        self.subscriber: Callable[[Event], object] = subscriber
        self.consume: bool = consume
        self.active: bool = True
        self.is_async: bool = iscoroutinefunction(subscriber)
        self.tasks: set[concurrent.futures.Future[Any]] = set()


class _SpecBinding:
    """One (widget, specification) binding: the Tk funcid and its subscribers."""

    __slots__ = ("funcid", "spec", "subs")

    def __init__(self, spec: EventSpec, funcid: str) -> None:
        self.spec: EventSpec = spec
        self.funcid: str = funcid
        self.subs: list[_EventSub] = []


class BaseWidget:
    """Duck-type a wrapper as a master acceptable to tkinter.

    ``tkinter.BaseWidget._setup`` reads ``tk``, ``_w``, ``children``,
    and ``_last_child_ids`` from its master (and assigns the last,
    hence the setter), so a wrapper proxying them to the wrapped
    widget in ``_tk`` passes wherever tkinter wants a master. Beyond
    those, ``master`` keeps ``Misc._root()``'s walk up the master
    chain from dead-ending at a wrapper, and ``__str__`` is the
    widget path _tkinter falls back to when a wrapper lands in a Tcl
    argument list.
    """

    if TYPE_CHECKING:
        _tk: Misc

    __slots__ = ("_emitting", "_event_bindings", "_tk")

    _wrappers: ClassVar[dict[tuple[object, str], BaseWidget]] = {}
    """Registry of live wrappers, keyed by (interpreter, Tk path).

    The interpreter is part of the key because a Tk path names one
    widget only within one: every root calls its first window
    ``.!basewindow``. An entry appears once the class that owns ``_tk``
    has built it — a subclass constructing on top of that, as
    :class:`~tkfacade.media.VideoDisplay` does, is registered before its own
    work is finished — and goes when Tk destroys the widget under it,
    so what the registry holds is the wrappers whose widgets are alive.

    Every widget evicts itself, the root included, so a teardown Tk
    announces empties that interpreter out entirely. One teardown does
    not announce itself: an interpreter dropped without ``destroy()``
    delivers no ``<Destroy>`` at all, and its entries stay. They are
    unreachable rather than wrong — the interpreter is part of the key,
    so no live lookup can land on one — and the suite sweeps them
    between tests.

    The reference is strong, on the same footing as the one
    :meth:`~tkfacade.window.Root.add_child` holds: it keeps a wrapper — and
    whatever that wrapper holds, such as its images — alive for as long
    as its widget is, whether or not the caller kept one of their own.
    """

    def __init__(self) -> None:
        """Enter the wrapper in the registry, and leave it when its widget dies.

        Subclasses assign ``_tk`` first and call this last, after the
        work that can still fail: the registry hands out live wrappers,
        and one whose construction went on to raise was never live.

        Raises:
            TclError: If the widget cannot take the ``<Destroy>``
                binding. The watch is bound before the entry is
                written, so such a widget is left unregistered rather
                than registered with no way out.
        """
        self._event_bindings: dict[str, _SpecBinding] = {}
        self._emitting: list[tuple[str, Mapping[str, object]]] = []
        widget = self._tk
        key: tuple[object, str] = (widget.tk, str(widget))

        def forget(event: TkEvent[Misc]) -> None:
            if str(event.widget) != key[1]:
                return
            held = BaseWidget._wrappers.get(key)
            if held is not None and held._tk is widget:
                del BaseWidget._wrappers[key]

        widget.bind("<Destroy>", forget, add="+")
        BaseWidget._wrappers[key] = self

    def __str__(self) -> str:
        """Return the widget path, so a wrapper converts as a Tcl argument."""
        return str(self._tk)

    def _route_events(self, *parts: Misc) -> None:
        """Make each part's events reach this wrapper's subscribers.

        A wrapper whose ``_tk`` is a frame holding the working widget
        would otherwise hear nothing a user does inside it: Tk sends an
        event to the widget it happened in and then runs that widget's
        bindtags — the widget, its class, the toplevel, ``all`` — which
        never contain the parent. Putting this wrapper's own path into
        each part's chain is Tk's own way of saying the events belong
        here too, and leaves :meth:`bind`, :meth:`unbind` and the
        dispatch untouched.

        The path goes in *second*, after the part's own tag. Witnessed
        (`experiments/composite_events/`): either position delivers,
        and either carries a consumer's ``break`` through to the part's
        class binding, so second place is chosen for costing nothing —
        a binding already on a part keeps running before this one.

        Each part's own descendants are routed with it, so a group
        of parts built into one container takes a single call. The
        walk reads the tree as it stands, so a part built later needs
        its own call — :class:`~tkfacade.ImageDisplay` makes one for
        the view it puts inside the surface.

        Called by a composite during construction, once its parts
        exist. Parts that are themselves wrappers are not passed: they
        hear their own events, and a container hears them the way a
        window does, by being in the chain already.

        Args:
            parts (Misc): The widgets this wrapper is built from.
        """
        pending = list(parts)
        while pending:
            part = pending.pop()
            pending.extend(part.winfo_children())
            tags = part.bindtags()
            if str(self._tk) in tags:
                continue
            part.bindtags((tags[0], str(self._tk), *tags[1:]))

    def _wrapper_for(self, widget: object, /) -> BaseWidget | None:
        """The wrapper ``widget`` belongs to, walking out until one answers.

        An event names the widget it happened in, and the parts a
        composite is built from are not wrappers — so a lookup on the
        event's own widget misses, and the walk continues to its
        master. A window binding still resolves a button inside it to
        the button, the innermost wrapper answering first.

        Returns:
            The wrapper, or None where nothing on the way out is one.
        """
        current: object | None = widget
        while current is not None:
            try:
                return self.nametowrapper(current)  # type: ignore[arg-type]
            except KeyError, TclError:
                current = getattr(current, "master", None)
        return None

    def _dispatch_spec(self, seq: str, raw: TkEvent[Misc]) -> str | None:
        """Fan one delivered event out to its specification's subscribers.

        Consumers run first, then observers, each in registration
        order, every one of them unconditionally — no subscriber can
        silence a sibling. Any consumer completing is the verdict,
        answered to Tk as "break" so only the default action below is
        suppressed. A raising subscriber is reported through the
        interpreter's error seam and counts as not completing.
        """
        binding = self._event_bindings.get(seq)
        if binding is None:
            return None
        payload: Mapping[str, object] = EMPTY_PAYLOAD
        if self._emitting and self._emitting[-1][0] == seq:
            payload = self._emitting.pop()[1]
        wrapper = self._wrapper_for(getattr(raw, "widget", self._tk))
        event = _snapshot(binding.spec, wrapper, raw, payload)
        consumed = False
        for consumers_turn in (True, False):
            for entry in list(binding.subs):
                if not entry.active or entry.consume is not consumers_turn:
                    continue
                if entry.is_async:
                    self._launch_coroutine(entry, event, seq)
                    continue
                try:
                    entry.subscriber(event)
                except Exception as exc:
                    report(self._tk, exc, f"a subscriber of {seq} on {self!r}")
                else:
                    consumed = consumed or consumers_turn
        return "break" if consumed else None

    def _launch_coroutine(self, entry: _EventSub, event: Event, seq: str) -> None:
        """Schedule an async observer on the root's core, fire-and-forget.

        The raise, if one lands, is reported through the same seam as a
        sync subscriber's; cancellation stays silent lifecycle. With no
        core to resolve — the root already tearing down — the miss is
        reported rather than swallowed.
        """
        core = resolve_core(self._tk.tk)
        context = f"a subscriber of {seq} on {self!r}"
        if core is None:
            report(self._tk, RuntimeError(f"no core to run {context}"), context)
            return
        # cast: is_async pinned iscoroutinefunction at bind time
        coro = cast(Coroutine[Any, Any, object], entry.subscriber(event))
        launch(core, coro, entry.tasks, lambda exc: report(self._tk, exc, context))

    @property
    def master(self) -> Misc | None:
        """The underlying Tk widget's master, or None at the root.

        This is the master *protocol* member ``Misc._root()`` walks, so
        it keeps answering up the real Tk chain rather than a wrapper.
        The facade's own word for the same direction is :attr:`parent`,
        which answers the nearest wrapper above.
        """
        return self._tk.master

    @property
    def parent(self) -> BaseWidget | None:
        """The nearest wrapper above this one, or None when there is none.

        Walks the underlying master chain and answers the first widget
        a wrapper was built for — for an ordinary widget, the wrapper
        the constructor's ``parent`` named. A widget no wrapper built
        is stepped over rather than answered, per the traversal rule
        (:func:`~tkfacade.widget._widget.wrappers_among`): a raw frame a
        caller nested wrappers inside does not hide their ancestry,
        and a chain that tops out unwrapped answers None.
        """
        widget = self._tk.master
        while widget is not None:
            wrapper = BaseWidget._wrappers.get((widget.tk, str(widget)))
            if wrapper is not None:
                return wrapper
            widget = widget.master
        return None

    @property
    def _tk_cls(self) -> str:
        """The underlying Tk widget's class name, as Tk reports it."""
        return self._tk.winfo_class()

    @property
    def children(self) -> dict[str, Widget]:
        """The underlying Tk widget's children, keyed by name.

        This is the live dict of the master *protocol* —
        ``tkinter.BaseWidget`` construction writes each new child into
        the very object this answers — so it can be neither a copy nor
        a wrapper view. The facade's own traversal downward is the
        geometry walk:
        :meth:`~tkfacade.widget.GridContainerWidget.grid_slaves` and its
        pack and place twins answer wrappers.
        """
        return self._tk.children

    @property
    def _w(self) -> str:
        """The underlying Tk widget's Tcl path name."""
        return self._tk._w  # type: ignore[attr-defined, no-any-return]

    @property
    def _last_child_ids(self) -> dict[str, int] | None:
        """Tkinter's per-type counters for naming new children."""
        return self._tk._last_child_ids  # type: ignore[attr-defined, no-any-return]

    @_last_child_ids.setter
    def _last_child_ids(self, value: dict[str, int] | None) -> None:
        self._tk._last_child_ids = value  # type: ignore[attr-defined]

    @property
    def tk(self) -> _tkinter.TkappType:
        """The Tcl interpreter behind the underlying Tk widget."""
        return self._tk.tk

    def destroy(self) -> None:
        """Destroy the wrapped widget, and everything mastered by it.

        The plain case rather than the whole story:
        :meth:`~tkfacade.Window.destroy` and
        :meth:`~tkfacade.window.Root.destroy` override this with the
        cascade and idempotence a toplevel needs, so a wrapper reached
        through one of those types does more than this. Nothing here
        unregisters the wrapper: :meth:`__init__`'s ``<Destroy>``
        binding does that, and does it for a widget destroyed by any
        route, this one included.
        """
        self._tk.destroy()

    def winfo_ismapped(self) -> bool:
        """Return whether Tk currently has the widget on screen.

        Delegates to :meth:`tkinter.Misc.winfo_ismapped`. False covers
        both a widget no geometry manager holds and one held by a
        manager that has taken it off screen, which is what
        :meth:`~tkfacade.AbstractMultiFrame.show` leaves every page but
        one in.
        """
        return bool(self._tk.winfo_ismapped())

    def bind(
        self,
        spec: EventSpec,
        subscriber: Callable[[Event], object],
        /,
        *,
        consume: bool = False,
    ) -> Subscription:
        """Register ``subscriber`` for ``spec``'s events on this widget.

        The registration declares its role. An *observer* — the default —
        witnesses the event and holds authority over nothing; its return
        is ignored. A *consumer* (``consume=True``) suppresses Tk's
        default action for the event by the fact of running to
        completion: no sentinel, no protocol — completion is the
        verdict, and it governs only the default
        action, never sibling subscribers, which all run regardless. A
        raise inside either role is routed to the callback error hook
        and, for a consumer, means it did not complete: the default
        proceeds, so a buggy consumer degrades to Tk's own behavior
        rather than eating input.

        On a window, the binding hears the window's whole bindtag —
        events on descendant widgets included, with
        :attr:`Event.widget <tkfacade.events.Event.widget>` naming the
        wrapper they landed on. Distinct specifications compete at Tk's
        level: when several match one event, the most specific fires
        alone (`hazards/tkinter.md`, *Bindings*).

        Args:
            spec (EventSpec): The occurrences to subscribe to.
            subscriber (Callable[[Event], object]): Called with each
                delivered :class:`~tkfacade.events.Event`; the return
                value is ignored in both roles.
            consume (bool): Whether completion suppresses Tk's default
                action. Defaults to False — an observer.

        Returns:
            The registration's :class:`~tkfacade.Subscription`; the
            widget's Tk binding for ``spec`` is removed when the last
            subscription on it is cancelled, and cancelling also
            cancels the subscription's coroutine runs still in flight.

        Raises:
            TypeError: If ``subscriber`` is a coroutine function
                registered as a consumer — refused permanently, since
                consumption is completion and a coroutine has not
                completed when the verdict is due. As an observer a
                coroutine function is accepted: each delivery schedules
                it on the root's async core, fire-and-forget — it works
                on the event's values and crosses back through
                observables or :meth:`async_submit`, never by touching a
                widget directly.
        """
        if iscoroutinefunction(subscriber) and consume:
            raise TypeError(
                "a coroutine cannot consume: consumption is completion, and "
                "a coroutine has not completed when the verdict is due; "
                "consumers are synchronous by design"
            )
        seq = spec.sequence
        binding = self._event_bindings.get(seq)
        if binding is None:

            def deliver(raw: TkEvent[Misc], _seq: str = seq) -> str | None:
                return self._dispatch_spec(_seq, raw)

            binding = _SpecBinding(spec, self._tk.bind(seq, deliver, add="+"))
            self._event_bindings[seq] = binding
        entry = _EventSub(subscriber, consume)
        binding.subs.append(entry)
        bound = binding

        def cancel() -> None:
            entry.active = False
            for task in tuple(entry.tasks):
                task.cancel()
            with suppress(ValueError):
                bound.subs.remove(entry)
            if not bound.subs and self._event_bindings.get(seq) is bound:
                del self._event_bindings[seq]
                with suppress(TclError):
                    self._tk.unbind(seq, bound.funcid)

        return Subscription(cancel)

    def emit(self, spec: EventSpec, /, payload: Mapping[str, object] | None = None) -> None:
        """Fire ``spec`` on this widget, as if Tk had delivered it.

        Delivery is synchronous for synchronous subscribers: every
        plain-callable subscriber of the specification has run by the
        time this returns, and every coroutine subscriber has been
        scheduled on the root's core, its body following off the
        mainloop. The payload is copied and
        frozen at the call, and subscribers receive that snapshot as
        :attr:`Event.payload <tkfacade.events.Event.payload>` — later
        changes to the caller's mapping are invisible, though the
        values themselves are whatever was passed. Only a
        :class:`~tkfacade.events.Virtual` specification may carry one,
        since physical occurrences are Tk's to describe. Tk drops a
        generated event silently until the widget's X window exists
        (`hazards/tkinter.md`, *Bindings*); ttk-backed wrappers create theirs
        at construction under a realized parent, so in practice an
        emit delivers once the window it sits in has been through one
        update.

        A destroyed widget emits nothing: the call returns without
        delivering — widget death ends deliveries. The bindings a
        subscription delivers through died with the widget's window, so
        there is no route left to deliver on; the case arises
        legitimately whenever a command destroys its own widget, a
        dialog button completing the dialog being the standing shape.

        Args:
            spec (EventSpec): The specification to fire.
            payload (Mapping[str, object] | None): Data for the
                event's subscribers, copied and frozen shallowly.
                Defaults to None, an event that carries none.

        Raises:
            TypeError: If a payload rides anything but a ``Virtual``
                specification.
        """
        if payload is not None and not isinstance(spec, Virtual):
            raise TypeError("only virtual events carry a payload")
        try:
            alive = bool(self._tk.winfo_exists())
        except TclError, RuntimeError:
            alive = False
        if not alive:
            return
        if not payload:
            self._tk.event_generate(spec.sequence)
            return
        entry = (spec.sequence, MappingProxyType(dict(payload)))
        self._emitting.append(entry)
        try:
            self._tk.event_generate(spec.sequence)
        finally:
            if self._emitting and self._emitting[-1] is entry:
                self._emitting.pop()

    def submit[T, **P](
        self,
        job: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Future[T]:
        """Schedule ``job`` to run on the Tk mainloop thread.

        Nothing executes until the mainloop processes the event on its
        next pass. Safe to call from another thread only while the
        mainloop is running; outside that window a foreign thread's
        call raises rather than queueing silently.

        The future carries the job's result or exception once it runs,
        a ``BaseException`` like ``KeyboardInterrupt`` included, which
        is re-raised as well. A ``cancel()`` landing before the job
        starts keeps it from running, and the widget dying with the job
        still pending cancels the future rather than leaving a waiter
        blocked.

        Args:
            job (Callable[P, T]): The callable to run on the mainloop.
            *args (P.args): Positional arguments for ``job``.
            **kwargs (P.kwargs): Keyword arguments for ``job``.

        Returns:
            A future resolved with ``job``'s result or exception, and
            cancelled if the widget dies first.

        Raises:
            RuntimeError: If called from another thread while the main
                thread is not in the mainloop.
        """
        future: Future[T] = Future()
        watch_id: str = ""
        timer: str = ""

        def work() -> None:
            if watch_id:
                with suppress(TclError):
                    self._tk.unbind("<Destroy>", watch_id)
            if not future.set_running_or_notify_cancel():
                return
            try:
                result = job(*args, **kwargs)
            except BaseException as exc:
                future.set_exception(exc)
                if not isinstance(exc, Exception):
                    raise
            else:
                future.set_result(result)

        def on_destroy(event: TkEvent[Misc]) -> None:
            if str(event.widget) == str(self._tk):
                future.cancel()
                if timer:
                    with suppress(TclError):
                        self._tk.after_cancel(timer)

        watch_id = self._tk.bind("<Destroy>", on_destroy, add="+")
        try:
            timer = self._tk.after(0, work)
        except TclError:
            future.cancel()
        return future

    def async_submit[T, **P](
        self,
        job: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> asyncio.Future[T]:
        """Run ``job`` on the mainloop and hand its result back, awaitably.

        :meth:`submit`'s async twin — the same action, aimed the other
        way: where ``submit`` schedules onto the mainloop for a caller
        who waits thread-style, this schedules the same crossing for a
        coroutine, answering an awaitable. It is the explicit crossing
        the two-sided async model sanctions: a coroutine on the
        facade's core touches no widget directly, so a widget read, a
        wrapper method, or an emit crosses here —
        ``text = await entry.async_submit(lambda: entry.text)`` — with
        the result, or the raise, delivered back into the awaiting
        coroutine. Built on :meth:`submit`, so this widget dying with
        the crossing still pending cancels it, arriving in the
        coroutine as lifecycle cancellation rather than error.

        Call it from a coroutine on the core: the crossing needs the
        mainloop genuinely running to land (`hazards/tkinter.md`, *Threads*),
        and the await needs a running loop to stand on.

        Args:
            job (Callable[P, T]): The function to run on the mainloop.
            *args (P.args): Positional arguments for ``job``.
            **kwargs (P.kwargs): Keyword arguments for ``job``.

        Returns:
            An awaitable resolving to ``job``'s return value, raising
            what ``job`` raised, or cancelled if the widget died first.
        """
        return asyncio.wrap_future(self.submit(job, *args, **kwargs))

    def nametowrapper(self, name: str | Misc | BaseWidget, /) -> BaseWidget:
        """Return the wrapper around the widget ``name`` identifies.

        The counterpart to ``tkinter.Misc.nametowidget``, answering
        with the wrapper rather than the Tk widget.

        A widget or wrapper is looked up on the interpreter it belongs
        to. A path string is looked up on this wrapper's interpreter,
        since a path alone does not say which root it came from, and a
        path not starting with ``.`` is taken as relative to this
        widget — both as ``nametowidget`` takes them.

        Only widgets a wrapper was built for are registered: a
        ``TextBox``'s inner text and scrollbars, and anything built
        with tkinter directly, are all misses. A multi-frame's pages
        are hits, being :class:`~tkfacade.Frame` wrappers the container
        built.

        Args:
            name (str | Misc | BaseWidget): A widget path, absolute or
                relative to this widget, or something whose ``str()``
                is one — a Tk widget, or another wrapper.

        Returns:
            The live wrapper registered for that path.

        Raises:
        KeyError: If no live wrapper holds that path, carrying the
            resolved path, as ``nametowidget`` raises carrying the
            name it could not resolve.
        """
        interpreter = name.tk if isinstance(name, Misc | BaseWidget) else self.tk
        path = str(name)
        if path and not path.startswith("."):
            here = str(self._tk)
            path = f"{here}.{path}" if here != "." else f".{path}"
        wrapper = BaseWidget._wrappers.get((interpreter, path))
        if wrapper is None:
            raise KeyError(path)
        return wrapper

    @staticmethod
    def _as_master(parent: Misc | BaseWidget, /) -> Misc:
        """Return the Tk widget behind ``parent``, for use as a master.

        A wrapper already duck-types as a master at runtime; this is the
        typed spelling of the same thing, unwrapping to the real widget so
        tkinter's annotated constructors accept it without complaint.

        Args:
            parent (Misc | BaseWidget): A Tk widget, or a wrapper
                around one.

        Returns:
            ``parent`` itself, or the widget it wraps.
        """
        return parent._tk if isinstance(parent, BaseWidget) else parent
