"""The geometry facets: wrapper behavior Tk's managers do not supply.

Everything here drives a live grid, so the module carries the ``gui``
marker and every test takes the ``window`` fixture.
"""

import tkinter as tk

import pytest

import tkfacade
from tkfacade.widget import Widget

pytestmark = pytest.mark.gui


class _Cell(Widget):
    """A minimal wrapper over a fixed-size frame, for laying out."""

    def __init__(self, parent: tkfacade.Window, /) -> None:
        """Create the frame inside ``parent``."""
        self._tk = tk.Frame(self._as_master(parent), width=30, height=20)


def test_grid_bbox_defaults_a_missing_range_half_to_the_start(window: tkfacade.Window) -> None:
    """``grid_bbox`` with one end-cell half given fills the other from the start.

    tkinter's own grid_bbox forwards the end cell only when both halves are given, so a lone col2 used to be dropped whole and the call answered the single starting cell's box — plausible pixels for the wrong region. The four-argument spelling is the oracle: the three-argument call must equal it, and must differ from the bare single-cell call, which is exactly what it used to collapse into.
    """
    for column in range(3):
        _Cell(window).grid(row=0, column=column)
    window.update_idletasks()

    spanned = window.grid_bbox(0, 0, 2, 0)

    assert spanned == window.grid_bbox(0, 0, 2)
    assert spanned != window.grid_bbox(0, 0)


def test_wrappers_pass_through_in_after_and_before(window: tkfacade.Window) -> None:
    """A wrapper given as ``in_``/``before`` reaches Tk instead of vanishing.

    The ... sentinel was detected with isinstance(tk.Misc), so a wrapper — the only handle this library gives out — failed the check and was silently dropped from the options: in_ placed into the construction parent and before= appended to the end of the packing order, layouts wrong with nothing raised. All three managers ride one test because they share the sentinel idiom, and every assertion reads the landed option back from Tk rather than trusting the call not to raise. The pack and place legs target a gridded sibling as their master because pack and grid refuse to share one, which is also why the old drop surfaced here as a manager-conflict error rather than quietly.
    """
    holder = _Cell(window)
    holder.grid(row=0, column=0)
    inner = _Cell(window)
    inner.grid(in_=holder, row=0, column=0)

    assert str(inner._tk.grid_info()["in"]) == str(holder._tk)

    pack_host = _Cell(window)
    pack_host.grid(row=1, column=0)
    first = _Cell(window)
    first.pack(in_=pack_host)
    second = _Cell(window)
    second.pack(in_=pack_host, before=first)

    assert [str(s) for s in pack_host._tk.pack_slaves()] == [str(second._tk), str(first._tk)]

    placed = _Cell(window)
    placed.place(in_=pack_host, x=1, y=1)

    assert str(placed._tk.place_info()["in"]) == str(pack_host._tk)


def test_a_cnf_carried_in_keeps_the_chosen_pack_position(window: tkfacade.Window) -> None:
    """``in_`` arriving via ``cnf`` still precedes ``after``/``before`` at Tk.

    The in_-first insertion guarded only the keyword door: cnf is merged last (so it can override first-placement defaults), and a dict update appends new keys at the end — so a cnf-carried in_ landed after -before in the Tcl argument list, where Tk's left-to-right read makes a late -in mean "append", silently discarding the chosen position. Both cnf spellings are driven — in_ in cnf with a keyword before, and both in one cnf — because they exercise the same merge through different key orders; the pack_slaves read is Tk's own word on where everything landed. cnf carries the bare widget because PackSetOptions admits tk.Misc there, not wrappers.
    """
    host = _Cell(window)
    host.grid(row=0, column=0)
    first = _Cell(window)
    first.pack({"in_": host._tk})
    second = _Cell(window)
    second.pack({"in_": host._tk}, before=first)
    third = _Cell(window)
    third.pack({"in_": host._tk, "before": second._tk})

    slaves = [str(s) for s in host._tk.pack_slaves()]
    assert slaves == [str(third._tk), str(second._tk), str(first._tk)]


