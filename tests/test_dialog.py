"""The Dialog foundation: shown, modal, completed once, two result doors.

The rulings pinned (2026-08-28): the dialog owns and encapsulates its
window — nothing public answers it; every dismissal spelling — cancel,
Escape, the close protocol, outright destruction — answers None, with
completion always preceding the window's death; the first completion
stands and later ones do nothing; the sync door genuinely parks its
caller while the application keeps pumping; and the async door rides
the core with the chord's crossing discipline. The concrete dialog
driving all of it is ephemeral and lives here, outside the library,
as ruled.
"""

import time

import pytest

import tkfacade
from conftest import Pump
from tkfacade.window import Root

pytestmark = pytest.mark.gui


class WordDialog(tkfacade.Dialog[str]):
    """An ephemeral test dialog: one word offered, taken or declined."""

    def __init__(self, parent: tkfacade.Window, word: str = "yes") -> None:
        super().__init__(parent, title="word?", width=240, height=120)
        self._word = word
        self.ok = tkfacade.Button(self._window, "OK", command=lambda: self.complete(self._word))
        self.ok.grid(row=0, column=0)
        self.no = tkfacade.Button(self._window, "Cancel", command=self.cancel)
        self.no.grid(row=0, column=1)


def test_show_takes_the_grab_and_completion_frees_everything(
    window: tkfacade.Window, pump: Pump
) -> None:
    """Posting grabs; completing resolves first, then the window dies."""
    box = WordDialog(window)
    assert not box.done
    box.show()
    pump(window)

    assert box._window._tk.winfo_viewable()
    # the grab read through Tcl's own string channel: typeshed leaves
    # grab_current untyped (strict mypy refuses the call), and raw
    # tk.call answers window *objects* — the probe README's trap
    assert window._tk.tk.eval("grab current") == str(box._window._tk)

    box.ok.invoke()
    pump(window)

    # typed locals through here: mypy narrows the `box.done` member
    # expression itself, so the line-42 assert would otherwise pin it
    # Literal[False] and mark everything after this assert unreachable
    settled: bool = box.done
    assert settled
    answer = box.result()
    assert answer == "yes"
    assert not box._window._tk.winfo_exists()
    assert window._tk.tk.eval("grab current") == ""
    assert repr(box).endswith("done>")


def test_the_dialog_answers_no_window_publicly(window: tkfacade.Window, pump: Pump) -> None:
    """Encapsulation as ruled: no public member hands the window out."""
    box = WordDialog(window)
    public = [name for name in dir(box) if not name.startswith("_")]

    assert "window" not in public
    assert all(not isinstance(getattr(box, name), tkfacade.Window) for name in public)
    box.cancel()


def test_the_sync_door_parks_and_resumes_with_the_answer(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``result()`` blocks its caller while events keep pumping.

    The probe's nested-loop fact, on the library's own surface: the caller's frame stood still through the wait — the driving `after` fired *during* it — and resumed the moment completion landed.
    """
    box = WordDialog(window, "parked")
    marks: list[str] = []

    def drive() -> None:
        marks.append("driven")
        box.ok.invoke()

    window._tk.after(150, drive)
    marks.append("before")
    answer = box.result()
    marks.append("resumed")

    assert marks == ["before", "driven", "resumed"]
    assert answer == "parked"


def test_every_dismissal_spelling_answers_none(window: tkfacade.Window, pump: Pump) -> None:
    """Cancel, Escape, the close protocol, and destruction all read as None.

    The last case is completion bound to destruction: even a window torn down out from under the dialog resolves the future — the probe's teardown property, preserved by design rather than inherited.
    """
    cancelled = WordDialog(window)
    cancelled.show()
    cancelled.no.invoke()
    assert cancelled.done
    assert cancelled.result() is None

    escaped = WordDialog(window)
    escaped.show()
    pump(window)
    escaped._window._tk.event_generate("<Escape>")
    pump(window)
    assert escaped.done
    assert escaped.result() is None

    destroyed = WordDialog(window)
    destroyed.show()
    pump(window)
    destroyed._window._tk.destroy()
    pump(window)
    assert destroyed.done
    assert destroyed.result() is None


def test_the_first_completion_stands(window: tkfacade.Window, pump: Pump) -> None:
    """Completing twice is not an error; the second answer is dropped."""
    box = WordDialog(window)
    box.complete("first")
    box.complete("second")
    box.cancel()

    assert box.result() == "first"


def test_the_async_door_lands_on_the_core(window: tkfacade.Window, pump: Pump, root: Root) -> None:
    """A coroutine awaits the completion across the thread wall."""
    box = WordDialog(window, "async")
    box.show()
    pump(window)
    landed: list[str | None] = []

    async def macro(_value: bool) -> None:
        landed.append(await box.wait())

    starter = tkfacade.ObservableBool(False)
    starter.transport_for(window._tk)  # a coroutine watcher needs the interpreter
    subscription = starter.watch(macro)
    deadline = time.monotonic() + 3.0
    driven = False
    while time.monotonic() < deadline and not landed:
        pump(window)
        if not driven and box._waiters:
            # complete only once the waiter is parked, or the resolve
            # answers an empty list and nothing ever lands
            box.ok.invoke()
            driven = True
        time.sleep(0.01)

    assert landed == ["async"]
    subscription.cancel()
    starter.release_transport()
