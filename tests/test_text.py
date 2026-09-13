"""The text inputs, their shared contract, and what each adds to it.

:class:`~tkfacade.TextBox`, :class:`~tkfacade.Entry`, and
:class:`~tkfacade.TitleEntry` all implement
:class:`~tkfacade.AbstractTextInterface` — a text input whose read-only
mode locks out the user and leaves the program alone — by different
routes: a ``tk.Text`` held at ``state="disabled"`` with the state
lifted around every write, a ``ttk.Entry`` in ttk's ``readonly`` state
fed through a :class:`tkinter.StringVar`, and that same entry mechanism
beside a title label inside a frame. What the contract declares is
parametrized across all three; what each implementation writes for
itself is tested against that class alone — the box's phantom newline,
the entry's mask and cursor, the titled entry's
:class:`~tkfacade.text.TitleEntryTitle` view, arrangement, and
two-variable parking.

Half the contract is unreachable through the Python API — a promise
that the *user* cannot edit is only worth what a keystroke says — so
this module does what the rest of the suite has not needed to and
delivers real key events to a focused widget. Everything needs a live
Tk widget, so the suite rides the ``window`` fixture under the ``gui``
marker.
"""

import gc
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

import pytest

import tkfacade
from tkfacade.widget import BaseWidget

pytestmark = pytest.mark.gui

type Build = Callable[..., tkfacade.AbstractTextInterface]

BUILDS = pytest.mark.parametrize(
    "build",
    (tkfacade.TextBox, tkfacade.Entry, tkfacade.TitleEntry),
    ids=("box", "entry", "titled"),
)
"""All three implementations, applied to every test of the shared contract."""

EDITING_KEYS = (
    "<KeyPress-a>",
    "<Return>",
    "<Tab>",
    "<Delete>",
    "<BackSpace>",
    "<Control-d>",
    "<Control-k>",
    "<Control-o>",
    "<Control-t>",
    "<Control-i>",
    "<Insert>",
    "<<Cut>>",
    "<<Paste>>",
    "<<Clear>>",
    "<<Undo>>",
    "<<Redo>>",
    "<<PasteSelection>>",
)
"""Every sequence Tk binds to an edit on a text widget or an entry."""


def _focusable(field: tkfacade.AbstractTextInterface) -> tk.Misc:
    """Return the widget Tk hands the keyboard focus to.

    The contract hides an asymmetry the keyboard does not: an entry is
    itself the widget that takes focus, while a box is a frame whose
    inner text widget takes it and a titled entry is a frame holding
    the entry beside its label. All are reached past the public API
    because no public member names the widget a user actually types
    into.

    Args:
        field (tkfacade.AbstractTextInterface): The input to look inside.

    Returns:
        The Tk widget that receives keystrokes.
    """
    if isinstance(field, tkfacade.TextBox):
        return field._text
    if isinstance(field, tkfacade.TitleEntry):
        return field._entry
    return field._tk


def _press(field: tkfacade.AbstractTextInterface, *sequences: str) -> None:
    """Deliver each sequence to ``field`` as a real keystroke.

    Focus is forced first: an unfocused widget is sent nothing, and
    every assertion about a refusal would then hold vacuously. Events
    are queued with ``when="tail"`` and delivered by the update, which
    is the path a typed key takes.

    Args:
        field (tkfacade.AbstractTextInterface): The input to type into.
        *sequences (str): Tk event sequences, in the order to send them.
    """
    target = _focusable(field)
    target.update()
    target.focus_force()
    target.update()
    for sequence in sequences:
        target.event_generate(sequence, when="tail")
    target.update()


@BUILDS
def test_a_programmatic_write_lands_and_leaves_the_mode_alone(
    build: Build, window: tkfacade.Window
) -> None:
    """Assigning ``text`` replaces the content read-only or not, and the mode survives.

    The half of the contract the Python API can reach: read-only binds the user, not the program. Both modes are written to in one test because the interesting failure is asymmetric — the box lifts its disabled state to write and puts back what it found, so a restore that forgot would silently re-enable every read-only box on first write, while one that always disabled would lock every editable box instead. Neither shows unless both directions are asserted. The entry needs no lifting at all and is held to the same result, which is what makes this the contract's test rather than the box's.
    """
    locked = build(window, text="before", read_only=True)
    free = build(window, text="before")

    locked.text = "after"
    free.text = "after"

    assert (locked.text, locked.disabled) == ("after", True)
    assert (free.text, free.disabled) == ("after", False)


