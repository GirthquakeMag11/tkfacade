"""The Dialog foundation: an owned window, a future, and one completion.

A dialog is not a widget — it owns one. :class:`Dialog` builds and
customizes a :class:`~tkfacade.Window` to suit, encapsulates it — the
window is never answered publicly — and wraps a future that receives
the displayed dialog's result. The class is the foothold for building
dialogs as such: the library's own roster, and a possible future
feature of entirely custom user dialogs.

The modality mechanics: Tk's waits park their caller in a nested event
loop that keeps pumping; a grab redirects clicks aimed elsewhere to
the grab holder; the async core's marshalled completions land while a
sync wait is parked; and a grab dies with its window, so teardown
needs no explicit release.
"""

import asyncio
import threading
import tkinter as tk
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from ..window import Window


class Dialog[ResultT]:
    """A modal prompt: an owned window, shown, completed exactly once.

    Not a widget — the dialog *owns* its window and never answers it:
    what a caller reaches is the lifecycle (:meth:`show`,
    :meth:`complete`, :meth:`cancel`) and the result's two doors —
    :meth:`result` blocking synchronously while the application keeps
    pumping, and :meth:`wait` awaitable from a coroutine on the
    root's core. The result type rides the class's one type
    parameter, and every route answers ``ResultT | None`` — ``None``
    is the spelling of a dialog dismissed without an answer, whether by
    :meth:`cancel`, the Escape key, the titlebar's close button, or the
    window being destroyed outright.

    Whatever path ends the dialog, the future resolves first and the
    window dies second, so no path leaves a parked caller. Completing
    twice is not an error; the first result stands and later calls do
    nothing.

    A concrete dialog builds its content in ``__init__`` with the
    owned window (``self._window``) as the master, wires its
    affirmative path to ``self.complete(value)`` and its negative one
    to ``self.cancel()``, and leaves showing and waiting to the base.
    The window stays an implementation detail: nothing public should
    hand it out.

    Nested dialogs are legal and stack-shaped: Tk's waits unwind
    last-in, first-out, so an outer synchronous dialog cannot return
    while an inner one is still posted.
    """

    __slots__ = (
        "_done",
        "_outcome",
        "_parent",
        "_resolved",
        "_waiters",
        "_waiters_lock",
        "_window",
    )

    def __init__(
        self,
        parent: Window,
        /,
        *,
        title: str | None = None,
        width: int = 300,
        height: int = 200,
    ) -> None:
        """Build the owned window, customized and held back from view.

        The window is created withdrawn — :meth:`show` is what posts
        it — transient to ``parent``, on the parent's own root, with
        the close-box, the Escape key, and destruction itself all
        routed into completion.

        Args:
            parent (Window): The window this dialog prompts for; the
                dialog is transient to it and lives on its root.
            title (str | None): The dialog window's title. Defaults
                to None, meaning the class name.
            width (int): The window's width in pixels. Defaults to 300.
            height (int): The window's height in pixels. Defaults to 200.
        """
        self._parent = parent
        self._resolved = False
        self._outcome: ResultT | None = None
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future[ResultT | None]]] = []
        self._waiters_lock = threading.Lock()
        window = Window(
            title=title if title is not None else type(self).__name__,
            width=width,
            height=height,
            root=parent._root,
        )
        self._window = window
        self._done = tk.IntVar(master=parent._root._tk)
        window._tk.withdraw()
        window._tk.transient(parent._tk)
        window._tk.protocol("WM_DELETE_WINDOW", self.cancel)
        window._tk.bind("<Escape>", lambda event: self.cancel(), add="+")
        window._tk.bind("<Destroy>", self._on_destroy, add="+")

    # ----------
    # Lifecycle
    # ----------

    @property
    def done(self) -> bool:
        """Whether the dialog has completed; its result stands from then on."""
        return self._resolved

    def show(self) -> None:
        """Post the dialog: map the window, take the grab and the focus.

        The grab is what makes the dialog modal: real clicks aimed at
        the application's other windows are redirected here while it
        stands, and it dies with the window, needing no release on any
        teardown path. Showing an already-completed dialog does
        nothing. An interpreter-thread act, like all tk work.
        """
        if self._resolved:
            return
        shown = self._window._tk
        shown.deiconify()
        shown.update()
        shown.grab_set()
        shown.focus_force()

    def complete(self, result: ResultT | None, /) -> None:
        """Resolve the dialog with ``result``, then destroy its window.

        The order is the contract: the outcome is settled and every
        waiter — synchronous and awaitable alike — is released
        *before* the window dies, so no ending leaves a parked
        caller. Only the first completion counts; later calls,
        including the destruction path's own, do nothing.

        Args:
            result (ResultT | None): The dialog's answer; None is the
                dismissed-without-an-answer spelling.
        """
        if self._resolved:
            return
        with self._waiters_lock:
            self._outcome = result
            self._resolved = True
            waiters, self._waiters = self._waiters, []
        for loop, future in waiters:
            loop.call_soon_threadsafe(_resolve, future, result)
        with suppress(tk.TclError):
            self._done.set(1)
        self._window.destroy()

    def cancel(self) -> None:
        """Complete with None: the dismissed-without-an-answer ending."""
        self.complete(None)

    def _on_destroy(self, event: tk.Event[tk.Misc]) -> None:
        """Bind completion to destruction: a dying window resolves first.

        A ``<Destroy>`` binding hears every child under the window
        (`hazards/tkinter.md`, *Bindings*), so the guard keys on the window
        itself. By the time this fires for an external destroy the
        completion path's own ``destroy`` is a no-op, and for a
        completion-driven destroy the resolve already happened — the
        once-guard makes the two paths one.
        """
        if event.widget is self._window._tk:
            self.complete(None)

    # ------------------
    # The result's doors
    # ------------------

    def result(self) -> ResultT | None:
        """Show the dialog and block until it completes; the sync door.

        The caller parks in Tk's nested wait — the application keeps
        pumping while this frame stands still — and resumes with the
        outcome the moment the dialog completes. Calling after
        completion answers the standing outcome immediately.

        Returns:
            The dialog's answer, or None for a dismissal.
        """
        self.show()
        if not self._resolved:
            self._parent._root._tk.wait_variable(self._done)
        return self._outcome

    async def wait(self) -> ResultT | None:
        """Await the dialog's completion; the async door.

        Await it from a coroutine on the root's core. This door only
        waits: posting the window is the interpreter thread's act, so
        the dialog is shown from the mainloop side. No nested wait
        stands anywhere on this route — the mainloop stays fully live.
        Awaiting an already-completed dialog answers immediately.

        Returns:
            The dialog's answer, or None for a dismissal.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ResultT | None] = loop.create_future()
        with self._waiters_lock:
            if self._resolved:
                return self._outcome
            self._waiters.append((loop, future))
        try:
            return await future
        finally:
            with self._waiters_lock, suppress(ValueError):
                self._waiters.remove((loop, future))

    def __repr__(self) -> str:
        """Name the class and where the dialog stands in its life."""
        state = "done" if self._resolved else "open"
        return f"<{type(self).__name__} {state}>"


def _resolve[ResultT](future: asyncio.Future[ResultT | None], result: ResultT | None, /) -> None:
    """Complete one waiter, tolerating a cancel that beat the crossing."""
    if not future.done():
        future.set_result(result)


async def _posted[DialogT: Dialog[Any]](
    parent: Window, factory: Callable[[], DialogT], /
) -> DialogT:
    """Build and show a dialog on the interpreter's thread; answer its handle.

    The async twins' shared crossing: a coroutine runs on the core's
    thread where tk work is walled off, so construction and showing
    are marshalled to the mainloop with the library's own
    ``after(0, ...)`` door and the handle crosses back through the
    running loop. A factory that raises delivers its raise here, on
    the awaiting coroutine.
    """
    loop = asyncio.get_running_loop()
    made: asyncio.Future[DialogT] = loop.create_future()

    def build() -> None:
        try:
            box = factory()
            box.show()
        except BaseException as error:
            loop.call_soon_threadsafe(_deliver_raise, made, error)
            return
        loop.call_soon_threadsafe(_deliver, made, box)

    parent._root._tk.after(0, build)
    return await made


def _deliver[DialogT: Dialog[Any]](future: asyncio.Future[DialogT], box: DialogT, /) -> None:
    """Hand the built dialog to its waiter, tolerating a beaten cancel."""
    if not future.done():
        future.set_result(box)


def _deliver_raise(future: asyncio.Future[Any], error: BaseException, /) -> None:
    """Hand a factory's raise to the waiter, tolerating a beaten cancel."""
    if not future.done():
        future.set_exception(error)
