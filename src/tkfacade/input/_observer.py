"""Root-held input state: what is pressed right now, and chords over it.

The keyboard and mouse observer: the root listens for every key and
button press and release, holds the current state — pressed or not —
for any widget to query at any time, and offers the chord condition on
top: notification when a defined set of inputs is all held at once,
the core of user-defined key-combination macros.

The two facts every global tracker trips over are discharged here, both
recorded in `hazards/tkinter.md` (*Input state*): X11 autorepeat delivers
phantom release/press pairs sharing one timestamp — a release is
therefore held until the next event is known, and dropped with its
pair — and a release after focus leaves the application never arrives
at all, so all held state clears when the application loses focus.
"""

import asyncio
import concurrent.futures
import threading
import tkinter as tk
from contextlib import suppress
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from .._command import dispatch_command
from .._subscription import Subscription
from .._types import Command
from ..events import Key, MouseButton

if TYPE_CHECKING:
    from ..window import Root

type InputName = Key | KeyGroup | MouseButton | str | int
"""One trackable input: a key by keysym, a modifier by role, or a mouse
button by number."""


class KeyGroup(StrEnum):
    """A modifier named by role, either physical variant satisfying it.

    The observer tracks left and right modifiers as the distinct keys
    they are, so a chord on :attr:`~tkfacade.Key.LEFT_CONTROL` fires
    on the left key only. A group names the role instead: a chord
    requirement given as :attr:`CONTROL` is met while *either*
    ``Control_L`` or ``Control_R`` is down, which is what a shortcut
    like Ctrl+S means everywhere else. The bare spellings — the
    members' own values, ``"Control"`` and so on — are accepted by
    :meth:`InputObserver.chord` identically; none of them collides
    with a real keysym.
    """

    CONTROL = "Control"
    SHIFT = "Shift"
    ALT = "Alt"
    META = "Meta"
    SUPER = "Super"


_GROUP_KEYS: Final[dict[str, frozenset[str]]] = {
    str(group): frozenset({str(Key[f"LEFT_{group.name}"]), str(Key[f"RIGHT_{group.name}"])})
    for group in KeyGroup
}
"""Each group spelling, expanded to the variant keysyms that satisfy it."""

_MODIFIER_RANKS: Final[dict[str, int]] = {
    spelling: rank
    for rank, role in enumerate(("Control", "Alt", "Shift", "Meta", "Super"))
    for spelling in (role, f"{role}_L", f"{role}_R")
}
"""Caption order for the modifier spellings, groups and variants alike."""

_MODIFIER_CAPTIONS: Final[dict[str, str]] = {
    "Control": "Ctrl",
    "Control_L": "LeftCtrl",
    "Control_R": "RightCtrl",
    "Alt_L": "LeftAlt",
    "Alt_R": "RightAlt",
    "Shift_L": "LeftShift",
    "Shift_R": "RightShift",
    "Meta_L": "LeftMeta",
    "Meta_R": "RightMeta",
    "Super_L": "LeftSuper",
    "Super_R": "RightSuper",
}
"""Modifier spellings whose caption is not the spelling itself."""

_KEY_CAPTIONS: Final[dict[str, str]] = {
    "Return": "Enter",
    "Escape": "Esc",
    "Prior": "PgUp",
    "Next": "PgDn",
    "space": "Space",
}
"""Keysyms whose conventional caption differs from their spelling."""


def _caption_for(spelling: str, /) -> str:
    """The display spelling of one key, modifier or not."""
    if spelling in _MODIFIER_RANKS:
        return _MODIFIER_CAPTIONS.get(spelling, spelling)
    if len(spelling) == 1:
        return spelling.upper()
    return _KEY_CAPTIONS.get(spelling, spelling)


def _checked_key(spelling: str, /) -> str:
    """Return ``spelling`` as a keysym, refusing what Tk could never report.

    Raises:
        ValueError: If the spelling is empty or carries binding syntax.
    """
    keysym = str(spelling)
    if not keysym or any(part in keysym for part in ("<", ">", " ")):
        raise ValueError(f"not a keysym: {keysym!r}")
    return keysym


