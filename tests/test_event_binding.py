"""The events contract: specs as values, two roles, fanout, and emit.

The specification classes and the Event value need no interpreter; the
delivery half rides the ``window`` fixture under the ``gui`` marker.
The machinery's evidence is ``experiments/event_bind/``; these tests
hold the production dispatch — the two
declared roles, consumption as completion, no subscriber silencing a
sibling — plus the payload transport and the hook routing the design
added on top of the witnessed facts.
"""

import pytest

import tkfacade
from tkfacade import (
    Destroyed,
    Event,
    FocusGained,
    Key,
    Motion,
    MouseButton,
    PointerEnter,
    PointerLeave,
    Press,
    Release,
    Virtual,
    VirtualEvent,
    Wheel,
)
from tkfacade.window import Root


def test_specs_spell_their_tk_sequences() -> None:
    """Each specification answers with the sequence its fields describe.

    The sequence is the spec's whole meaning to Tk, so each kind's spelling is pinned: the press and release kinds for a key and for a button, an enum member spelling its keysym, the double angle brackets a virtual event's name gains. Literal strings on the right: a sequence test that composed its expectations from the same enums the code uses would pass whatever both agreed to get wrong.
    """
    assert Press("a").sequence == "<KeyPress-a>"
    assert Press(Key.ENTER).sequence == "<KeyPress-Return>"
    assert Release("a").sequence == "<KeyRelease-a>"
    assert Press(MouseButton.LEFT).sequence == "<Button-1>"
    assert Release(MouseButton.RIGHT).sequence == "<ButtonRelease-3>"
    assert Virtual("SaveRequested").sequence == "<<SaveRequested>>"
    assert Destroyed().sequence == "<Destroy>"


def test_specs_are_values() -> None:
    """Equal fields mean one spec: equal, hashable, storable before any widget.

    The first door-keeping constraint: a decorator stores a spec at class-definition time and the construction machinery looks it up later, which only works if specs compare and hash by content. The dict round-trip is the declarative bridge in miniature.
    """
    assert Press(MouseButton.LEFT) == Press(MouseButton.LEFT)
    assert hash(Press("a")) == hash(Press("a"))
    assert Press("a") != Press("b")
    registry = {Virtual("Ping"): "handler"}
    assert registry[Virtual("Ping")] == "handler"


def test_bad_specs_are_refused_at_construction() -> None:
    """A spec that cannot mean anything to Tk raises when built, not when bound.

    Values validate at birth: a spec is stored long before it is bound, and an error surfacing at bind time would point at the wrong line of the caller's code. Only spelling can be wrong now: the vocabulary describes single memoryless occurrences, so the contradictions that once needed runtime refusal -- a counted release, an unprefixable modifier -- are no longer spellable at all.
    """
    with pytest.raises(ValueError):
        Press("no keysym")
    with pytest.raises(ValueError):
        Release("")
    with pytest.raises(ValueError):
        Virtual("<nope>")


def test_specs_declare_whether_they_happen_at_the_pointer() -> None:
    """at_pointer is True exactly for the pointer-located occurrence kinds.

    The same input dichotomy the sequence spelling turns on, asked once by the dispatch: a mouse press happens at the pointer while a key press happens at the keyboard, so Press and Release answer from their input and the pointer kinds answer True by nature. The dispatch trusts this answer when deciding whether the packet's coordinates are the occurrence's own facts or a state sample to drop.
    """
    assert Press(MouseButton.LEFT).at_pointer
    assert Release(MouseButton.RIGHT).at_pointer
    assert Motion().at_pointer
    assert Wheel().at_pointer
    assert PointerEnter().at_pointer
    assert PointerLeave().at_pointer
    assert not Press("a").at_pointer
    assert not Release(Key.ENTER).at_pointer
    assert not Virtual("Ping").at_pointer
    assert not Destroyed().at_pointer
    assert not FocusGained().at_pointer


