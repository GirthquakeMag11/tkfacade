"""Traversal answers wrappers: the slaves triple, ``parent``, and the rule.

The traversal rule (ruled 2026-08-27): a walk answers the wrappers the
facade built and does not name what it did not build. Downward that
means the ``*_slaves`` methods answer wrappers with raw slaves absent;
upward it means ``parent`` steps over an unwrapped widget to the
nearest wrapper. The raw ``tkinter`` used here builds the unwrapped
widgets the rule is about — tests are not examples, and the rule needs
something unbuilt to skip.
"""

import tkinter as tk

import pytest

import tkfacade
from conftest import Pump
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def test_grid_slaves_answers_the_wrappers_in_reverse_stacking_order(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A gridded host answers its slaves as wrappers, latest first.

    Identity, not paths: the answer is the very wrappers the caller built, which is the whole repair — the raw era answered Tk widgets a caller had to push back through nametowrapper by hand. The row filter rides the same delegation, so one filtered read pins that arguments still reach Tk.
    """
    host = tkfacade.Frame(window)
    first = tkfacade.Button(host, "first")
    first.grid(row=0, column=0)
    second = tkfacade.Button(host, "second")
    second.grid(row=1, column=0)

    assert host.grid_slaves() == (second, first)
    assert host.grid_slaves(row=0) == (first,)


def test_a_slave_no_wrapper_built_is_absent_from_the_answer(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A raw tkinter slave is omitted, not answered raw.

    The ruling's downward half: what the facade did not build it does not name. Answering the raw label would put a tkinter type back into the very return this item seals; answering some on-the-spot wrapper would manufacture an identity nothing owns the lifetime of.
    """
    host = tkfacade.Frame(window)
    mine = tkfacade.Button(host, "mine")
    mine.grid(row=0, column=0)
    loose = tk.Label(host._tk, text="loose")
    loose.grid(row=1, column=0)

    assert host.grid_slaves() == (mine,)


def test_a_composites_internals_stay_behind_its_boundary(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A composite masters its internals, and the walk does not name them.

    The same rule pointed at the library's own composites: a TextBox's grid manages its inner text widget and scrollbars, and a traversal that answered them raw would open a door through the facade boundary that no other surface opens. The empty answer is the boundary held.
    """
    box = tkfacade.TextBox(window, "words")

    assert box.grid_slaves() == ()


def test_pack_and_place_slaves_follow_the_same_rule(window: tkfacade.Window, pump: Pump) -> None:
    """The other two managers answer wrappers with raw slaves absent.

    One rule, three managers: the triple shares wrappers_among, so the pack and place legs each pin the shared filter riding their own Tk read rather than re-proving the rule's cases.
    """
    packer = tkfacade.Frame(window)
    packed = tkfacade.Button(packer, "packed")
    packed.pack()
    tk.Label(packer._tk, text="loose").pack()

    placer = tkfacade.Frame(window)
    placed = tkfacade.Button(placer, "placed")
    placed.place(x=0, y=0)
    tk.Label(placer._tk, text="loose").place(x=10, y=10)

    assert packer.pack_slaves() == (packed,)
    assert placer.place_slaves() == (placed,)


def test_parent_answers_the_wrapper_the_constructor_named(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``parent`` is the constructor's parent, wrapper for wrapper.

    The upward half in its plain case: the property answers the very wrapper the caller passed, so a tree built through the facade walks back up through the facade.
    """
    host = tkfacade.Frame(window)
    button = tkfacade.Button(host, "child")

    assert button.parent is host
    assert host.parent is window


def test_parent_steps_over_a_widget_no_wrapper_built(window: tkfacade.Window, pump: Pump) -> None:
    """An unwrapped intermediate does not hide the ancestry above it.

    The ruling's upward spelling: absence must fall through rather than answer None with wrappers still above, because a caller who nested one raw frame would otherwise lose the whole chain — and answering the raw frame itself is the tkinter-typed return this item seals.
    """
    host = tkfacade.Frame(window)
    loose = tk.Frame(host._tk)
    loose.grid(row=0, column=0)
    button = tkfacade.Button(loose, "nested")

    assert button.parent is host


def test_parent_tops_out_at_the_root_and_then_none(window: tkfacade.Window, root: Root) -> None:
    """The chain ends at the root wrapper, whose own parent is None.

    The chain's far end, pinned from both sides: a window's nearest wrapper above is the root wrapper itself, and the root — mastered by nothing — answers None rather than raising or inventing an ancestor.
    """
    assert window.parent is root
    assert root.parent is None


def test_a_media_players_displays_answer_the_player(window: tkfacade.Window, pump: Pump) -> None:
    """A composite's child wrappers answer the composite as their parent.

    The composite case from the inside: the display's underlying master is the player's frame, and the registry answers the player wrapper for it — so even a wrapper the caller never constructed sits in a walkable chain.
    """
    player = tkfacade.MediaPlayer(window, width=64, height=32)

    assert player._image_display.parent is player