class Chord(Subscription):
    """A set of inputs that notifies when all of them are held at once.

    Built by :meth:`InputObserver.chord`, never directly. The chord is
    edge-triggered: it fires at the moment its whole set becomes held —
    keys and buttons alike — and not again until some member is
    released first; inputs held *beyond* the set do not block it, so a
    chord for Control+S fires with Shift also down. Two notification
    routes, both command-shaped: :meth:`subscribe` registers
    a command of either kind, and :meth:`wait` answers an awaitable
    for a coroutine on the root's core — the macro shape,
    ``await chord.wait()`` then act.

    A key may be named exactly, by keysym — ``Control_L`` is the left
    key alone — or by role through a :class:`KeyGroup` spelling, which
    either physical variant satisfies. Both spell the same way in
    :attr:`inputs` and the derived :attr:`caption`.

    The chord is immutable, by ruling (2026-08-27): the set it waits
    on is fixed at construction and can never be changed, so anything
    that consumes a chord — a menu row's accelerator, a saved macro —
    may derive from it once and rely on nothing drifting afterward.

    A chord is itself the :class:`~tkfacade.Subscription` for its place
    in the observer: :meth:`cancel` unregisters it, after which it
    never fires and its pending waiters are cancelled.
    """

    __slots__ = (
        "_buttons",
        "_complete",
        "_keys",
        "_observer",
        "_requirements",
        "_subscribers",
        "_tasks",
        "_waiters",
        "_waiters_lock",
    )

    def __init__(
        self,
        observer: InputObserver,
        keys: frozenset[str],
        requirements: frozenset[frozenset[str]],
        buttons: frozenset[int],
        /,
    ) -> None:
        self._keys = keys
        self._requirements = requirements
        self._buttons = buttons
        self._observer = observer
        self._complete = False
        self._subscribers: list[Command] = []
        self._tasks: set[concurrent.futures.Future[Any]] = set()
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = []
        self._waiters_lock = threading.Lock()
        super().__init__(lambda: observer._drop(self))

    @property
    def held(self) -> bool:
        """Whether the whole set is held right now."""
        return self._complete

    @property
    def inputs(self) -> frozenset[Key | MouseButton | str | int]:
        """The set this chord waits on, by spelling.

        A group requirement appears as its role spelling
        (``"Control"``), an exact one as its keysym, a button as its
        number — plain ``str`` and ``int``, whatever enum members the
        chord was built from.
        """
        return frozenset(self._keys) | frozenset(self._buttons)

    @property
    def caption(self) -> str:
        """The set as conventional shortcut text, derived — ``Ctrl+O``.

        One derivation for anything that displays a chord, so the text
        can never drift from the binding: modifiers first (Ctrl, Alt,
        Shift, Meta, Super), remaining keys sorted, mouse buttons as
        ``Mouse1`` last, joined with ``+``. A group renders as its
        role — ``Ctrl`` — while an exact variant renders honestly as
        that key alone, ``LeftCtrl``, never promising the other one.
        """
        modifiers = sorted(
            (key for key in self._keys if key in _MODIFIER_RANKS),
            key=lambda key: (_MODIFIER_RANKS[key], key),
        )
        others = sorted(key for key in self._keys if key not in _MODIFIER_RANKS)
        parts = [_caption_for(key) for key in (*modifiers, *others)]
        parts.extend(f"Mouse{number}" for number in sorted(self._buttons))
        return "+".join(parts)

    def subscribe(self, command: Command, /) -> Subscription:
        """Run ``command`` each time the set becomes held.

        Args:
            command (Command): A plain callable run on the mainloop,
                or a coroutine function scheduled on the root's core —
                fire-and-forget either way, raises routed to the
                callback hook.

        Returns:
            The registration's handle; cancelling it removes only this
            subscriber.
        """
        self._subscribers.append(command)
        return Subscription(lambda: self._subscribers.remove(command))

    async def wait(self) -> None:
        """Complete the next time the set becomes held.

        Await it from a coroutine on the root's core. Each completion
        releases the waiters registered before it; awaiting again waits
        for the next edge. Cancelled — as lifecycle, silently — when
        the chord or the observer is cancelled first.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        with self._waiters_lock:
            self._waiters.append((loop, future))
        try:
            await future
        finally:
            with self._waiters_lock, suppress(ValueError):
                self._waiters.remove((loop, future))

    def _met_by(self, keys: set[str], buttons: set[int], /) -> bool:
        """Whether the held state covers this chord's whole set."""
        every_key = all(requirement & keys for requirement in self._requirements)
        return every_key and self._buttons <= buttons

    def _update(self, met: bool, /) -> None:
        """Track the edge: fire exactly when the set becomes complete."""
        if met and not self._complete:
            self._complete = True
            self._fire()
        elif not met:
            self._complete = False

    def _fire(self) -> None:
        """Notify every subscribed route."""
        for held in tuple(self._subscribers):
            dispatch_command(self._observer._tk, held, self._tasks, f"a subscriber of {self!r}")
        with self._waiters_lock:
            waiters, self._waiters = self._waiters, []
        for loop, future in waiters:
            loop.call_soon_threadsafe(_resolve, future)

    def _shut(self) -> None:
        """Cancel pending waiters; the chord will never fire again."""
        with self._waiters_lock:
            waiters, self._waiters = self._waiters, []
        for loop, future in waiters:
            loop.call_soon_threadsafe(future.cancel)

    def __repr__(self) -> str:
        """Name the class and the set it waits on."""
        names = sorted(str(part) for part in (*self._keys, *self._buttons))
        return f"<{type(self).__name__} {'+'.join(names)}>"