def test_virtual_events_are_one_kind_with_named_builtins() -> None:
    """A virtual event is one spec kind; type names the built-in, or None.

    The collapse ruling: the only kind of user-defined event Tk offers is a virtual event, so a separate Custom class was a nominal distinction the mechanism does not have. The enum spells which names Tk itself fires -- type answers with that member however the spec was written, since the same name IS the same event, which the equality row pins: member-built and name-built specs are one registry key, not two bindings racing over one occurrence.
    """
    assert Virtual("SaveRequested").type is None
    assert Virtual(VirtualEvent.COPY).type is VirtualEvent.COPY
    assert Virtual("Copy").type is VirtualEvent.COPY
    assert Virtual(VirtualEvent.COPY) == Virtual("Copy")
    assert Virtual(VirtualEvent.COPY).sequence == "<<Copy>>"


def test_an_event_is_fabricable_from_plain_values() -> None:
    """An Event is built from plain values, each fact given or defaulted.

    The constructor takes only plain values -- which is what keeps raw tkinter types off the Event surface in the audit, and what lets a handler's own unit test fabricate the occurrence it feeds the handler with no interpreter anywhere. The translation from tkinter's raw events belongs to the dispatch and is covered by the delivery tests; the assignment refusal pins the immutability the class claims, with the payload's own freezing pinned in its dedicated test below.
    """
    event = Event(spec=Press(MouseButton.LEFT), widget=None, widget_x=4, widget_y=2)
    assert event.spec == Press(MouseButton.LEFT)
    assert event.widget is None
    assert (event.widget_x, event.widget_y) == (4, 2)
    assert event.screen_x is None
    assert event.payload == {}
    with pytest.raises(AttributeError):
        event.widget_x = 9  # type: ignore[misc]