@BUILDS
def test_a_read_only_input_refuses_every_keyboard_edit(
    build: Build, window: tkfacade.Window
) -> None:
    """The whole editing repertoire, typed into a focused read-only input, changes nothing.

    The contract's headline half, and the only claim here that needs a real key event: every guard Tk applies reads the widget's state at the moment the binding fires, so nothing short of delivering the event proves the guard holds. The repertoire is the full set rather than a sample because the bindings do not share one guard — some test the state in Tcl, the rest are refused by the widget command underneath them — so a sample would leave whole families unasserted. The clipboard is seeded so <<Paste>> has something to fail to paste with. Focus is asserted at the end because without it the keys would go nowhere and the whole test would pass vacuously; the editable companion below is what proves the delivery itself works.
    """
    field = build(window, text="untouched", read_only=True)
    field.grid(row=0, column=0)
    field.tk.call("clipboard", "clear")
    field.tk.call("clipboard", "append", "pasted")
    target = _focusable(field)

    _press(field, *EDITING_KEYS)

    assert field.text == "untouched"
    assert target.focus_get() is target


@BUILDS
def test_an_editable_input_takes_the_keystroke_read_only_refuses(
    build: Build, window: tkfacade.Window
) -> None:
    """The same delivery that changes nothing while read-only types into an editable input.

    The guard the refusal test leans on. That test's assertion is a negative — content unchanged — which an event_generate delivering nothing at all would satisfy just as well, so a helper quietly broken by a Tk or platform change would turn every refusal green forever. This is the same helper, the same widget and the same sequence with read-only lifted, and the two together say the keys arrive and that the mode is what stops them.
    """
    field = build(window, text="")
    field.grid(row=0, column=0)

    _press(field, "<KeyPress-a>")

    assert field.text == "a"


@BUILDS
def test_a_read_only_input_stays_in_focus_traversal(build: Build, window: tkfacade.Window) -> None:
    """Tab order reaches a read-only input rather than skipping past it.

    What ``takefocus=True`` is for on the box, and what ttk's readonly state gives the entry for free. Traversal is the assertion rather than focus_force, which bypasses the tab order outright and would pass on a widget traversal skips: a bare disabled tk.Text leaves takefocus at "" and is skipped, which is exactly what dropping the option would reintroduce. An input traversal skipped would be reachable by mouse and never selectable or copyable from the keyboard — the whole reason the contract promises focus at all.
    """
    anchor = tkfacade.Entry(window, text="anchor")
    anchor.grid(row=0, column=0)
    field = build(window, text="reachable", read_only=True)
    field.grid(row=1, column=0)
    _focusable(anchor).update()

    assert _focusable(anchor).tk_focusNext() is _focusable(field)


@BUILDS
def test_a_read_only_input_still_selects_and_copies(build: Build, window: tkfacade.Window) -> None:
    """Selecting and copying work while read-only, all the way to the clipboard.

    The other side of the refusal test: read-only takes away editing and nothing else. It is followed through to the clipboard rather than stopping at the return value, because copy_selection reporting what it meant to copy is not the same as the text being there to paste, and the clipboard is the only place the user meets the result. The input is read-only throughout, which is the state the claim is about. This is the program's route; the user's own is below.
    """
    field = build(window, text="quotable", read_only=True)
    field.grid(row=0, column=0)
    field.tk.call("clipboard", "clear")

    field.select_all()

    assert field.selection == "quotable"
    assert field.copy_selection() == "quotable"
    assert field.tk.call("clipboard", "get") == "quotable"


