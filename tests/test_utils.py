"""Edge cases of the shared helpers in ``tkfacade._utils``.

The doctests already pin each helper's headline behavior and run as
part of this suite via ``--doctest-modules``; the tests here cover only
the boundaries the doctests leave open, and restate nothing.
"""

from tkfacade._utils import format_time, intersects, to_snake_case, to_title_case


def test_intersects_containment_counts_as_overlap() -> None:
    """A box wholly inside another intersects it, from either argument.

    Containment shares no edge crossing with the doctests' partial-overlap case, and a comparison chain accidentally requiring each box to cross the other's boundary would fail exactly here. Both argument orders are asserted because the implementation is four asymmetric comparisons whose symmetry is a property, not a given.
    """
    outer = (0, 0, 100, 100)
    inner = (10, 10, 20, 20)

    assert intersects(outer, inner)
    assert intersects(inner, outer)


def test_intersects_diagonal_disjoint_is_false() -> None:
    """Boxes separated on both axes do not intersect.

    The doctests cover abutting boxes (one shared edge, False); this pins the fully-disjoint quadrant case, where a bug that ORs the per-axis checks instead of ANDing them would still answer False for abutting boxes yet True for nothing — the diagonal case is the one that fails under an inverted combinator.
    """
    assert not intersects((0, 0, 10, 10), (20, 20, 30, 30))


def test_format_time_negative_reads_as_zero() -> None:
    """A negative duration renders as ``0:00``.

    The clamp is documented ("a clock running backwards means the caller has a bug, and a readout is not where to report it") but not doctested. Without it, ``divmod`` on a negative total would render nonsense like ``-1:59:55`` in a control bar rather than raising anywhere visible.
    """
    assert format_time(-5.0) == "0:00"


def test_format_time_hour_boundary_switches_format() -> None:
    """The H:MM:SS form appears exactly at the first full hour.

    One second either side of the format switch: the doctests show one example of each shape but not the boundary between them, and an off-by-one in the hours test (``>=`` vs ``>`` on the divmod result) flips only these two values.
    """
    assert format_time(3599.0) == "59:59"
    assert format_time(3600.0) == "1:00:00"


def test_to_title_case_keeps_digit_led_tokens() -> None:
    """A token starting with a digit passes through untouched.

    The digit-led branch is documented but undoctested, and it is the one branch where ``str.title`` would misbehave — ``"2nd".title()`` is "2Nd" — so the fallback to the raw token is what this pins.
    """
    assert to_title_case("chapter_2nd_part") == "Chapter 2nd Part"


def test_to_snake_case_does_not_split_case_boundaries() -> None:
    """An intra-token case boundary casefolds without splitting.

    The docstring calls this out explicitly ('``"FirstName"`` is one token') because it is the surprising half of the contract — most snake-casers split camelCase. The mixed input pins both halves at once: the space still separates, the case boundary still does not.
    """
    assert to_snake_case("FirstName Last") == "firstname_last"


def test_case_converters_keep_non_ascii_letters() -> None:
    """Non-ASCII letters are token members, not separators.

    _tokenize matched [A-Za-z0-9]+, so é and ß counted as separators and vanished: "café_bar" → "Caf Bar", "Straße" → "stra_e" — character loss the docstrings' "alphanumeric runs" never licensed, mangling any accented tree-column heading. "strasse" rather than "straße" is casefold's documented doing, not the tokenizer's: ß casefolds to ss, and asserting it pins that the token reached casefold whole.
    """
    assert to_title_case("café_bar") == "Café Bar"
    assert to_snake_case("Straße") == "strasse"


def test_case_converters_keep_combining_marks() -> None:
    """Decomposed input neither loses its marks nor splits at them.

    The regex fix kept precomposed non-ASCII letters but a combining mark is outside ``\\w``, so NFD text — the normal form of macOS filenames — still lost its accents and split words at them: "cafés" came out "Cafe S". The tokenizer now normalizes to NFC and keeps a mark with the run it follows. The first two assertions pin the NFD input arriving as its composed spelling; the x-circumflex has no composed form at all, so the third pins the mark surviving on its own merits rather than by composition.
    """
    assert to_title_case("cafés_menu") == "Cafés Menu"
    assert to_snake_case("Café Bar") == "café_bar"
    assert to_title_case("x\u0302_files") == "X\u0302 Files"
