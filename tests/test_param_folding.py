"""The boolean-to-literal folds ``_show_param``, ``select_param`` and ``_wrap_param``.

Each translates a wrapper's independent boolean options into the
composite literal Tk actually takes, so every truth table is pinned in
full — the folds are total functions and small enough to enumerate.

All three are private to the module defining them —
:mod:`tkfacade.tree._tree` and :mod:`tkfacade.text._text` — and imported from
there rather than published: a fold is an implementation detail of its
wrapper's constructor, and a test is not a reason to widen an
interface.
"""

from typing import Literal

import pytest

from tkfacade._utils import select_param
from tkfacade.text._box import _wrap_param
from tkfacade.tree import SelectParam, ShowParam
from tkfacade.tree._tree import _show_param


@pytest.mark.parametrize(
    ("tree", "headings", "expected"),
    [
        (True, True, "tree headings"),
        (True, False, "tree"),
        (False, True, "headings"),
        (False, False, ""),
    ],
)
def test_show_param_folds_the_full_truth_table(
    tree: bool, headings: bool, expected: ShowParam
) -> None:
    """Every ``(tree, headings)`` pair maps to its Tk ``show`` literal.

    The full table rather than a sample because the fold's whole job is the mapping, and the two easy-to-swap cases — which single boolean yields "tree" and which "headings" — are exactly the regression a partial table could miss. The empty string for (False, False) is Tk's real spelling of "show neither", so it is asserted literally.
    """
    assert _show_param(tree, headings) == expected


@pytest.mark.parametrize(
    ("enabled", "extended", "expected"),
    [
        (True, True, "extended"),
        (True, False, "browse"),
        (False, True, "none"),
        (False, False, "none"),
    ],
)
def test_select_param_folds_the_full_truth_table(
    enabled: bool, extended: bool, expected: SelectParam
) -> None:
    """Every ``(enabled, extended)`` pair maps to its Tk ``selectmode``.

    Same shape as the _show_param table, with one asymmetry worth its row: ``extended`` is documented as ignored when ``enabled`` is False, so (False, True) must fold to "none" rather than "extended" — that row is the one a naive two-branch implementation would get wrong.
    """
    assert select_param(enabled, extended) == expected


@pytest.mark.parametrize(
    ("word", "char", "expected"),
    [
        (True, True, "char"),
        (True, False, "word"),
        (False, True, "char"),
        (False, False, "none"),
    ],
)
def test_wrap_param_folds_the_full_truth_table(
    word: bool, char: bool, expected: Literal["none", "char", "word"]
) -> None:
    """Every ``(wrap_word, wrap_char)`` pair maps to its Tk ``wrap`` literal.

    The precedence is the asymmetry here: ``wrap_char`` wins, so both rows carrying it fold to "char" whatever ``wrap_word`` says, and (True, True) is the one an implementation testing ``word`` first would answer "word" to. "none" is Tk's real spelling of "do not wrap" and the only setting a horizontal scrollbar can scroll, so it is asserted literally for the same reason the empty string is in the _show_param table. The expected values are annotated with the literal rather than a project alias because this fold, unlike the other two, has no published return type to import.
    """
    assert _wrap_param(word, char) == expected
