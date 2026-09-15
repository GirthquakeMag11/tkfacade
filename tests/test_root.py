"""The :class:`~tkfacade.window.Root` lifecycle and its window registry.

Tk allows one interpreter per process, so the shared root's identity,
replacement, and teardown cascade are the contracts everything else in
the package stands on. Every test runs on the ``root`` fixture's fresh
interpreter and carries the ``gui`` marker.
"""

import threading

import pytest

import tkfacade
from tkfacade.widget import Surface
from tkfacade.window import Root, get_root
from tkfacade.window import _root as _root_module

pytestmark = pytest.mark.gui


def test_get_root_shares_one_instance(root: Root) -> None:
    """Repeated ``get_root`` calls answer with the same live root.

    The whole point of get_root is that the process shares one interpreter; two calls answering different roots would give every module its own Tk and break cross-window state (keyboard tracking, Surface registries) silently. Identity, not equality, is the contract. The fixture's root is included so the test also proves the fixture hands out the shared instance rather than a private one.
    """
    assert get_root() is root
    assert get_root() is get_root()


def test_get_root_replaces_a_destroyed_root(root: Root) -> None:
    """After the shared root dies, ``get_root`` builds a fresh live one.

    The documented self-healing path: "a destroyed root is transparently replaced on the next call". Without it, the first window closing (which cascades the root down) would leave every later get_root caller holding a dead interpreter. The replacement is asserted live because returning the old object un-destroyed is the failure mode the ``or _root.destroyed`` guard exists for.
    """
    root.destroy()

    replacement = get_root()

    assert replacement is not root
    assert not replacement.destroyed


def test_add_child_is_idempotent_and_rem_child_tolerates_absence(root: Root) -> None:
    """Re-registering a window adds nothing; removing a stranger is a no-op.

    Window.__init__ already registers itself, so the explicit add_child here is a genuine double registration — the case the idempotence guard exists for, since a duplicate entry would make rem_child leave a stale strong reference behind (its while-loop is the other half pinned here). The second rem_child pins "missing is fine" straight from the docstring.
    """
    window = tkfacade.Window(title="only", root=root)

    root.add_child(window)
    after_double_add = root.windows

    root.rem_child(window)
    root.rem_child(window)
    after_double_rem = root.windows

    assert after_double_add == (window,)
    assert after_double_rem == ()


def test_windows_lists_oldest_first(root: Root) -> None:
    """The registry answers wrappers in creation order.

    Creation order is documented ("oldest first") and callers use it to find their main window. Two windows are enough: any accidental reordering — a set, a dict keyed by name — shows up as a swapped or unstable pair.
    """
    first = tkfacade.Window(title="first", root=root)
    second = tkfacade.Window(title="second", root=root)

    assert root.windows == (first, second)


def test_last_window_destruction_cascades_to_the_root(root: Root) -> None:
    """Destroying the only window tears its root down with it.

    The teardown cascade is BaseWindow's defining behavior: an app closes its last window and the mainloop ends, with no explicit shutdown call. The registry is checked empty because Root.destroy promises to release its wrapper references — a destroyed root still holding windows would keep icons and wrappers alive forever.
    """
    window = tkfacade.Window(title="only", root=root)

    window.destroy()

    assert root.destroyed
    assert root.windows == ()


def test_surviving_window_keeps_the_root_alive(root: Root) -> None:
    """Destroying one window of two leaves the root standing.

    The other half of the cascade contract: the root goes down with the *last* toplevel, not with any toplevel. The registry assertion pins that destroy also unregistered the dead window — a stale entry would resurrect it through the windows tuple.
    """
    doomed = tkfacade.Window(title="doomed", root=root)
    survivor = tkfacade.Window(title="survivor", root=root)

    doomed.destroy()

    assert not root.destroyed
    assert root.windows == (survivor,)


def test_a_window_manager_close_runs_the_cascade(root: Root) -> None:
    """Invoking the WM_DELETE_WINDOW handler tears down like a wrapper destroy.

    The teardown cascade lived only in the Python destroy override, and Tk's default for WM_DELETE_WINDOW destroys the toplevel at Tcl level where an override is never invoked — so a user closing the last window by the titlebar button left the interpreter and mainloop alive forever, and a closed non-last window's wrapper stayed pinned in the registry. No window manager exists under the test display, so the test does what one would: reads the registered protocol command off the widget and invokes it through the interpreter. Both halves are driven — a non-last close must unregister without tearing the root down, and the last close must end everything.
    """
    survivor = tkfacade.Window(title="survivor", root=root)
    doomed = tkfacade.Window(title="doomed", root=root)
    command = str(doomed._tk.protocol("WM_DELETE_WINDOW"))
    assert command

    doomed._tk.tk.call(command)

    assert root.windows == (survivor,)
    assert not root.destroyed

    survivor._tk.tk.call(str(survivor._tk.protocol("WM_DELETE_WINDOW")))

    assert root.destroyed