@BUILDS
def test_a_read_only_input_lets_the_user_select_and_copy(
    build: Build, window: tkfacade.Window
) -> None:
    """A user's own select-all and copy carry content out of a read-only input.

    The promise the contract makes about the user specifically, and the reason read-only is not simply Tk's disabled state: what is taken away is editing, so the bindings that only read have to keep working. Nothing but a real event tests them — these are Tk's own virtual events, dispatched through the same bindings a Ctrl+A and Ctrl+C arrive on. The assertions are prefix rather than exact because the two implementations genuinely disagree by one character here: Tk's select-all on a text box takes the phantom trailing newline its entry has no equivalent of. That difference is Tk's binding rather than anything either wrapper does, so it is pinned exactly in the box's own test below rather than smoothed over here.
    """
    field = build(window, text="content", read_only=True)
    field.grid(row=0, column=0)
    field.tk.call("clipboard", "clear")
    field.tk.call("clipboard", "append", "precious")

    _press(field, "<<SelectAll>>", "<<Copy>>")

    assert field.selection.startswith("content")
    assert str(field.tk.call("clipboard", "get")).startswith("content")


@BUILDS
def test_disable_and_enable_round_trip_leaves_content_alone(
    build: Build, window: tkfacade.Window
) -> None:
    """``disable`` and ``enable`` flip ``disabled`` and never touch content.

    Both transitions in one pass because their contract is symmetric — "the content is left alone" — and the closing read covers the whole cycle. Neither implementation keeps a wrapper flag: the box reads a state string back from Tk and the entry reads ttk's state flags, which are different enough mechanisms that holding both to one table is worth the parametrize. The reads land in locals because mypy narrows a repeated property expression and would call the later asserts unreachable.
    """
    field = build(window, text="kept")

    before = field.disabled
    field.disable()
    during = field.disabled
    field.enable()
    after = field.disabled

    assert (before, during, after) == (False, True, False)
    assert field.text == "kept"


@BUILDS
def test_is_empty_tracks_content(build: Build, window: tkfacade.Window) -> None:
    """A fresh input is empty; written text clears the flag; blanking restores it.

    The blank-again step is what proves emptiness is recomputed rather than remembered from construction. It also catches the box's own trap: Tk's text widget keeps a trailing newline of its own, so an is_empty reading to "end" instead of "end-1c" would answer False for a fresh box and the property would be constant — vacuously useless. The entry has no such phantom and is held to the same table, which is what makes this the contract's test. Locals again for mypy's property narrowing.
    """
    field = build(window)

    fresh = field.is_empty
    field.text = "something"
    filled = field.is_empty
    field.text = ""
    blanked = field.is_empty

    assert (fresh, filled, blanked) == (True, False, True)


@BUILDS
def test_selection_reads_empty_when_nothing_is_selected(
    build: Build, window: tkfacade.Window
) -> None:
    """``selection`` answers ``""`` with no selection, and the text after one.

    Neither implementation gets "" for free, and they do not get it the same way. Tk raises TclError for the box's absent "sel" range, and a suppress is what turns that into ""; the entry has to avoid selection_get(), which reads the X PRIMARY selection and would answer with some sibling widget's text on an entry that has nothing selected at all. The full cycle — none, all, none again — is what proves select_none clears, since its no-op-when-empty contract leaves a do-nothing implementation otherwise indistinguishable.
    """
    field = build(window, text="pick me")

    assert field.selection == ""
    field.select_all()
    assert field.selection == "pick me"
    field.select_none()
    assert field.selection == ""


@BUILDS
def test_copy_selection_leaves_the_clipboard_alone_when_empty(
    build: Build, window: tkfacade.Window
) -> None:
    """Copying with no selection returns ``""`` and preserves the clipboard.

    The documented guard: an empty copy must not clear the clipboard, because clipboard_clear-then-append-nothing is precisely what the obvious implementation does, destroying whatever the user had. The read-only input doubles as the "works while read-only, since copying only reads" claim. Clipboard state is read and seeded through the public ``tk`` interpreter handle — the clipboard is interpreter-global, not a private detail of either input.
    """
    field = build(window, text="content", read_only=True)
    field.tk.call("clipboard", "clear")
    field.tk.call("clipboard", "append", "precious")

    assert field.copy_selection() == ""
    assert field.tk.call("clipboard", "get") == "precious"

    field.select_all()
    assert field.copy_selection() == "content"
    assert field.tk.call("clipboard", "get") == "content"


