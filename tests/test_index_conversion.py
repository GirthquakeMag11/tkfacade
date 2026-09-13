"""The Tcl-to-Python index conversion behind ``Entry`` and ``TitleEntry``.

``_astral_width``, ``_to_python_index`` and ``_to_tcl_index`` carry the
whole of what the wrappers know about Tk's index unit: an astral
character costs two entry indices on a Tcl that stores UTF-16 and one on
a Tcl that stores codepoints, and every index after it moves with that
cost. The helpers are total functions of ``(text, index, astral)``, so
each mapping is pinned in full.

They are private to :mod:`tkfacade.text._entry` and imported from there
rather than published — the conversion is an implementation detail of
the two wrappers, and a test is not a reason to widen an interface, the
same standing this suite's other fold tests are written under.

Nothing here builds a widget. That is the point: the interpreter decides
which unit is in force, and a machine with no display — or with only one
of the two Tcls — can still hold the conversion to both answers.
"""

import tkinter as tk
from typing import cast

import pytest

from tkfacade.text._entry import _astral_width, _to_python_index, _to_tcl_index

ASTRAL = "a\U0001f600bc"
"""Four Python characters, five Tcl ones where an astral character costs two."""


class _Unusable:
    """A stand-in whose interpreter raises if anything reaches for it."""

    @property
    def tk(self) -> object:
        raise AssertionError("the interpreter was asked about text with no astral character")


def test_astral_width_answers_one_without_asking_the_interpreter() -> None:
    """Text holding no astral character is answered without a Tcl call.

    The short-circuit is the reason _astral_width takes the text at all, and nothing else can observe it: both units agree on text with no astral character, so an implementation that asked Tcl every time would return the same numbers everywhere and only cost a round trip per conversion. The stand-in turns that round trip into a failure rather than a measurement, which is the one way to assert a call did not happen. It is cast to the parameter's type because the helper reaches for `.tk` alone and mypy cannot see that a double satisfying that much is enough.
    """
    assert _astral_width(cast(tk.Misc, _Unusable()), "plain") == 1


@pytest.mark.parametrize(
    ("tcl_index", "expected"),
    [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 4)],
)
def test_a_tcl_index_converts_whole_where_an_astral_character_costs_one(
    tcl_index: int, expected: int
) -> None:
    """Under a codepoint unit every Tcl index answers itself, past-the-end clamping.

    This is the table the wrappers got wrong: the conversion exists to undo a skew, and where there is no skew it must be the identity rather than introduce one. Every index is enumerated rather than sampled because the failure it guards against was uniform — each index past the emoji off by one — so any single row would have caught it and none of them did. The trailing row is the clamp the docstring promises, Tcl's own past-the-end index answering len(text) rather than raising.
    """
    assert _to_python_index(ASTRAL, tcl_index, astral=1) == expected


@pytest.mark.parametrize(
    ("tcl_index", "expected"),
    [(0, 0), (1, 1), (2, 2), (3, 2), (4, 3), (5, 4), (6, 4)],
)
def test_a_tcl_index_converts_whole_where_an_astral_character_costs_two(
    tcl_index: int, expected: int
) -> None:
    """Under a UTF-16 unit each Tcl index past the emoji answers one lower.

    The mirror of the table above, and the two rows that matter are 2 and 3: Tcl 2 addresses the emoji's trailing half, an index no Python string has, and both it and Tcl 3 resolve forward to the "b" at Python 2 rather than splitting the character. That is the mid-surrogate case the wrappers' cursor setter is written to avoid producing, asserted here from the reading side where it can be stated as a value rather than a symptom.
    """
    assert _to_python_index(ASTRAL, tcl_index, astral=2) == expected


@pytest.mark.parametrize(
    ("python_index", "astral", "expected"),
    [
        (0, 1, 0),
        (1, 1, 1),
        (2, 1, 2),
        (3, 1, 3),
        (4, 1, 4),
        (0, 2, 0),
        (1, 2, 1),
        (2, 2, 3),
        (3, 2, 4),
        (4, 2, 5),
    ],
)
def test_a_python_index_converts_whole_under_either_unit(
    python_index: int, astral: int, expected: int
) -> None:
    """Every Python index maps to the Tcl index its unit puts it at.

    Both units in one table because the setter's whole contract is that the same caller index reaches the same character on either interpreter, and reading the two rows for a given index side by side is what shows it. The pairs that diverge start at Python 2, the first index past the emoji — 2 against 3, and at the end 4 against 5, which is the index the cursor round-trip in test_text.py drives through Tk itself. That test proves the conversion is wired into the wrappers; this one proves it is right, and it runs where no window can open.
    """
    assert _to_tcl_index(ASTRAL, python_index, astral=astral) == expected
