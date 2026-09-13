"""The facade's async core: one loop thread per root, lazily started.

Coroutine functions admitted through the facade's registration surfaces
— a command or watcher given as ``async def`` — run on a root-owned
asyncio loop beside the mainloop, with a paired thread pool as the
loop's default executor so blocking work inside a coroutine has a home
(``asyncio.to_thread``).

The registry below maps a Tcl interpreter to its root's core factory,
so the dispatch — which holds a widget, not a root — reaches the core
without the widget or observable packages importing the window
package. Registry access is main-thread-only, like the dispatch that
uses it.
"""

import asyncio
import concurrent.futures
import threading
from collections.abc import Callable, Coroutine
from contextlib import suppress
from typing import Any, Final

_READY_WAIT: Final = 5.0
"""Seconds :meth:`Core.start` waits for the loop thread to take work."""


class Core:
    """An asyncio loop on its own thread, taking coroutines from the mainloop.

    Built and started once by a root on first async need, stopped by
    that root's teardown, never restarted — a new root builds a new
    core. The paired pool is the loop's default executor, so
    ``asyncio.to_thread`` inside an admitted coroutine lands there.
    """

    __slots__ = ("_closing", "_loop", "_pool", "_ready", "_thread")

    def __init__(self) -> None:
        """Prepare without starting anything; :meth:`start` brings the loop up."""
        self._ready = threading.Event()
        self._closing = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pool = concurrent.futures.ThreadPoolExecutor(thread_name_prefix="tkfacade-core")

    def _run(self) -> None:
        """Thread target: build the loop, signal readiness, serve forever."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_default_executor(self._pool)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    def start(self) -> None:
        """Start the loop thread and block briefly until it takes work."""
        self._thread = threading.Thread(target=self._run, name="tkfacade-core", daemon=True)
        self._thread.start()
        self._ready.wait(_READY_WAIT)

    def submit(self, coro: Coroutine[Any, Any, Any], /) -> concurrent.futures.Future[Any]:
        """Schedule ``coro`` on the loop; the future is its explicit channel.

        Args:
            coro (Coroutine[Any, Any, Any]): The coroutine to run.

        Returns:
            The scheduling future. Cancelling it is fire-and-forget
            toward the coroutine (`experiments/async_route/`): the
            future reports cancelled at once and the unwinding arrives
            on the loop afterward.

        Raises:
            RuntimeError: If the core is stopping or never started.
                ``coro`` is closed first, so a refused submission never
                leaves an un-awaited coroutine behind.
        """
        if self._closing or self._loop is None or not self._ready.is_set():
            coro.close()
            raise RuntimeError("the core is not taking work")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _drain(self, grace: float) -> None:
        """On the loop: give tasks ``grace`` to finish, cancel the rest, wait."""
        current = asyncio.current_task()
        loop = asyncio.get_running_loop()
        pending = {task for task in asyncio.all_tasks(loop) if task is not current}
        if pending and grace > 0:
            _, pending = await asyncio.wait(pending, timeout=grace)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await loop.shutdown_asyncgens()

    def stop(self, *, grace: float = 0.5, timeout: float = 5.0) -> None:
        """Drain, stop, and join, in the witnessed order. Idempotent.

        Args:
            grace (float): Seconds running tasks get to finish before
                they are cancelled. Defaults to 0.5.
            timeout (float): Seconds to wait for the drain, and again
                for the join. Defaults to 5.0.

        Raises:
            RuntimeError: If called from the core's own thread, which
                would be a join of itself.
        """
        if self._thread is not None and threading.current_thread() is self._thread:
            raise RuntimeError("the core cannot stop itself from its own thread")
        if self._closing:
            return
        self._closing = True
        loop, thread = self._loop, self._thread
        if loop is None or thread is None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            return
        try:
            drained = asyncio.run_coroutine_threadsafe(self._drain(grace), loop)
        except RuntimeError:
            pass  # the loop is already gone; the join below settles it
        else:
            with suppress(TimeoutError, concurrent.futures.CancelledError):
                drained.result(timeout)
        with suppress(RuntimeError):
            loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout)
        self._pool.shutdown(wait=False, cancel_futures=True)


_factories: Final[dict[object, Callable[[], Core]]] = {}
"""Per-interpreter core factories, registered by each root at birth."""


def attach_core(interpreter: object, factory: Callable[[], Core], /) -> None:
    """Register ``interpreter``'s core factory; the root's construction calls this."""
    _factories[interpreter] = factory


def detach_core(interpreter: object, /) -> None:
    """Forget ``interpreter``'s factory; the root's teardown calls this."""
    _factories.pop(interpreter, None)


def resolve_core(interpreter: object, /) -> Core | None:
    """Return ``interpreter``'s core, built on first need; None when rootless."""
    factory = _factories.get(interpreter)
    return None if factory is None else factory()


def launch(
    core: Core,
    coro: Coroutine[Any, Any, Any],
    tasks: set[concurrent.futures.Future[Any]],
    report: Callable[[BaseException], None],
) -> None:
    """Schedule ``coro`` fire-and-forget: track it, report a raise on landing.

    The notification routes' shared shape, as for any scheduled
    coroutine: the scheduling future joins ``tasks`` so the registration
    handle's cancel can reach work in flight, cancellation stays silent
    lifecycle in both its spellings, and any other raise goes to
    ``report`` — the caller hands in the wall-safe route to the hook.
    A refused submission (the core stopping) is reported the same way.
    """
    try:
        future = core.submit(coro)
    except RuntimeError as exc:
        report(exc)
        return
    tasks.add(future)

    def landed(done: concurrent.futures.Future[Any]) -> None:
        tasks.discard(done)
        if done.cancelled():
            return
        exc = done.exception()
        if exc is not None and not isinstance(
            exc, asyncio.CancelledError | concurrent.futures.CancelledError
        ):
            report(exc)

    future.add_done_callback(landed)