def _resolve(future: asyncio.Future[None], /) -> None:
    """Complete one waiter, tolerating a cancel that beat the crossing."""
    if not future.done():
        future.set_result(None)


class InputObserver:
    """The root's record of every key and button: pressed, or not.

    Owned by :class:`~tkfacade.window.Root` and reached as its
    :attr:`~tkfacade.window.Root.inputs`, so any widget queries it
    through :func:`~tkfacade.get_root` at any time. One interpreter-
    level binding per event kind observes without stealing: the
    widgets' own bindings keep running first.

    What the state means: a key is pressed while the X server says its
    key is down — autorepeat's phantom release/press pairs are paired
    by their shared timestamp and dropped, so held state never
    flickers — and everything clears when the application loses the
    input focus, because the release that happens elsewhere will never
    arrive (`hazards/tkinter.md`, *Input state*). X11's wheel arrives as
    buttons 4 and 5 and carries no held state, so those two are not
    tracked there.
    """

    __slots__ = (
        "_chords",
        "_flush_job",
        "_focus_job",
        "_pending_release",
        "_pressed_buttons",
        "_pressed_keys",
        "_tk",
        "_wheel_buttons",
    )

    def __init__(self, root: Root, /) -> None:
        """Attach the observation bindings to ``root``'s interpreter.

        Args:
            root (Root): The root wrapper whose interpreter carries
                the observation; taken as the wrapper so no tkinter
                type rides this signature.
        """
        self._tk: tk.Tk = root._tk
        self._pressed_keys: set[str] = set()
        self._pressed_buttons: set[int] = set()
        self._pending_release: tuple[str, int] | None = None
        self._flush_job: str | None = None
        self._focus_job: str | None = None
        self._chords: list[Chord] = []
        x11 = str(self._tk.tk.call("tk", "windowingsystem")) == "x11"
        self._wheel_buttons: frozenset[int] = frozenset({4, 5}) if x11 else frozenset()
        self._tk.bind_all("<KeyPress>", self._on_key_press, add="+")
        self._tk.bind_all("<KeyRelease>", self._on_key_release, add="+")
        self._tk.bind_all("<ButtonPress>", self._on_button_press, add="+")
        self._tk.bind_all("<ButtonRelease>", self._on_button_release, add="+")
        self._tk.bind_all("<FocusOut>", self._on_focus_out, add="+")

    # ------
    # Query
    # ------

    def is_pressed(self, input: InputName, /) -> bool:
        """Whether ``input`` is held right now.

        Args:
            input (InputName): A key — a :class:`~tkfacade.Key` member or
                any keysym spelling — or a mouse button, as a
                :class:`~tkfacade.MouseButton` member or its number.

        Returns:
            True while the key or button is down.
        """
        if isinstance(input, str):
            spelling = str(input)
            variants = _GROUP_KEYS.get(spelling)
            if variants is not None:
                return bool(variants & self._pressed_keys)
            return spelling in self._pressed_keys
        return int(input) in self._pressed_buttons

    @property
    def pressed_keys(self) -> frozenset[str]:
        """The keysyms held right now, a snapshot."""
        return frozenset(self._pressed_keys)

    @property
    def pressed_buttons(self) -> frozenset[int]:
        """The mouse buttons held right now, by number, a snapshot."""
        return frozenset(self._pressed_buttons)

    # ------
    # Chords
    # ------

    def chord(self, *inputs: InputName) -> Chord:
        """Register a chord over ``inputs`` and answer its handle.

        Args:
            *inputs (InputName): The keys and buttons that must all be
                held at once, at least one. A key is named exactly by
                keysym, or by role with a :class:`KeyGroup` spelling —
                ``"Control"`` is met by either physical Control key,
                where ``"Control_L"`` stays the left one alone.

        Returns:
            The live :class:`Chord`; cancel it to unregister.

        Raises:
            ValueError: If no input is given, or a key spelling could
                never be a keysym.
        """
        if not inputs:
            raise ValueError("a chord needs at least one input")
        keys: set[str] = set()
        requirements: set[frozenset[str]] = set()
        buttons: set[int] = set()
        for part in inputs:
            if isinstance(part, str):
                spelling = str(part)
                variants = _GROUP_KEYS.get(spelling)
                if variants is None:
                    spelling = _checked_key(spelling)
                    variants = frozenset({spelling})
                keys.add(spelling)
                requirements.add(variants)
            else:
                buttons.add(int(part))
        registered = Chord(self, frozenset(keys), frozenset(requirements), frozenset(buttons))
        self._chords.append(registered)
        registered._update(registered._met_by(self._pressed_keys, self._pressed_buttons))
        return registered

    def _drop(self, chord: Chord, /) -> None:
        """Unregister ``chord`` and cancel its pending waiters."""
        with suppress(ValueError):
            self._chords.remove(chord)
        chord._shut()

    def _settle(self) -> None:
        """Re-judge every chord against the state that just changed."""
        for chord in tuple(self._chords):
            chord._update(chord._met_by(self._pressed_keys, self._pressed_buttons))

    # -------------------
    # The state machinery
    # -------------------

    def _on_key_press(self, event: tk.Event[tk.Misc]) -> None:
        """Record a press — unless it pairs with the pending release as a repeat."""
        pending, self._pending_release = self._pending_release, None
        self._cancel_flush()
        if pending is not None:
            if pending[0] == event.keysym and pending[1] == event.time:
                return  # autorepeat's phantom pair: the key never moved
            self._release_key(pending[0])
        if event.keysym not in self._pressed_keys:
            self._pressed_keys.add(event.keysym)
            self._settle()

    def _on_key_release(self, event: tk.Event[tk.Misc]) -> None:
        """Hold the release until the next event says whether it was real.

        The autorepeat signature: a phantom release is followed
        immediately by a press of the same key with the identical
        timestamp. The release is applied by the very next event, or by
        the flush timer when no next event comes — a real release at
        the end of a burst.
        """
        self._flush_pending()
        self._pending_release = (event.keysym, event.time)
        self._flush_job = self._tk.after(1, self._flush_pending)

    def _flush_pending(self) -> None:
        """Apply a held release that no press claimed as its pair."""
        self._cancel_flush()
        pending, self._pending_release = self._pending_release, None
        if pending is not None:
            self._release_key(pending[0])

    def _cancel_flush(self) -> None:
        """Cancel the pending flush timer, if one is armed."""
        if self._flush_job is not None:
            with suppress(tk.TclError):
                self._tk.after_cancel(self._flush_job)
            self._flush_job = None

    def _release_key(self, keysym: str, /) -> None:
        """Record one key coming up."""
        if keysym in self._pressed_keys:
            self._pressed_keys.discard(keysym)
            self._settle()

    def _on_button_press(self, event: tk.Event[tk.Misc]) -> None:
        """Record a button going down; X11's wheel buttons stay untracked.

        A button event is "the next event" a pending key release waits
        on, and can never be its autorepeat pair — so the release is
        applied first, or a chord would fire on a key already up.
        """
        self._flush_pending()
        if event.num in self._wheel_buttons:
            return
        if event.num not in self._pressed_buttons:
            self._pressed_buttons.add(event.num)
            self._settle()

    def _on_button_release(self, event: tk.Event[tk.Misc]) -> None:
        """Record a button coming up; a pending key release lands first."""
        self._flush_pending()
        if event.num in self._pressed_buttons:
            self._pressed_buttons.discard(event.num)
            self._settle()

    def _on_focus_out(self, _event: tk.Event[tk.Misc]) -> None:
        """Schedule the focus check: clearing waits until focus settles."""
        if self._focus_job is None:
            self._focus_job = self._tk.after_idle(self._check_focus)

    def _check_focus(self) -> None:
        """Clear all held state when the application no longer has focus.

        A focus move *within* the application lands on another widget
        by the time this runs and clears nothing; only focus leaving
        the application — after which no release will ever arrive —
        drops the state. ``focus_get`` raising for an exotic holder (a
        menu's own window) reads as focus still being ours.
        """
        self._focus_job = None
        try:
            focused = self._tk.focus_get()
        except KeyError, tk.TclError:
            return
        if focused is not None:
            return
        self._flush_pending()
        if self._pressed_keys or self._pressed_buttons:
            self._pressed_keys.clear()
            self._pressed_buttons.clear()
            self._settle()

    def _teardown(self) -> None:
        """Cancel jobs and waiters before the interpreter goes.

        The interpreter-level bindings die with the interpreter; what
        would outlive it — after jobs, coroutine waiters parked on the
        core — is ended here.
        """
        self._cancel_flush()
        if self._focus_job is not None:
            with suppress(tk.TclError):
                self._tk.after_cancel(self._focus_job)
            self._focus_job = None
        for chord in tuple(self._chords):
            chord._shut()
        self._chords.clear()
