""":class:`~tkfacade.Button`: the command in widget form, both command kinds.

The first widget, and the first public proof of the command
story: a plain callable runs on the mainloop, a coroutine function
runs on the root's core, and both report their raises to the same
hook. Everything needs a live widget, so the suite rides the
``window`` fixture under the ``gui`` marker; the async legs run the
real mainloop through the shared ``run_mainloop`` fixture, per the
thread wall.
"""

import asyncio
import threading

import pytest

import tkfacade
from conftest import RunMainloop
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def test_construction_options_round_trip(window: tkfacade.Window) -> None:
    """text, enabled, and width land at construction and read back live.

    The state surface read live from Tk: text through cget, enabled through the state flags, both after construction and after assignment. The width is read raw off the widget because the wrapper deliberately offers no width property yet — the option is construction-time sizing, and a property would promise live resizing this test has not earned.
    """
    plain = tkfacade.Button(window, "Save")
    sized = tkfacade.Button(window, "Cancel", enabled=False, width=12)

    assert plain.text == "Save"
    assert plain.enabled is True
    assert sized.enabled is False
    assert str(sized._tk.cget("width")) == "12"

    plain.text = "Save As"
    sized.enabled = True

    assert plain.text == "Save As"
    assert sized.enabled is True


def test_invoke_runs_the_command_and_a_disabled_button_does_nothing(
    window: tkfacade.Window,
) -> None:
    """invoke runs the command while enabled and nothing while disabled.

    The disabled leg was drafted expecting ttk's raw invoke to run the command regardless of state, and the witness refuted it: on this floor ttk honors disabled itself, which is why the wrapper carries no second guard. The raw call stays beside the facade's as the pin — a build where ttk stops honoring the state fails here first, and the no-guard decision gets revisited on evidence. The commandless button's invoke closes the None branch: activating into nothing is quiet, not an error.
    """
    ran: list[str] = []
    button = tkfacade.Button(window, "Go", command=lambda: ran.append("ran"))

    button.invoke()
    assert ran == ["ran"]

    button.enabled = False
    button._tk.invoke()
    button.invoke()
    assert ran == ["ran"]

    tkfacade.Button(window, "Idle").invoke()


def test_the_command_property_swaps_what_activation_runs(window: tkfacade.Window) -> None:
    """Assigning command changes future activations; None deactivates.

    The runtime half of the command story: the wrapper holds the command itself and hands Tk one stable dispatcher, so swapping never touches the widget's -command option and the property reads back exactly what was assigned — including the None that turns activation into nothing while the button stays enabled and clickable.
    """
    ran: list[str] = []
    button = tkfacade.Button(window, "Go", command=lambda: ran.append("first"))

    button.invoke()
    button.command = lambda: ran.append("second")
    button.invoke()
    button.command = None
    button.invoke()

    assert ran == ["first", "second"]
    assert button.command is None


def test_a_click_activates_through_the_users_route(window: tkfacade.Window) -> None:
    """A generated press-and-release on the button runs the command.

    invoke() exercises the command seam from the program's side; this is the user's side — ttk runs the command on the release of a press that began on the button, so both halves are generated, at coordinates inside the widget, after an update has realized it (the witnessed window-creation boundary). One activation, one run.
    """
    ran: list[str] = []
    button = tkfacade.Button(window, "Go", command=lambda: ran.append("clicked"))
    button.grid(row=0, column=0)
    window._tk.update()

    button._tk.event_generate("<Button-1>", x=2, y=2)
    button._tk.event_generate("<ButtonRelease-1>", x=2, y=2)
    window._tk.update()

    assert ran == ["clicked"]


def test_a_raising_sync_command_reaches_the_hook(root: Root, window: tkfacade.Window) -> None:
    """A plain command's raise is swallowed by Tk and routed to the hook.

    Fire-and-forget on the command route: invoke returns normally — the witnessed behavior for every -command raise — and the raise lands in the interpreter's hook, which the Root routes to the application's handler. Nothing here is the wrapper's own code: the pin is that the wrapper did not accidentally interpose a layer that eats or reroutes what Tk already handles right.
    """
    hooked: list[BaseException] = []
    root.callback_error_handler = hooked.append

    def bad() -> None:
        raise ValueError("sync boom")

    button = tkfacade.Button(window, "Go", command=bad)
    button.invoke()

    assert len(hooked) == 1
    assert isinstance(hooked[0], ValueError)