def test_a_text_box_strips_tks_trailing_newline(window: tkfacade.Window) -> None:
    """The content reads back exactly as written, without Tk's newline.

    Tk's text widget always keeps a trailing newline of its own, so a naive get("1.0", "end") answers "line\n" — the end-1c index is the whole fix, and it is the box's alone, since an entry has no such phantom. Exact equality is the only honest assertion; an in-test strip would hide the regression.
    """
    box = tkfacade.TextBox(window, text="line")

    assert box.text == "line"


def test_a_text_box_keeps_a_newline_the_caller_wrote(window: tkfacade.Window) -> None:
    """Assigned newlines start new lines, including one at the very end.

    The multi-line half of what makes a box not an entry, on the content the end-1c index is easiest to get wrong: text ending in a real newline leaves the widget holding two, and the fix has to strip Tk's while keeping the author's. Off by one either way and this is the shape that shows it — the case above passes whether the index is end-1c or end-2c. Written through the read-only path because that is the path a caller uses on a box they mean nobody to type into.
    """
    box = tkfacade.TextBox(window, text="", read_only=True)

    box.text = "first\nsecond\n"

    assert box.text == "first\nsecond\n"


def test_a_text_box_carries_and_wires_only_the_scrollbars_it_was_asked_for(
    window: tkfacade.Window,
) -> None:
    """A box builds exactly the scrollbars it was given, and connects each to a view.

    Counting the children says a scrollbar was built; reading the view commands off the text widget says it was connected, and a bar that was gridded but never wired is the failure the count alone cannot see. The horizontal bar is the one worth the second box: it is off by default, it is the only one whose usefulness depends on another option — nothing scrolls sideways unless both wraps are False — and it was the sole path through this constructor that no test entered. The children are reached through the public mapping the wrapper already proxies, so only the view commands go through the helper.
    """
    bare = tkfacade.TextBox(window, vertical_scrollbar=False)
    both = tkfacade.TextBox(window, horizontal_scrollbar=True)

    assert sorted(child.winfo_class() for child in bare.children.values()) == ["Text"]
    assert sorted(child.winfo_class() for child in both.children.values()) == [
        "TScrollbar",
        "TScrollbar",
        "Text",
    ]
    assert str(_focusable(bare).cget("yscrollcommand")) == ""
    assert str(_focusable(both).cget("xscrollcommand")) != ""


def test_a_user_select_all_in_a_text_box_takes_tks_trailing_newline(
    window: tkfacade.Window,
) -> None:
    """The user's select-all reaches Tk's phantom newline where ``select_all`` stops short.

    Tk's select-all binding runs to "end" while the wrapper's runs to "end-1c", so the user and the program disagree by exactly the phantom newline — a box whose whole content is selected two different ways gives two different answers. Nothing here is the wrapper's doing and nothing is being asserted as desirable: the divergence is Tk's, it is real, and pinning it is what stops the looser prefix assertion in the shared user-route test from being mistaken for the two implementations agreeing. Both readings are taken in one test because the claim is the difference between them, and locals carry them past mypy's property narrowing.
    """
    box = tkfacade.TextBox(window, text="content", read_only=True)
    box.grid(row=0, column=0)

    _press(box, "<<SelectAll>>")
    user = box.selection
    box.select_none()
    box.select_all()
    programmatic = box.selection

    assert (user, programmatic) == ("content\n", "content")


def test_an_entry_write_reaches_the_shared_observable(window: tkfacade.Window) -> None:
    """Assignments and observable writes both land, and both reach a watcher.

    The documented hook, spoken in the facade's own vocabulary since the conversion: every change to the content passes through the observable, "typed or assigned", so a watcher sees both. Only the assigned half is reachable without a keyboard, so the second write drives the observable directly — and the raw ttk get() asserts the widget followed it through the transport, which is the drive-and-follow contract check landing on the first converted wrapper. The entry is read-only throughout, the point carried over from the variable era: the transport is why an entry needs no state lifting to be written to. The leading "start" is the watch contract's ruled immediate first call, asserted rather than skipped past.
    """
    entry = tkfacade.Entry(window, text="start", read_only=True)
    observable = entry.text_observable
    seen: list[str] = []
    observable.watch(seen.append)

    entry.text = "assigned"
    observable.value = "driven"

    assert entry.text == "driven"
    assert str(entry._tk.get()) == "driven"
    assert seen == ["start", "assigned", "driven"]