@pytest.mark.gui
def test_an_observer_receives_the_event_with_its_facts(window: tkfacade.Window) -> None:
    """A bound observer gets the immutable event: spec, wrapper, payload empty.

    The delivered object is the library's Event, never a tk.Event: the spec rides it, the widget field answers with the wrapper itself (resolved through the registry), and an un-emitted payload is the shared empty mapping. Emit-then-assert with no pump is deliberate -- delivery is synchronous, witnessed by the probes, and the contract says so.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    seen: list[Event] = []
    frame.bind(Virtual("Ping"), seen.append)
    frame.emit(Virtual("Ping"))

    assert len(seen) == 1
    event = seen[0]
    assert event.spec == Virtual("Ping")
    assert event.widget is frame
    assert dict(event.payload) == {}


@pytest.mark.gui
def test_a_keystroke_event_carries_no_position(window: tkfacade.Window) -> None:
    """A keystroke's event has no coordinates even when the packet does.

    The ruled reading of position: a fact only of occurrences that happen at the pointer. Tk stuffs the pointer's position into keyboard packets too -- the generate carries x=5 to prove the packet had numbers to offer -- and the snapshot drops them, because where the pointer idled during a keystroke is device state, not a fact of the keystroke. The raw generate is deliberate: emit cannot speak coordinates, and the point is what the facade withholds from a packet that carries them.
    """
    entry = tkfacade.Entry(window)
    entry.grid(row=0, column=0)
    window.update_idletasks()
    seen: list[Event] = []
    entry.bind(Press("a"), seen.append)
    entry._tk.focus_force()
    window._tk.update()
    entry._tk.event_generate("<KeyPress-a>", x=5, y=6)
    window._tk.update()

    assert len(seen) == 1
    assert (seen[0].widget_x, seen[0].widget_y) == (None, None)
    assert (seen[0].screen_x, seen[0].screen_y) == (None, None)


@pytest.mark.gui
def test_a_consumer_completing_suppresses_the_default(window: tkfacade.Window) -> None:
    """A consumer on a keystroke keeps the character out of the entry.

    Consumption as completion, end to end: the consumer's body carries no protocol at all -- a lambda returning None -- and its mere completion suppresses Tk's class default, so the character never lands. The passive twin proves the suppression came from the consumer rather than from the harness. This is the probe's eaten-keystroke witness rebuilt on the facade's own surface: wrapper bind, wrapper emit, wrapper text property.
    """
    consumed = tkfacade.Entry(window)
    passive = tkfacade.Entry(window)
    consumed.grid(row=0, column=0)
    passive.grid(row=1, column=0)
    window.update_idletasks()

    consumed.bind(Press("a"), lambda _e: None, consume=True)
    for entry in (consumed, passive):
        entry._tk.focus_force()
        window._tk.update()
        entry.emit(Press("a"))
        window._tk.update()

    assert consumed.text == ""
    assert passive.text == "a"


@pytest.mark.gui
def test_a_raising_consumer_does_not_consume_and_siblings_run(
    window: tkfacade.Window, root: Root
) -> None:
    """A consumer that raises is reported; the default proceeds; observers run.

    The failure shape for the consumer role: a raise means the consumer did not complete, so it consumed nothing -- the character lands, degrading to Tk's own behavior rather than eating input -- and the raise is routed to the hook while the observer still runs, since no subscriber can silence a sibling. All three legs in one delivery.
    """
    caught: list[BaseException] = []
    root.callback_error_handler = caught.append
    entry = tkfacade.Entry(window)
    entry.grid(row=0, column=0)
    window.update_idletasks()

    def bad(_event: Event) -> None:
        raise RuntimeError("consumer boom")

    observed: list[Event] = []
    entry.bind(Press("a"), bad, consume=True)
    entry.bind(Press("a"), observed.append)
    entry._tk.focus_force()
    window._tk.update()
    entry.emit(Press("a"))
    window._tk.update()

    assert entry.text == "a"
    assert len(observed) == 1
    assert len(caught) == 1


@pytest.mark.gui
def test_consumers_run_before_observers(window: tkfacade.Window) -> None:
    """Dispatch order is consumers first, then observers, registration order.

    The design's dispatch order, pinned from the side that could get it wrong: the observer registered first, and still hears the event after the consumer, because roles order the fanout and registration order only breaks ties within a role.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    order: list[str] = []
    frame.bind(Virtual("Ping"), lambda _e: order.append("observer"))
    frame.bind(Virtual("Ping"), lambda _e: order.append("consumer"), consume=True)
    frame.emit(Virtual("Ping"))

    assert order == ["consumer", "observer"]


@pytest.mark.gui
def test_cancelling_the_last_subscription_unbinds(window: tkfacade.Window) -> None:
    """After every subscription is cancelled, an emit reaches nobody.

    The lifecycle the surgical-unbind finding licenses: two deliveries on the first emit, one after the first cancel, none after the last -- whose cancel also removes the widget's Tk binding for the spec, which is only observable behaviorally, as the silence of the third emit.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    seen: list[Event] = []
    first = frame.bind(Virtual("Ping"), seen.append)
    second = frame.bind(Virtual("Ping"), seen.append)
    frame.emit(Virtual("Ping"))
    first.cancel()
    frame.emit(Virtual("Ping"))
    second.cancel()
    frame.emit(Virtual("Ping"))

    assert len(seen) == 3
    assert not first.active


@pytest.mark.gui
def test_emit_payload_arrives_frozen(window: tkfacade.Window) -> None:
    """The emitted mapping arrives as a read-only snapshot on the event.

    The ruled payload shape: one caller-supplied mapping, no arbitrary types, copied and frozen at the one level the library owns. The post-emit write to the source pins the copy -- delivery is a snapshot, not a view of the caller's dict -- and the mutation attempt pins the read-only half, where a plain dict would satisfy every other assertion and quietly break the immutable-event contract. The ignore is deliberate: the annotation already forbids assignment, and the test is about the runtime wall behind it.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    seen: list[Event] = []
    frame.bind(Virtual("Save"), seen.append)
    sent = {"path": "/tmp/x", "overwrite": True}
    frame.emit(Virtual("Save"), sent)
    sent["path"] = "elsewhere"

    payload = seen[0].payload
    assert dict(payload) == {"path": "/tmp/x", "overwrite": True}
    with pytest.raises(TypeError):
        payload["path"] = "elsewhere"  # type: ignore[index]


