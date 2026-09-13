"""The frame containers: the plain :class:`Frame`, and the multi-frames.

:class:`Frame` is thin over ``ttk.Frame``, so what is worth testing is
the seam: that an option assigned reaches Tk rather than being kept in
Python, and that one read comes back off the widget rather than out of
something remembered at construction. :class:`StackFrame` and
:class:`TabFrame` both implement the :class:`AbstractMultiFrame`
contract — pages addressed by key, exactly one mapped at a time — with
different hosting: a stack maps pages into one shared grid cell, a tab
frame hands them to a ``ttk.Notebook``. Their pages are ``Frame``
wrappers too, so the two halves of this file meet: a page is destroyed
and asked whether it is mapped through the same surface any other frame
answers on. Everything here needs a live widget and mapping is only
observable on a realized window, so the suite rides the ``window``
fixture under the ``gui`` marker, gridding and pumping wherever a
container's own placement is what is in question.
"""

from collections.abc import Callable

import pytest

import tkfacade
from conftest import Pump

pytestmark = pytest.mark.gui


def test_frame_construction_options_reach_the_widget(window: tkfacade.Window) -> None:
    """Every constructor option is readable back off the widget that was built.

    The constructor is the one place the four options could be accepted and dropped, since nothing else in the class would notice: the properties read Tk rather than any stored copy, so a __init__ that took an option and never forwarded it would answer with ttk's default and look like a working default instead of a lost argument. Every value here is chosen away from that default — "groove" against "flat", a two-element padding against 0, non-zero sizes — so each assertion fails if its option was not forwarded.
    """
    frame = tkfacade.Frame(window, relief="groove", padding=(12, 6), width=200, height=150)

    assert frame.relief == "groove"
    assert frame.padding == (12, 6)
    assert frame.width == 200
    assert frame.height == 150


def test_frame_options_are_read_live_off_the_widget(window: tkfacade.Window) -> None:
    """Changes made behind the wrapper are seen, and changes made through it land in Tk.

    Both directions of the seam, because a wrapper caching values in Python passes neither: the first half configures the Tk widget past the facade and asks the properties what they see, the second assigns through the properties and asks Tk. Reading past the facade goes through the public handles — ``tk`` is the interpreter and a wrapper stringifies to its own widget path — rather than through ``_tk``, so the test says nothing about how the wrapper stores what it wraps.
    """
    frame = tkfacade.Frame(window)

    frame.tk.call(frame, "configure", "-relief", "sunken", "-width", 120)

    assert frame.relief == "sunken"
    assert frame.width == 120

    frame.relief = "ridge"
    frame.height = 90

    assert str(frame.tk.call(frame, "cget", "-relief")) == "ridge"
    assert int(frame.tk.call(frame, "cget", "-height")) == 90


def test_frame_padding_answers_as_a_tuple_whatever_shape_it_was_set(
    window: tkfacade.Window,
) -> None:
    """One amount, two or four all answer as a tuple of plain values.

    The one getter that converts, and every shape it has to survive. Tk keeps -padding as a list however it was set, so a single amount comes back wrapped and the property says so rather than unwrapping it into an inconsistency; the first assertion pins that on the constructor's own default. The amounts arrive as ints for whole pixel counts and as Tk's pixel objects for anything else, which compare equal to nothing a caller would write — the "2c" case is what fails if that coercion goes, and it is the only one that would, since ints need none. An unset padding answers "" rather than an empty list, which is the empty-tuple case at the end.
    """
    frame = tkfacade.Frame(window)

    assert frame.padding == (0,)

    frame.padding = 6
    assert frame.padding == (6,)

    frame.padding = (12, 6)
    assert frame.padding == (12, 6)

    frame.padding = (1, 2, 3, 4)
    assert frame.padding == (1, 2, 3, 4)

    frame.padding = "2c"
    assert frame.padding == ("2c",)

    frame.padding = ""
    assert frame.padding == ()