def test_an_entry_observable_outlives_a_dropped_wrapper(window: tkfacade.Window) -> None:
    """Content and watchers survive the last wrapper reference going away.

    The parking test, carried across the conversion: what is parked on the ttk entry is now the observable, and everything downstream of it — the transport variable, the held value, the watch list — must ride the widget's lifetime rather than the wrapper's. The watcher closes over nothing but its own list for the same reason as ever: the observable holds it, so a closure that mentioned the observable would anchor it by itself and the test would pass with the parking line deleted. The transport's Tcl name is read off the widget's own -textvariable option because the observable's internals are not this test's business. The closing GUI-path insert proves the whole pipeline — widget, transport, observable, watcher — still runs with the wrapper gone, and the exact list pins the immediate first call beside it.
    """
    fired: list[str] = []

    def build() -> tuple[str, ttk.Entry]:
        entry = tkfacade.Entry(window, text="kept")
        entry.grid(row=0, column=0)
        entry.text_observable.watch(fired.append)
        return str(entry._tk.cget("textvariable")), entry._tk

    name, tk_entry = build()
    # the wrapper registry is a second and stronger anchor than the one
    # under test: it holds every live wrapper, so dropping the caller's
    # reference no longer drops the wrapper and the parking line would go
    # unexercised. Released here so the wrapper really is unreferenced.
    BaseWidget._wrappers.pop((tk_entry.tk, str(tk_entry)), None)
    gc.collect()
    tk_entry.update()

    assert bool(int(tk_entry.tk.call("info", "exists", name)))
    assert tk_entry.get() == "kept"
    tk_entry.insert(0, "x")
    tk_entry.update()
    assert fired == ["kept", "xkept"]


def test_a_titled_entrys_observables_outlive_a_dropped_wrapper(window: tkfacade.Window) -> None:
    """Displayed title and content both survive the last wrapper reference going away.

    TitleEntry carries its own copy of Entry's parking with two observables on the line instead of one, and the title is the half that visibly dies: a label whose -textvariable vanishes re-creates it from its own empty -text, where an entry re-creates it from its current content — so deleting the parking line while rearranging __init__ blanks only the title, and only in a program that drops its wrapper. The label's displayed -text is asserted because it is that visible casualty, Tk mirroring the transport into -text; the Tcl-level existence checks cover the content transport, whose visible half would survive the deletion and say nothing. The transports' Tcl names come off the widgets' own -textvariable options; watcher survival is the same mechanism the entry's test above pins and is not re-asserted here.
    """

    def build() -> tuple[str, str, ttk.Label, ttk.Entry, ttk.Frame]:
        titled = tkfacade.TitleEntry(window, title="kept title", text="kept text")
        titled.grid(row=0, column=0)
        return (
            str(titled._title_label.cget("textvariable")),
            str(titled._entry.cget("textvariable")),
            titled._title_label,
            titled._entry,
            titled._tk,
        )

    title_name, text_name, tk_label, tk_entry, tk_frame = build()
    # released for the same reason the entry test releases it: the registry
    # anchors the wrapper, and an anchored wrapper never exercises parking
    BaseWidget._wrappers.pop((tk_frame.tk, str(tk_frame)), None)
    gc.collect()
    tk_frame.update()

    assert bool(int(tk_frame.tk.call("info", "exists", title_name)))
    assert bool(int(tk_frame.tk.call("info", "exists", text_name)))
    assert str(tk_label.cget("text")) == "kept title"
    assert tk_entry.get() == "kept text"