def test_a_reconfigure_call_changes_only_what_it_names(window: tkfacade.Window) -> None:
    """A second geometry call leaves unnamed options standing; a first fills defaults.

    Every keyword used to carry a concrete default sent to Tcl on every call, so w.grid(row=1) after w.grid(row=0, sticky="w", padx=10) moved the widget and silently snapped sticky and padding back to defaults — where the Tk command the docstrings delegate to is incremental on a managed widget. All three managers ride one test because they shared the always-send shape; each asserts a surviving option beside the changed one, and the fresh grid pins that a first placement still fills the wrapper's own opinionated defaults, the half a naive send-only-what-was-named fix would lose. Read-backs go through Tk's info calls because the defect was in what landed, not what was passed, and Tk's own spellings (sticky "nesw", string place values) are asserted as Tk reports them.
    """
    gridded = _Cell(window)
    gridded.grid(row=0, column=0, sticky="w", padx=10)
    gridded.grid(row=2)
    info = gridded._tk.grid_info()
    assert (info["row"], str(info["sticky"]), info["padx"]) == (2, "w", 10)

    fresh = _Cell(window)
    fresh.grid(row=3, column=0)
    assert str(fresh._tk.grid_info()["sticky"]) == "nesw"

    host = _Cell(window)
    host.grid(row=1, column=0)
    packed = _Cell(window)
    packed.pack(in_=host, side="left", padx=9, expand=True)
    packed.pack(ipadx=1)
    pinfo = packed._tk.pack_info()
    assert (str(pinfo["side"]), pinfo["padx"], pinfo["expand"], pinfo["ipadx"]) == (
        "left",
        9,
        1,
        1,
    )

    placed = _Cell(window)
    placed.place(in_=host, x=50, anchor="center", relwidth=0.5)
    placed.place(y=10)
    plinfo = placed._tk.place_info()
    assert (plinfo["x"], plinfo["y"], plinfo["anchor"], plinfo["relwidth"]) == (
        "50",
        "10",
        "center",
        "0.5",
    )


def test_pack_info_expand_is_the_int_tk_returns(window: tkfacade.Window) -> None:
    """``pack_info`` answers ``expand`` as Tk's 0/1 int, matching its type.

    PackInfo declared expand as bool while Tk round-trips 0/1 ints, so `info["expand"] is True` was False on an expanding widget and typed consumers were told a shape the runtime never honors. The exact-type assertion is the point — equality alone passes for True under int interning — and the TypedDict now says int, which this pins against a tkinter that might someday start converting.
    """
    host = _Cell(window)
    host.grid(row=2, column=0)
    packed = _Cell(window)
    packed.pack(in_=host, expand=True)

    value = packed.pack_info()["expand"]

    assert value == 1
    assert type(value) is int


def test_grid_restores_what_grid_remove_remembered(window: tkfacade.Window) -> None:
    """A bare ``grid()`` after ``grid_remove`` restores Tk's memory; ``grid_forget`` clears it.

    Tk remembers a grid_remove'd widget's full option set and its own bare grid restores it, but exposes no way to ask — removed and never-gridded both read manager "" and grid_info {} — so the wrapper's first-placement detection stamped the defaults over the memory: a hide/show cycle landed the widget at (0, 0), sticky nsew, no padding. The wrapper now owns the removal and carries the distinction itself, which is why grid_remove and grid_forget exist as methods rather than raw-Tk reaches. The forget leg pins the other half: discarded memory makes the next grid a genuine first placement, wrapper defaults and all.
    """
    cell = _Cell(window)
    cell.grid(row=3, column=2, sticky="w", padx=7)

    cell.grid_remove()
    cell.grid()
    info = cell._tk.grid_info()

    assert (info["row"], info["column"], str(info["sticky"]), info["padx"]) == (3, 2, "w", 7)

    cell.grid_forget()
    cell.grid(row=1, column=1)

    assert str(cell._tk.grid_info()["sticky"]) == "nesw"


def test_a_bogus_grid_remove_leaves_the_first_placement_a_first_placement(
    window: tkfacade.Window,
) -> None:
    """``grid_remove`` on a widget grid never managed records nothing.

    grid_remove set its removal flag unconditionally, but Tk's grid remove on an unmanaged widget is a silent no-op that leaves no remembered options — so the next grid(), a genuine first placement, saw the flag, concluded Tk held memory to restore, and skipped stamping the wrapper's defaults: sticky landed "" where the wrapper documents "nsew". The flag is now recorded only when grid actually manages the widget, which the sticky read pins from Tk's side; row and column are read too because a fully bare grid() after the bogus remove used to lose them to auto-placement as well.
    """
    cell = _Cell(window)

    cell.grid_remove()
    cell.grid(row=0, column=0)
    info = cell._tk.grid_info()

    assert (info["row"], info["column"], str(info["sticky"])) == (0, 0, "nesw")