class _RecordingSurface(Surface):
    """A :class:`Surface` that records the liveness of its frames at teardown.

    The ordering probe for the two destroy hooks below: ``(outer,
    inner)`` answers whether each frame still existed at the moment
    :meth:`_surface_teardown` ran, and one entry per teardown pins
    that it ran exactly once.
    """

    __slots__ = ("observations",)

    def __init__(self, parent: tkfacade.Window, observations: list[tuple[bool, bool]]) -> None:
        self.observations: list[tuple[bool, bool]] = observations
        super().__init__(parent)

    def _surface_teardown(self) -> None:
        super()._surface_teardown()
        self.observations.append(
            (bool(self._tk.winfo_exists()), bool(self._surface.winfo_exists()))
        )


def test_root_destruction_tears_surfaces_down_while_the_window_lives(root: Root) -> None:
    """``Root.destroy`` runs surface teardowns before Tk frees their windows.

    The Windows hard crash behind issue #6: teardown lived only in the reactive ``<Destroy>`` binding, which fires *during* Tk's destroy — by then the inner drawing frame, the native window an mpv render context is bound to, is already freed, and a backend writing into it kills the process with 0xe24c4a02 rather than raising. Benign on X11, so the ordering is asserted directly instead of by crash: at teardown both frames must still exist. The single-entry list is the other half of the contract — the reactive binding stays armed as the backstop for raw frame destroys and must not run a second teardown after the proactive one.
    """
    observations: list[tuple[bool, bool]] = []
    window = tkfacade.Window(title="host", root=root)
    _RecordingSurface(window, observations).grid(row=0, column=0)

    root.destroy()

    assert observations == [(True, True)]


def test_window_destruction_tears_its_surfaces_down_while_it_lives(root: Root) -> None:
    """``BaseWindow.destroy`` runs the surfaces under it down before the window dies.

    The per-window half of the ordering, and the half a Root-only fix would have left crashing: a titlebar close or a standalone ``win.destroy()`` frees the toplevel's native windows with no root teardown in sight — and on the last window the cascade only reaches the root afterwards — so the reactive binding used to fire there with the drawing frame already dead. A survivor window keeps the root alive through the destroy, which pins the teardown as this hook's work rather than the root cascade's; the assertion shape is the root test's.
    """
    observations: list[tuple[bool, bool]] = []
    survivor = tkfacade.Window(title="survivor", root=root)
    doomed = tkfacade.Window(title="doomed", root=root)
    _RecordingSurface(doomed, observations).grid(row=0, column=0)

    doomed.destroy()

    assert observations == [(True, True)]
    assert not root.destroyed
    assert root.windows == (survivor,)


def test_a_dead_interpreter_is_released_only_from_the_main_thread(root: Root) -> None:
    """A destroyed root is pinned; a worker flush is a no-op; a main-thread flush frees it.

    _tkinter deallocates an interpreter with Tcl_AsyncDelete, which panics — a whole-process abort, no exception to catch — when it runs on any thread but the interpreter's own; and since every widget tree is a master↔children reference cycle, a dead root used to reach that dealloc through whichever thread's allocation happened to trigger cycle collection (an mpv event thread, reproducibly, once the suite grew enough). The abort itself cannot be staged in a test that survives, so the guard is pinned piecewise: retirement into the pin at destroy, the worker flush refusing (that refusal *is* the fix — the identity read after join answers it), and the next main-thread interpreter moment releasing the pin. get_root is that moment here, and the fixture teardown reaps the replacement root it makes.
    """
    app = root._tk.tk
    root.destroy()
    assert any(entry is app for entry in _root_module._retired_apps)

    worker = threading.Thread(target=_root_module._flush_retired)
    worker.start()
    worker.join(timeout=2)
    assert any(entry is app for entry in _root_module._retired_apps)

    get_root()

    assert _root_module._retired_apps == []