def test_an_entry_mask_hides_the_display_but_not_the_content(window: tkfacade.Window) -> None:
    """A masked entry still reports, selects and copies the real content.

    "Masking is display only" — every assertion here is one reading of that claim, because ``show`` changes what Tk draws and nothing else, and a wrapper that read the drawn characters back would answer "******" to all of them. selection is the one that could plausibly go either way, being computed from Tk's own sel indices rather than from the variable. The copy is followed to the clipboard because a mask leaking there is where it would actually cost something. The mask is set after construction rather than given to it so the setter is the member under test; the constructor's route is covered by the user-copy test below.
    """
    entry = tkfacade.Entry(window, text="secret", read_only=True)
    entry.grid(row=0, column=0)
    entry.tk.call("clipboard", "clear")

    entry.mask = "*"
    entry.select_all()

    assert entry.mask == "*"
    assert entry.text == "secret"
    assert entry.selection == "secret"
    assert entry.copy_selection() == "secret"
    assert entry.tk.call("clipboard", "get") == "secret"


def test_an_entry_justify_round_trips(window: tkfacade.Window) -> None:
    """``justify`` reads back what construction set, and what a later assignment sets.

    The getter carries a ``# type: ignore[return-value]``: it hands Tk's answer back as a Justify literal on the strength of Tk only ever answering with one of the three, which the type checker cannot see and no other test asserts. That claim is what this pins — a Tk returning "left " or "centre" would satisfy every annotation in the file and break the first caller to compare against the literal. Both routes in one pass because the option is the same one either way, and locals for mypy's property narrowing.
    """
    entry = tkfacade.Entry(window, text="aligned", justify="center")

    built = entry.justify
    entry.justify = "right"
    assigned = entry.justify

    assert (built, assigned) == ("center", "right")


def test_a_user_copy_from_a_masked_entry_takes_the_mask(window: tkfacade.Window) -> None:
    """The user's copy carries the mask characters; ``copy_selection`` carries the content.

    The masking claim from the user's side, where it is worth more than on the program's: Tk copies what it draws, so the secret never reaches the clipboard by any route the user has. Asserting the mask characters exactly is the point — an assertion that merely differed from "secret" would pass on an empty clipboard, and a mask that started leaking the real content is precisely the regression worth catching. The program's own copy is read in the same test because the contract is that these two disagree: the program is entitled to the content and the user is not.
    """
    entry = tkfacade.Entry(window, text="secret", read_only=True, mask="*")
    entry.grid(row=0, column=0)
    entry.tk.call("clipboard", "clear")

    _press(entry, "<<SelectAll>>", "<<Copy>>")
    user = str(entry.tk.call("clipboard", "get"))
    programmatic = entry.copy_selection()

    assert (user, programmatic) == ("******", "secret")


def test_an_entry_cursor_moves_while_read_only(window: tkfacade.Window) -> None:
    """The insertion cursor moves while read-only, and an index past the end clamps.

    Both documented claims in one pass: "movable while disabled", and "an index past the end lands at the end". The clamp is Tk's rather than the setter's, which is why it is worth pinning at all — nothing in the wrapper would change if a future Tk started raising or wrapping instead, and the docstring would quietly become wrong. The reads land in locals for mypy's property narrowing.
    """
    entry = tkfacade.Entry(window, text="abcdef", read_only=True)

    entry.cursor = 3
    moved = entry.cursor
    entry.cursor = 99
    clamped = entry.cursor

    assert (moved, clamped) == (3, 6)