@pytest.mark.gui
def test_payload_rides_only_virtual_specs(window: tkfacade.Window) -> None:
    """A payload on a physical occurrence is refused at the emit call.

    Physical occurrences are Tk's to describe -- their facts arrive on the event itself -- so a payload on one is a category error caught at the call site, not a silent drop discovered in a handler that reads an empty mapping. The empty mapping raises too: passing the parameter at all is the mistake, and refusing it regardless of content keeps the refusal deterministic rather than data-dependent.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    with pytest.raises(TypeError):
        frame.emit(Press(MouseButton.LEFT), {"x": 1})
    with pytest.raises(TypeError):
        frame.emit(Press(MouseButton.LEFT), {})


@pytest.mark.gui
def test_a_foreign_event_carries_an_empty_payload(window: tkfacade.Window) -> None:
    """A virtual event generated past emit arrives with the empty payload.

    The stash is correlated, not ambient: an event arriving from raw Tcl -- another library, a Tk-internal generate -- must never inherit the previous emit's payload. The emit-then-foreign ordering is the trap arrangement: a stash left stale by the first delivery would grace the second.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    seen: list[Event] = []
    frame.bind(Virtual("Ping"), seen.append)
    frame.emit(Virtual("Ping"), {"token": 1})
    frame._tk.event_generate("<<Ping>>")

    assert dict(seen[0].payload) == {"token": 1}
    assert dict(seen[1].payload) == {}


@pytest.mark.gui
def test_an_undelivered_emit_leaves_no_stale_payload(window: tkfacade.Window) -> None:
    """An emit nobody subscribes to is dropped whole; the next delivery is clean.

    The stash must never outlive the generate that carried it: with no subscriber bound, the facade's dispatch never runs and never pops the entry, so emit's own way out must pop it back -- otherwise the next same-spec delivery, here a foreign Tcl-level generate, would arrive wearing a payload from an event nobody ever heard. (Tk can also drop a generate outright when the widget's X window does not exist yet -- hazards/tkinter.md, Bindings -- and the same pop-back covers that arm; the unsubscribed arrangement is used because it is deterministic on every platform and widget kind.)
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window._tk.update()
    frame.emit(Virtual("Ping"), {"token": "stale"})

    seen: list[Event] = []
    frame.bind(Virtual("Ping"), seen.append)
    frame._tk.event_generate("<<Ping>>")

    assert len(seen) == 1
    assert dict(seen[0].payload) == {}


@pytest.mark.gui
def test_a_window_binding_hears_descendants_as_wrappers(window: tkfacade.Window) -> None:
    """A window-level binding receives a child's event, widget resolved to the wrapper.

    The ruled bind surface's window half: a toplevel's bindtag hears every descendant, so the window binding fires for the frame's event and the event's widget names the frame's wrapper, resolved through the registry -- the walk a caller would otherwise hand-build from the raw event's path string.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    seen: list[Event] = []
    window.bind(Virtual("Ping"), seen.append)
    frame.emit(Virtual("Ping"))

    assert len(seen) == 1
    assert seen[0].widget is frame


def test_a_coroutine_consumer_is_still_refused() -> None:
    """The consumer role refuses a coroutine structurally, before any Tk work.

    The one refusal the async route's landing left standing, and it is permanent: completion is the verdict, and a coroutine has not completed when the verdict is due. The observer role now accepts coroutine subscribers — that acceptance needs a live core and is pinned in tests/test_async_route.py — while this guard still runs before any widget state is touched, which is what lets the test exercise it on a hollow wrapper and stay display-free.
    """

    async def handler(_event: Event) -> None:
        pass

    hollow = object.__new__(tkfacade.Frame)
    with pytest.raises(TypeError, match="consumption is completion"):
        hollow.bind(Virtual("Ping"), handler, consume=True)