def test_frame_size_requests_are_honoured_only_with_propagation_off(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A frame sizes to its children until grid propagation is turned off.

    What width and height are documented to be worth, which is nothing at all while a frame is sizing to its children — a property answering 300 on a frame 30 pixels wide is the whole reason the docstring says "asks for" rather than "is". The two frames differ only in the grid_propagate call, so that call is what the contrast attributes the difference to, and it comes before the child because hazards/tkinter.md records that the same call after one has settled holds the settled size instead. The requested size is read through _tk: winfo_reqwidth is not on the facade, and the point here is what Tk ended up believing. grid_propagate is inherited from the container half, so this exercises that Frame really is a master and not only a slave.
    """
    sized = tkfacade.Frame(window, width=300, height=200)
    sized.grid(row=0, column=0)
    tkfacade.TextLabel(sized, text="hello").grid(row=0, column=0)
    pump(window)

    assert (sized._tk.winfo_reqwidth(), sized._tk.winfo_reqheight()) != (300, 200)

    held = tkfacade.Frame(window, width=300, height=200)
    held.grid_propagate(False)
    held.grid(row=1, column=0)
    tkfacade.TextLabel(held, text="hello").grid(row=0, column=0)
    pump(window)

    assert (held._tk.winfo_reqwidth(), held._tk.winfo_reqheight()) == (300, 200)
    assert (held.width, held.height) == (300, 200)


@pytest.mark.parametrize("build", (tkfacade.StackFrame, tkfacade.TabFrame), ids=("stack", "tab"))
def test_a_page_is_a_frame_wrapper(build: Build, window: tkfacade.Window) -> None:
    """Both containers answer with ``Frame`` from every route into the mapping.

    The mapping has four routes to a page -- add, __getitem__, showing and the inherited views -- and each is separately capable of handing back the raw widget, since the containers store one object and the ABC types another. Both implementations are held to it because each writes its own __getitem__ and showing. The identity assertions are what say the page is stored rather than freshly wrapped on every read: a container building a new Frame per access would satisfy isinstance everywhere and still break every caller who kept the page add() gave them.
    """
    frame = build(window)
    page = frame.add("a")
    frame.show("a")

    assert isinstance(page, tkfacade.Frame)
    assert isinstance(frame["a"], tkfacade.Frame)
    assert isinstance(frame.showing, tkfacade.Frame)
    assert frame["a"] is page
    assert list(frame.values()) == [page]


@pytest.mark.parametrize("build", (tkfacade.StackFrame, tkfacade.TabFrame), ids=("stack", "tab"))
def test_a_page_takes_the_frame_interface(build: Build, window: tkfacade.Window) -> None:
    """A page is configured and laid out through its own wrapper, like any frame.

    What the type change is actually worth: before it, every one of these lines needed the raw widget. The Label is built with the page as its parent, which is the whole point of a page being a wrapper -- _as_master unwraps it -- and children counts one to show the label really landed inside the page rather than beside it.
    """
    frame = build(window)
    page = frame.add("a")

    page.padding = 12
    page.relief = "sunken"
    tkfacade.TextLabel(page, text="inside").grid(row=0, column=0)

    assert page.padding == (12,)
    assert page.relief == "sunken"
    assert len(page.children) == 1


@pytest.mark.parametrize("build", (tkfacade.StackFrame, tkfacade.TabFrame), ids=("stack", "tab"))
def test_a_page_is_found_by_nametowrapper(build: Build, window: tkfacade.Window) -> None:
    """A page is a registered wrapper, and stops being one when it dies.

    The externally visible consequence of pages being wrappers, and the claim BaseWidget.nametowrapper's docstring now makes -- it named a StackFrame's pages as misses for as long as they were raw widgets. Registration hangs off Frame.__init__ calling super() last, so this fails if a container ever builds its pages some other way. The eviction half is asserted too because a registry that only ever gains entries would pass the first assertion forever while leaking a wrapper per page.
    """
    frame = build(window)
    page = frame.add("a")
    path = str(page)

    assert window.nametowrapper(path) is page

    page.destroy()

    with pytest.raises(KeyError):
        window.nametowrapper(path)


type Build = Callable[[tkfacade.Window], tkfacade.AbstractMultiFrame]


@pytest.mark.parametrize("build", (tkfacade.StackFrame, tkfacade.TabFrame), ids=("stack", "tab"))
def test_multi_frames_answer_the_whole_mapping_contract(
    build: Build, window: tkfacade.Window
) -> None:
    """``len``, ``in``, iteration and the inherited views all read the live pages.

    The whole of Mapping, which is what AbstractMultiFrame declares. The inherited half is the half that breaks quietly: keys, items, values, get and ``in`` are all built on __iter__ and __getitem__, so a subclass whose __iter__ yielded pages instead of keys would satisfy the interpreter and turn every one of them into a lie. Before the contract was declared, ``in`` and iteration reached Python's legacy iteration protocol instead, which subscripts with 0, 1, 2 … and raised KeyError: 0 about a key no caller wrote — the regression the first three assertions guard. Both implementations are held to it because each writes its own __iter__ and __len__; ordering is asserted because both store pages in a dict, whose insertion order is the only order a page key has.
    """
    frame = build(window)
    first = frame.add("a")
    second = frame.add("b")

    assert len(frame) == 2
    assert list(frame) == ["a", "b"]
    assert "a" in frame
    assert "missing" not in frame
    assert list(frame.keys()) == ["a", "b"]
    assert list(frame.values()) == [first, second]
    assert list(frame.items()) == [("a", first), ("b", second)]
    assert frame.get("b") is second
    assert frame.get("missing") is None


def test_a_multi_frame_compares_and_hashes_by_identity(window: tkfacade.Window) -> None:
    """Two containers are equal only to themselves, and stay hashable.

    Declaring Mapping brings its content equality along, under which these two empty containers would compare equal, and the __hash__ = None that comes with it would make a widget unusable as a dict key or set member. Both are overridden back to identity, and both halves are asserted because __eq__ alone cannot show the hash survived. The containers are left empty on purpose: that is the state in which content equality and identity disagree most loudly.
    """
    first = tkfacade.StackFrame(window)
    second = tkfacade.StackFrame(window)

    assert first == first
    assert first != second
    assert len({first, second}) == 2


def test_stack_add_rejects_duplicate_keys(window: tkfacade.Window) -> None:
    """Adding a page under an existing key raises ``ValueError``.

    The AbstractMultiFrame contract for add. Silently replacing would orphan the first frame — still gridded in the shared cell but no longer reachable by key — so the refusal is what keeps the key space and the cell contents in agreement. The match pins that the message names the offending key.
    """
    stack = tkfacade.StackFrame(window)
    stack.add("page")

    with pytest.raises(ValueError, match="page"):
        stack.add("page")


def test_stack_lookup_and_show_reject_unknown_keys(window: tkfacade.Window) -> None:
    """``show`` and ``__getitem__`` raise ``KeyError`` for unknown keys.

    Both lookups share the mapping idiom, and both must refuse before touching Tk: show("missing") reaching the grid calls would unmap every real page and leave the region empty. Tested on a non-empty stack so the failure is the key, not emptiness.
    """
    stack = tkfacade.StackFrame(window)
    stack.add("only")

    with pytest.raises(KeyError):
        stack.show("missing")
    with pytest.raises(KeyError):
        stack["missing"]


def test_stack_first_show_is_deferred_to_the_event_loop(
    window: tkfacade.Window, pump: Pump
) -> None:
    """The first page maps only once the event loop has run.

    add() schedules the first show via after(0, ...) because showing before the mainloop starts fumbles Tk's stacking order — so the page being *unmapped* immediately after add is part of the design, not a bug, and the pump fixture exists precisely because update_idletasks cannot fire that job. Both moments are asserted so a future eager first-show (the original broken shape) fails on the first line.
    """
    stack = tkfacade.StackFrame(window)
    stack.grid(row=0, column=0)
    first = stack.add("first")

    assert not first.winfo_ismapped()
    pump(window)
    assert first.winfo_ismapped()
    assert stack.showing is first


def test_stack_pre_pump_show_is_not_stomped(window: tkfacade.Window, pump: Pump) -> None:
    """An explicit ``show`` before the deferred first show wins over it.

    The subtlest behavior in frame/: the deferred first-show re-reads _current when it finally fires, exactly so a caller who added pages and immediately showed a specific one pre-mainloop is not overridden by the queued job. A lambda that captured the first key at add() time — the natural way to write it — fails this test.
    """
    stack = tkfacade.StackFrame(window)
    stack.grid(row=0, column=0)
    first = stack.add("first")
    second = stack.add("second")
    stack.show("second")
    pump(window)

    assert second.winfo_ismapped()
    assert not first.winfo_ismapped()
    assert stack.showing is second


def test_stack_show_maps_exactly_one_page(window: tkfacade.Window, pump: Pump) -> None:
    """After a show, the named page is mapped and every sibling is not.

    The core contract, quoted from AbstractMultiFrame: "Exactly one page is mapped at a time: hidden pages report winfo_ismapped() == False". Unmapping matters because Tk raises widgets silently — a stack that merely raised the incoming page would pass any showing-based check while covered siblings still reported themselves mapped and full-size. Three pages, switched away from the default, so both the map and both unmaps are real transitions.
    """
    stack = tkfacade.StackFrame(window)
    stack.grid(row=0, column=0)
    pages = {key: stack.add(key) for key in ("a", "b", "c")}
    pump(window)

    stack.show("b")
    pump(window)

    assert [key for key, page in pages.items() if page.winfo_ismapped()] == ["b"]
    assert stack.showing is pages["b"]


def test_tab_first_page_becomes_current_via_the_notebook(
    window: tkfacade.Window, pump: Pump
) -> None:
    """The notebook's own first-tab selection is reflected by ``showing``.

    TabFrame never calls show() for the first page — ttk.Notebook selects the first tab itself, and _current is picked up from the <<NotebookTabChanged>> event. That event-driven path is the same one a user's click takes, so this pins user-driven tracking without synthesizing click coordinates. The pump is what delivers the event; before it, showing is legitimately None.
    """
    tabs = tkfacade.TabFrame(window)
    tabs.grid(row=0, column=0)
    first = tabs.add("first")
    tabs.add("second")
    pump(window)

    assert tabs.showing is first


def test_tab_show_selects_and_tracks(window: tkfacade.Window, pump: Pump) -> None:
    """``show`` switches the selected tab and ``showing`` follows.

    The programmatic half of TabFrame's contract, plus the shared one-page-mapped invariant on the Notebook host — the Notebook unmaps deselected tabs itself, but that is exactly the kind of host behavior the abstract contract exists to pin across implementations. The title kwarg rides along to exercise add's one TabFrame-specific parameter.
    """
    tabs = tkfacade.TabFrame(window)
    tabs.grid(row=0, column=0)
    first = tabs.add("first")
    second = tabs.add("second", title="2nd")
    pump(window)

    tabs.show("second")
    pump(window)

    assert tabs.showing is second
    assert second.winfo_ismapped()
    assert not first.winfo_ismapped()


def test_tab_lookup_and_show_reject_unknown_keys(window: tkfacade.Window) -> None:
    """``show`` and ``__getitem__`` raise ``KeyError``; duplicate adds raise.

    The same contract edges as the stack tests, on the other implementation: the ABC leaves add/show entirely to subclasses, so nothing guarantees the two containers refuse alike except tests that hold them both to it.
    """
    tabs = tkfacade.TabFrame(window)
    tabs.add("only")

    with pytest.raises(KeyError):
        tabs.show("missing")
    with pytest.raises(KeyError):
        tabs["missing"]
    with pytest.raises(ValueError, match="only"):
        tabs.add("only")


def test_stack_first_show_skips_a_page_destroyed_before_the_event_loop_turns(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A page destroyed before the deferred first show leaves the stack empty, quietly.

    The first ``add`` defers its show to an idle job so tkinter does not fumble the stacking order before mainloop; the page can be destroyed in between, and destroying a page does not take it out of the stack's own dict, so the job still names it and ``show`` would call grid() on a dead widget. That raises from inside a Tk callback, where it reaches report_callback_exception rather than any caller — which is why the handler is captured rather than pytest.raises used. Asserting ``showing is None`` as well keeps the test honest: swallowing the error by never running the job at all would be a different bug, and this says the stack really did decline to show a page rather than never having tried.
    """
    raised: list[str] = []
    root = tkfacade.get_root()
    stack = tkfacade.StackFrame(window)

    def record(exc: type[BaseException], val: BaseException, _tb: object) -> None:
        raised.append(f"{exc.__name__}: {val}")

    original = root._tk.report_callback_exception
    root._tk.report_callback_exception = record
    page = stack.add("a")
    page.destroy()
    pump(window)
    root._tk.report_callback_exception = original

    assert raised == []
    assert stack.showing is None


@pytest.mark.parametrize("build", (tkfacade.StackFrame, tkfacade.TabFrame), ids=("stack", "tab"))
def test_a_destroyed_page_leaves_the_container(
    build: Build, window: tkfacade.Window, pump: Pump
) -> None:
    """A destroyed page leaves the mapping, frees its key, and never haunts ``showing``.

    Nothing removed a destroyed page before: showing answered a dead widget, show raised TclError where the contract promises KeyError, the key was stuck refusing a replacement forever, and len counted corpses. The assertions walk that exact cost list in order. showing is pinned as not-the-corpse rather than as a concrete page because the implementations legitimately diverge — a stack shows nothing while the notebook auto-selects the surviving tab — and the re-add closes the loop with the freed key hosting a live replacement.
    """
    frame = build(window)
    frame.add("a")
    doomed = frame.add("b")
    frame.show("b")
    pump(window)

    doomed.destroy()
    pump(window)

    assert list(frame) == ["a"]
    assert len(frame) == 1
    assert frame.showing is not doomed
    with pytest.raises(KeyError):
        frame.show("b")

    replacement = frame.add("b")
    frame.show("b")
    pump(window)

    assert frame.showing is replacement


@pytest.mark.parametrize("build", (tkfacade.StackFrame, tkfacade.TabFrame), ids=("stack", "tab"))
def test_none_is_refused_as_a_page_key(build: Build, window: tkfacade.Window) -> None:
    """``add(None)`` raises on both containers instead of minting an unshowable page.

    None is _current's nothing-shown sentinel in both containers, and add accepted it: the page mapped while showing answered None, a selected None tab read as nothing selected, and a pre-mainloop explicit show(None) was stomped by the first-show fallback that treats _current None as "no choice made". Refusal at add is the menu package's model — its ledger reserves None for separators by construction — and the length assertion pins that the refusal leaves no half-registered page behind.
    """
    frame = build(window)

    with pytest.raises(ValueError, match="sentinel"):
        frame.add(None)

    assert len(frame) == 0


def test_an_emptied_stack_shows_its_next_page(window: tkfacade.Window, pump: Pump) -> None:
    """A stack repopulated after losing every page shows the new page, as a fresh one would.

    The initial-show trigger was a first-add-ever flag nothing reset, so once eviction made keys reusable an emptied stack re-added into a blank region — len 1, showing None — while TabFrame's notebook auto-selected in the identical sequence, splitting the ABC's "first page added is the one initially shown" between implementations. The trigger is now the stack's emptiness at add time, which is what the flag was standing in for all along; the pre-destroy assertion pins that the ordinary first show still works through the same path.
    """
    stack = tkfacade.StackFrame(window)
    stack.grid(row=0, column=0)
    first = stack.add("a")
    pump(window)
    assert stack.showing is first

    first.destroy()
    pump(window)

    replacement = stack.add("b")
    pump(window)

    assert stack.showing is replacement
    assert bool(replacement.winfo_ismapped())