def test_selection_and_cursor_survive_an_astral_character(window: tkfacade.Window) -> None:
    """Both entries answer Python-string indices on content holding an emoji.

    Tk's entry indices count Tcl's string unit, and that unit is not the same everywhere: Tcl 8.6 stores UTF-16 and spends two indices on the emoji, Tcl 9 stores codepoints and spends one. So the raw indices are read off the widget rather than written down — "end" is whatever this interpreter counts, and the trailing "bc" is its last two units on either — and they are read from Tk rather than from _astral_width, so the test does not lean on the conversion it is checking. The Tcl-level selection_range is exactly what a user's drag over "bc" produces; with no conversion at all the wrapper sliced the Python string with those raw indices and answered 'c' on Tcl 8.6, and with the conversion hardcoded to UTF-16 it answered 'b' on Tcl 9 — the same fault mirrored, which is why the unit is asked for rather than assumed. Both ways copy_selection put the truncation on the clipboard. The cursor round-trips prove the setter converts the other way: entry.cursor = 4 must land at the true end to read back 4, and titled.cursor = 2 — the index just past the emoji — is the one that lands mid-surrogate on a UTF-16 Tcl if the setter passes it raw. Both wrappers in one pass because each carries its own copy of the rewiring against its own inner widget — but strictly one after the other: exportselection is on by default, so the second widget's selection_range steals X PRIMARY and empties the first's selection. The conversion's own tables, both units enumerated, are tests/test_index_conversion.py; this test is what proves they are wired into the wrappers at all.
    """
    text = "a\U0001f600bc"
    entry = tkfacade.Entry(window, text=text)
    titled = tkfacade.TitleEntry(window, title="t", text=text)
    end = entry._tk.index("end")

    entry._tk.selection_range(end - 2, end)
    entry.cursor = 4
    selected = entry.selection
    copied = entry.copy_selection()
    landed = entry.cursor
    titled._entry.selection_range(end - 2, end)
    titled.cursor = 2

    assert (selected, copied, landed) == ("bc", "bc", 4)
    assert titled.selection == "bc"
    assert titled.cursor == 2


def test_select_all_replaces_a_user_select_all(window: tkfacade.Window) -> None:
    """After a user Ctrl+A, the wrapper's ``select_all`` selects exactly the content.

    select_all was a bare tag_add, which only unions — and the one region a union can differ from a replace in is the phantom trailing newline the user's own Ctrl+A selects (through "end", the divergence the user-route test pins). So after a user select-all the wrapper's call left that newline tagged: selection answered 'content\n' against a text of 'content', and copy_selection carried the stray line break to the clipboard. The user press comes first and nothing clears between — every other test calls select_none() in between, which is exactly the masking condition this test removes. Equality with text is the contract's own wording; the copy pins the clipboard cost.
    """
    box = tkfacade.TextBox(window, text="content")
    box.grid(row=0, column=0)

    _press(box, "<<SelectAll>>")
    box.select_all()

    assert box.selection == box.text
    assert box.copy_selection() == "content"


def test_a_title_write_reaches_every_entry_sharing_the_observable(
    window: tkfacade.Window,
) -> None:
    """``value`` reads the title back, and ``set`` lands on both twins and a watcher.

    The view's one trap, pinned from both ends. Its ``value`` and ``set`` could plausibly have been copied from a text label's own reading of its ``-text`` option — and on a label driven by -textvariable that is a one-way mirror: Tk copies the transport into -text and ignores a write back, so a copied ``set`` would silently do nothing and a copied ``value`` would still read right, hiding it. Two entries on one observable is what makes the failure visible in a single call: the second twin can only see the write if it went through the observable they share — the constructor's observable form doing the sharing the old variable parameter did. The watcher reads through ``value`` rather than its own argument so the documented route and the mechanism under it are asserted to agree, and it deliberately closes over the wrapper, which the twins already hold alive; the leading "shared" is the watch contract's immediate first call.
    """
    twin_a = tkfacade.TitleEntry(window, title="shared", text="a")
    twin_b = tkfacade.TitleEntry(window, title=twin_a.title_observable, text="b")
    seen: list[str] = []
    twin_a.title_observable.watch(lambda _value: seen.append(twin_a.title.value))

    built = twin_a.title.value
    twin_a.title.set("retitled")

    assert (built, twin_b.title.value, twin_a.title_observable.value) == (
        "shared",
        "retitled",
        "retitled",
    )
    assert seen == ["shared", "retitled"]


def test_two_views_of_one_title_see_each_others_writes(window: tkfacade.Window) -> None:
    """Each ``title`` access is a fresh view, and none of them caches anything.

    The claim the facade rests on: the view holds nothing but the wrapper, so a caller may take as many as it likes and drive the title through any of them. A view that cached the title string or the anchor at construction would satisfy every annotation and pass the round-trip test above — the second view is what catches it, having been built before either write. Held in locals rather than chained (entry.title twice in one expression) because the identity assertion is half the point and chaining would hide which object answered.
    """
    entry = tkfacade.TitleEntry(window, title="first", text="content")

    first = entry.title
    second = entry.title
    first.set("second")
    first.anchor = "center"

    assert first is not second
    assert (second.value, second.anchor) == ("second", "center")


