""":class:`~tkfacade.PanedFrame`: panes side by side, split by sashes.

A container with its own geometry manager: every pane is visible at
once and the user redistributes space between them. Not an
:class:`~tkfacade.AbstractMultiFrame`, whose pages take turns — this
borrows that family's keyed-frames shape without claiming its
contract, and the suite exercises the shape rather than assuming it.
"""

import tkinter as tk

import pytest

import tkfacade

pytestmark = pytest.mark.gui


def _split(window: tkfacade.Window) -> tkfacade.PanedFrame:
    """A realized horizontal split with two weighted panes."""
    paned = tkfacade.PanedFrame(window, width=300, height=200)
    paned.grid(row=0, column=0, sticky="nsew")
    paned.add("left", weight=1)
    paned.add("right", weight=1)
    window._tk.update()
    return paned


def test_the_mapping_answers_panes_in_order(window: tkfacade.Window) -> None:
    """Panes are keyed as added and ordered as they sit.

    The mapping face, and the two refusals that keep it honest: an unknown key raises rather than answering something, and a key already in use is refused rather than silently replacing a live pane. Panes come back as Frames because the container makes them — Tk accepts a pane that is not its child and accepts one being gridded on top of the pane management, and a caller handed a frame can do neither.
    """
    paned = tkfacade.PanedFrame(window)
    first = paned.add("first")
    second = paned.add("second")

    assert list(paned) == ["first", "second"]
    assert len(paned) == 2
    assert paned["first"] is first
    assert paned["second"] is second
    assert isinstance(first, tkfacade.Frame)

    with pytest.raises(KeyError):
        paned["missing"]
    with pytest.raises(ValueError, match="already exists"):
        paned.add("first")


def test_the_inherited_mapping_mixins_answer_the_panes(window: tkfacade.Window) -> None:
    """``keys``, ``values``, ``items``, ``get`` and membership all come from Mapping, live.

    The inherited half of the mapping contract, none of which this class writes itself: every one is built on ``__iter__`` and ``__getitem__``, so a regression in either would turn the whole set into a lie with nothing in the class's own source looking different. Asserted for the container separately from the multi-frames because it inherits ``Mapping`` directly rather than through ``AbstractMultiFrame``, and each side could break alone.
    """
    paned = tkfacade.PanedFrame(window)
    first = paned.add("first")
    second = paned.add("second")

    assert list(paned.keys()) == ["first", "second"]
    assert list(paned.values()) == [first, second]
    assert list(paned.items()) == [("first", first), ("second", second)]
    assert paned.get("first") is first
    assert paned.get("missing") is None
    assert "first" in paned
    assert "missing" not in paned


def test_insert_places_a_pane_among_the_others(window: tkfacade.Window) -> None:
    """A pane inserted at an index sits there, and the books follow.

    Insertion is where a keyed mapping and a positional widget can drift apart: Tk puts the pane where it was told while a dict remembers insertion order, so the books are rebuilt from Tk's own pane order rather than trusted. An index past the end appends, as a list's insert does.
    """
    paned = tkfacade.PanedFrame(window)
    paned.add("first")
    paned.add("third")
    paned.insert(1, "second")
    window._tk.update()

    assert list(paned) == ["first", "second", "third"]

    paned.insert(99, "last")

    assert list(paned) == ["first", "second", "third", "last"]


def test_forgetting_a_pane_leaves_the_mapping(window: tkfacade.Window) -> None:
    """A removed pane frees its key, and a destroyed one leaves too.

    Both routes out of the mapping. Forgetting is the container's, and the key is free again afterwards. Destroying the frame is the caller's, and the pane leaves the books by its own Destroyed binding — the same identity-guarded eviction StackFrame uses, so a page that died cannot evict a live replacement under its key.
    """
    paned = _split(window)

    paned.forget("left")
    window._tk.update()

    assert list(paned) == ["right"]

    paned.add("left")
    window._tk.update()
    assert list(paned) == ["right", "left"]

    paned["right"].destroy()
    window._tk.update()

    assert list(paned) == ["left"]


def test_weights_are_read_and_set_by_key(window: tkfacade.Window) -> None:
    """The one per-pane setting ttk offers, keyed.

    A keyed pair rather than a property, a property being unable to take the key that says which pane, and rather than a handle, ttk offering exactly one setting per pane — `pane()` answers `{'weight': N}` and nothing else, so a handle would be ceremony around a single integer.
    """
    paned = tkfacade.PanedFrame(window)
    paned.add("fixed")
    paned.add("stretchy", weight=3)

    assert paned.weight("fixed") == 0
    assert paned.weight("stretchy") == 3

    paned.set_weight("fixed", 2)

    assert paned.weight("fixed") == 2

    with pytest.raises(KeyError):
        paned.weight("missing")


def test_sash_positions_report_and_move(window: tkfacade.Window) -> None:
    """One sash fewer than panes, readable live and movable.

    A sash divides two neighbours, so an empty container and a single-pane one have none — both asserted, since "one fewer" is the kind of arithmetic that goes wrong at zero. The moved position is compared with a tolerance because Tk settles a sash where the panes around it allow, which the method's docstring says.
    """
    empty = tkfacade.PanedFrame(window)
    lonely = tkfacade.PanedFrame(window)
    lonely.add("only")
    paned = _split(window)

    assert empty.sash_positions == ()
    assert lonely.sash_positions == ()
    assert len(paned.sash_positions) == 1

    paned.move_sash(0, 120)
    window._tk.update()

    assert abs(paned.sash_positions[0] - 120) <= 2

    with pytest.raises(IndexError, match="no sash at"):
        paned.move_sash(5, 100)


def test_the_orientation_is_fixed_at_construction(window: tkfacade.Window) -> None:
    """orient reads back and cannot be reassigned, because Tk refuses.

    Read-only is Tk's ruling rather than the wrapper's, and the test says so by provoking Tk directly: the option answers "attempt to change read-only option". The wrapper offers no setter, so this is the only way to show why there is none — and typeshed agrees, which is why the question has to be put in Tcl.
    """
    sideways = tkfacade.PanedFrame(window)
    stacked = tkfacade.PanedFrame(window, orient="vertical")

    assert sideways.orient == "horizontal"
    assert stacked.orient == "vertical"

    with pytest.raises(tk.TclError, match="read-only"):
        # through Tcl rather than configure(): typeshed declares the option
        # read-only too, so the typed route cannot ask the question
        stacked._tk.tk.call(str(stacked._tk), "configure", "-orient", "horizontal")


def test_a_pane_masters_and_lays_out_what_is_built_in_it(window: tkfacade.Window) -> None:
    """A pane is a frame like any other once the container has placed it.

    The division of labour the design turns on: the container places the pane, and everything inside the pane is the caller's ordinary business. The padding is compared against a frame built the ordinary way rather than against a literal: what is claimed is that a pane is a plain Frame, not that Frame's default padding is any particular thing, which is Frame's own business and already its own test.
    """
    paned = _split(window)
    inside = tkfacade.Button(paned["left"], "Press")
    inside.grid(row=0, column=0)
    window._tk.update()

    assert str(inside._tk.winfo_parent()) == str(paned["left"]._tk)
    assert inside._tk.winfo_ismapped()
    assert paned["left"].padding == tkfacade.Frame(window).padding