def test_a_coroutine_command_runs_on_the_core(
    window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """A coroutine function as command is scheduled off-thread per activation.

    The birthright the async gate existed to arrange: the same command parameter takes a coroutine function with no second spelling, and activation schedules it on the root's core — off the mainloop, fire-and-forget, invoke returning at once. The invoke is scheduled into the running mainloop because the scheduling itself resolves the core and the run crosses threads, which the wall only permits while the main thread is genuinely in Tk's loop.
    """
    main = threading.get_ident()
    ran_on: list[int] = []
    done = threading.Event()

    async def command() -> None:
        await asyncio.sleep(0)
        ran_on.append(threading.get_ident())
        done.set()

    button = tkfacade.Button(window, "Fetch", command=command)
    button.grid(row=0, column=0)
    window._tk.after(0, button.invoke)
    run_mainloop(window, done)

    assert len(ran_on) == 1
    assert ran_on[0] != main


def test_a_raising_coroutine_command_reaches_the_hook(
    root: Root, window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """The async command's raise is retrieved and routed to the same hook.

    One hook for both command kinds: the sync raise arrives through Tk's own report seam, the async raise through the facade's retrieval, and an application that registered a handler for one gets the other for free — the no-new-category ruling, proven on the first widget whose command story was born after it.
    """
    hooked: list[BaseException] = []
    done = threading.Event()

    def hook(exc: BaseException) -> None:
        hooked.append(exc)
        done.set()

    root.callback_error_handler = hook

    async def bad() -> None:
        await asyncio.sleep(0)
        raise ValueError("async boom")

    button = tkfacade.Button(window, "Fetch", command=bad)
    button.grid(row=0, column=0)
    window._tk.after(0, button.invoke)
    run_mainloop(window, done)

    assert len(hooked) == 1
    assert isinstance(hooked[0], ValueError)
    assert str(hooked[0]) == "async boom"


def test_a_command_that_completes_a_dialog_activates_without_error(
    root: Root, window: tkfacade.Window
) -> None:
    """A button whose command destroys it invokes cleanly and emits to nobody.

    The witnessed defect this pins closed: Dialog.complete destroys the dialog's window mid-activation, and the ACTIVATED emission that follows the command used to event_generate on the dead button — TclError, swallowed to the interpreter's seam, invisible to a suite that never watched it. The handler is hooked explicitly rather than left to the conftest guard so the assertion is the test's own, and the ACTIVATED observer pins the ruled other half: a widget destroyed by its own command emits into silence, delivering to nobody — the empty `heard` is the contract, not a gap.
    """
    hooked: list[BaseException] = []
    root.callback_error_handler = hooked.append

    class Closing(tkfacade.Dialog[bool]):
        """An ephemeral dialog: one button, completing — and so destroying — it."""

        def __init__(self, parent: tkfacade.Window) -> None:
            super().__init__(parent, title="closing", width=200, height=100)
            self.ok = tkfacade.Button(self._window, "OK", command=lambda: self.complete(True))
            self.ok.grid(row=0, column=0)

    box = Closing(window)
    box.show()
    heard: list[object] = []
    box.ok.bind(tkfacade.ACTIVATED, heard.append)

    box.ok.invoke()
    window._tk.update()

    assert box.result() is True
    assert hooked == []
    assert heard == []


def test_a_command_that_destroys_the_button_directly_stays_silent(
    root: Root, window: tkfacade.Window
) -> None:
    """A command destroying its own button runs once and reports nothing.

    The same defect without the dialog machinery: a callback may destroy what called it, so the bare shape — the command reaching for its own widget's destroy — must survive on any wrapper, not only under a dialog's teardown cascade. Kept separate from the dialog-shaped pin because the two destroy different things (the widget itself against the window over it) and a regression could split them.
    """
    hooked: list[BaseException] = []
    root.callback_error_handler = hooked.append
    ran: list[str] = []

    button = tkfacade.Button(window, "Self-destruct")

    def vanish() -> None:
        ran.append("ran")
        button.destroy()

    button.command = vanish
    button.grid(row=0, column=0)
    window._tk.update()
    button.invoke()

    assert ran == ["ran"]
    assert hooked == []
    assert not button._tk.winfo_exists()