def test_a_worker_cannot_create_the_interpreter(root: Root) -> None:
    """Off-main construction is refused, and the main thread heals afterwards.

    tk.Tk() binds the Tcl interpreter to whichever thread creates it, and nothing enforced the main-thread moment the code assumed — so a worker's first-touch get_root() built the shared interpreter on the worker and poisoned it for the process: every main-thread call raised "main thread is not in main loop", and the self-heal path could not even ask destroyed without raising too, unrecoverably. Construction now refuses off-main with an error naming the real problem. The root is destroyed first so the worker's get_root takes the construction branch off the flag alone — a live-root probe from a worker parks on the main thread unless a mainloop is running, which is the running-loop test's territory, not this one's. The final main-thread get_root is the poison refuted: the shared root heals where it used to be lost for good.
    """
    answers: list[object] = []
    root.destroy()

    def construct() -> None:
        try:
            answers.append(get_root())
        except RuntimeError as error:
            answers.append(error)

    builder = threading.Thread(target=construct, name="builder")
    builder.start()
    builder.join(timeout=2)

    assert len(answers) == 1
    assert isinstance(answers[0], RuntimeError)

    healed = get_root()

    assert not healed.destroyed


def test_a_callback_raise_routes_to_the_error_handler(root: Root) -> None:
    """A raise inside a command callback reaches the handler as the exception instance.

    The error hook, exercised through a real library route rather than by calling the router directly: the menu command's raise travels Tk's whole swallow-and-report path (CallWrapper, Misc._report_exception, the interpreter's report_callback_exception) and must land in the application's handler as the exception instance itself -- identity, not a re-raise or a string. invoke() returning at all is half the contract: the operation that triggered the callback completes. The root surviving is the other half.
    """
    window = tkfacade.Window(title="hook")
    caught: list[BaseException] = []
    root.callback_error_handler = caught.append
    boom = RuntimeError("command boom")

    def bad() -> None:
        raise boom

    menu = tkfacade.Menubutton(window, "File")
    entry = menu.insert_command("Boom", command=bad)
    entry.invoke()

    assert caught == [boom]
    assert not root.destroyed
    window.destroy()


def test_without_a_handler_the_default_prints_and_the_loop_survives(
    root: Root, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no handler set, a callback raise prints Tk's report to stderr.

    What "Defaults to None" is worth: the hook's default must be Tk's own print-and-continue, byte-compatible enough that an application that never touches the handler sees exactly what tkinter always showed. The assertion pins the two load-bearing fragments -- tkinter's banner line and the raise's own message -- rather than the whole traceback, whose frames shift with interpreter versions.
    """
    window = tkfacade.Window(title="default")
    # the root fixture guards the seam with a collector; the no-handler
    # default under test is reached by clearing it, which is also what
    # tells the guard this test owns the seam
    root.callback_error_handler = None

    def bad() -> None:
        raise RuntimeError("default boom")

    menu = tkfacade.Menubutton(window, "File")
    menu.insert_command("Boom", command=bad).invoke()

    stderr = capsys.readouterr().err
    assert "Exception in Tkinter callback" in stderr
    assert "default boom" in stderr
    assert not root.destroyed
    window.destroy()


def test_assigning_none_restores_the_default(
    root: Root, capsys: pytest.CaptureFixture[str]
) -> None:
    """Clearing the handler sends the next raise back to Tk's own report.

    The setter's None half: the property docstring promises that assigning None restores the default, and a handler that kept receiving reports after being cleared would hold the application's error routing hostage to registration order. The earlier assignment is deliberate -- the test walks the full set-then-clear path rather than clearing a never-set handler, which would pass vacuously.
    """
    window = tkfacade.Window(title="restore")
    caught: list[BaseException] = []
    root.callback_error_handler = caught.append
    root.callback_error_handler = None

    def bad() -> None:
        raise RuntimeError("restored boom")

    menu = tkfacade.Menubutton(window, "File")
    menu.insert_command("Boom", command=bad).invoke()

    assert caught == []
    assert "restored boom" in capsys.readouterr().err
    window.destroy()


def test_a_raising_handler_falls_back_to_stderr(
    root: Root, capsys: pytest.CaptureFixture[str]
) -> None:
    """A handler that raises gets both tracebacks printed; nothing propagates.

    The hook's own failure mode: a raise inside the handler cannot be routed through the handler, so the router's last resort is stderr, and it must surface both exceptions -- swallowing the original in favor of the handler's would hide the actual application bug behind its reporter's. invoke() returning and the root surviving pin that the fallback never lets either raise escape into the callback machinery, where it would abort the Tcl callback mid-flight.
    """
    window = tkfacade.Window(title="fallback")

    def terrible(_exc: BaseException) -> None:
        raise ValueError("handler boom")

    root.callback_error_handler = terrible

    def bad() -> None:
        raise RuntimeError("original boom")

    menu = tkfacade.Menubutton(window, "File")
    menu.insert_command("Boom", command=bad).invoke()

    stderr = capsys.readouterr().err
    assert "original boom" in stderr
    assert "handler boom" in stderr
    assert not root.destroyed
    window.destroy()