def test_the_title_presentation_members_round_trip(window: tkfacade.Window) -> None:
    """``justify``, ``wraplength`` and ``anchor`` answer their defaults, then their writes.

    The three members the entry gained a facade to be able to offer at all, and every one of them reads Tk's answer back through a claim the type checker cannot see. ``justify`` and ``anchor`` carry a ``# type: ignore[return-value]`` asserting Tk answers with one of the literals — it answers with a Tcl index object, so the str() around it is load-bearing and a getter that dropped it would return something that compares equal to nothing. ``wraplength`` comes back as the empty string until something sets it, normalized to 0 here and documented as "wraps only on newlines"; the defaults are read before any write because that unset state is unreachable afterwards. "w" is asserted because the anchor docstring names it as the label's own default rather than something the wrapper sets — if ttk ever stopped populating the option, this is what would say so.
    """
    entry = tkfacade.TitleEntry(window, title="a long title", text="content")

    defaults = (entry.title.justify, entry.title.wraplength, entry.title.anchor)
    entry.title.justify = "right"
    entry.title.wraplength = 120
    entry.title.anchor = "center"

    assert defaults == ("left", 0, "w")
    assert (entry.title.justify, entry.title.wraplength, entry.title.anchor) == (
        "right",
        120,
        "center",
    )


@pytest.mark.parametrize(
    ("arrangement", "title_cell", "entry_cell"),
    (
        ("top-bottom", (0, 0), (1, 0)),
        ("bottom-top", (1, 0), (0, 0)),
        ("left-right", (0, 0), (0, 1)),
        ("right-left", (0, 1), (0, 0)),
    ),
)
def test_an_arrangement_puts_the_pair_in_the_cells_it_names(
    arrangement: tkfacade.Arrangement,
    title_cell: tuple[int, int],
    entry_cell: tuple[int, int],
    window: tkfacade.Window,
) -> None:
    """Each arrangement grids title and entry where its name says, and reads back.

    Every value of the alias in one sweep, since the alias exists to be exhaustive and a fifth would have nowhere to be tested. The cells are asserted against grid_info rather than against ``arrangement`` alone because the getter derives its answer from those same two cells: a placement that wrote the row and forgot the column would put the pair on a diagonal, and a round-trip through ``arrangement`` would still agree with itself. The expected cells are written out per case rather than computed, so the table in the test is an independent statement of the layout and not a second copy of _arrange's arithmetic.
    """
    entry = tkfacade.TitleEntry(window, title="t", text="content", arrangement=arrangement)

    title_info = entry._title_label.grid_info()
    entry_info = entry._entry.grid_info()

    assert (title_info["row"], title_info["column"]) == title_cell
    assert (entry_info["row"], entry_info["column"]) == entry_cell
    assert entry.arrangement == arrangement


def test_re_arranging_clears_what_the_last_arrangement_left(window: tkfacade.Window) -> None:
    """Switching back to stacked takes the second column's weight and the gap with it.

    The failure a re-placement invites: ``grid`` merges into the options already in place and ``grid_columnconfigure`` is per column, so an implementation that wrote only what the new arrangement needs leaves the old one's weight on column 1 and the old one's padx on the label. Neither shows in the first arrangement — the widget looks right until it is moved back, and then the title carries a stray gap and the frame a stretchy empty column that eats the width the entry was supposed to get. Both leftovers are read before the switch as well as after, so the test proves it is clearing something that was genuinely there rather than asserting a zero that was never anything else.
    """
    entry = tkfacade.TitleEntry(window, title="t", text="content", arrangement="left-right")

    side_by_side = (
        entry._tk.grid_columnconfigure(1)["weight"],
        entry._title_label.grid_info()["padx"],
    )
    entry.arrangement = "top-bottom"

    assert side_by_side == (1, (0, 6))
    assert entry._title_label.grid_info()["column"] == entry._entry.grid_info()["column"] == 0
    assert entry._tk.grid_columnconfigure(1)["weight"] == 0
    assert entry._title_label.grid_info()["padx"] == 0
