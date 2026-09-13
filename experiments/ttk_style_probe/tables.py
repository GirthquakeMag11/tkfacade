"""Turn the measured results into the markdown tables the note carries.

Run with::

    python -m experiments.ttk_style_probe.tables results.json > tables.md

``entry_family.json`` is folded in when it sits beside the results file, because
the selection and insert-cursor options are measured separately -- see
:mod:`~experiments.ttk_style_probe.entry_family` for why the sweep cannot see them.
"""

import json
import sys
from pathlib import Path
from typing import Any

THEMES = ["clam", "alt", "default", "classic"]
CELL = {"configure": "yes", "map": "map", "none": "no", "error": "err"}

#: Widgets in the order the note presents them, with the sub-styles each owns.
GROUPS: list[tuple[str, list[str]]] = [
    ("Button", ["TButton", "Toolbutton"]),
    ("Checkbutton and Radiobutton", ["TCheckbutton", "TRadiobutton"]),
    ("Menubutton", ["TMenubutton"]),
    ("Entry", ["TEntry"]),
    ("Combobox", ["TCombobox"]),
    ("Spinbox", ["TSpinbox"]),
    ("Frame", ["TFrame"]),
    ("Label", ["TLabel"]),
    ("Labelframe", ["TLabelframe", "TLabelframe.Label"]),
    ("Notebook", ["TNotebook", "TNotebook.Tab"]),
    (
        "Panedwindow",
        ["Horizontal.TPanedwindow", "Vertical.TPanedwindow", "Horizontal.Sash", "Vertical.Sash"],
    ),
    ("Progressbar", ["Horizontal.TProgressbar", "Vertical.TProgressbar"]),
    ("Scale", ["Horizontal.TScale", "Vertical.TScale"]),
    ("Scrollbar", ["Horizontal.TScrollbar", "Vertical.TScrollbar"]),
    ("Separator", ["Horizontal.TSeparator", "Vertical.TSeparator"]),
    ("Sizegrip", ["TSizegrip"]),
    (
        "Treeview",
        ["Treeview", "Treeview.Heading", "Treeview.Item", "Treeview.Cell", "Treeview.Row"],
    ),
]

#: Why an option needed more than a plain widget in its plain state to show itself.
CAVEATS = {
    (
        "prep",
        "content+unshadow",
    ): "is taken from the style only while the widget's own `-{o}` is empty",
    ("prep", "content"): (
        "needs content that shows it (a second line of text, or an image beside the text)"
    ),
    ("state", "focus"): "changes the rendering only while the widget has focus",
    ("state", "selected"): "changes the rendering only in the `selected` state",
}

_extra_caveats: dict[tuple[str, str], str] = {}


def source(data: dict[str, Any], style: str, option: str) -> str:
    """Name the elements that declare an option, or 'widget' when none does."""
    seen: set[str] = set()
    out: list[str] = []
    for theme in THEMES:
        entry = data[theme].get(style)
        if not entry:
            continue
        for element in entry["options"].get(option, {}).get("elements") or []:
            short = element.split(".", 1)[-1]
            if short not in seen:
                seen.add(short)
                out.append(short)
    return ", ".join(out) if out else "widget"


def caveats(data: dict[str, Any], style: str, options: list[str]) -> dict[str, str]:
    """Return the conditions attached to each option that has one."""
    out: dict[str, str] = {}
    for option in options:
        if (style, option) in _extra_caveats:
            out[option] = _extra_caveats[style, option]
            continue
        for theme in THEMES:
            verdict = data[theme].get(style, {}).get("options", {}).get(option, {})
            if verdict.get("verdict") not in ("configure", "map"):
                continue
            if verdict.get("prep") and verdict["prep"] != "plain":
                out[option] = CAVEATS["prep", verdict["prep"]].replace("{o}", option)
            elif verdict.get("state"):
                key = ("state", verdict["state"][0])
                if key in CAVEATS:
                    out[option] = CAVEATS[key]
    return out


def table(data: dict[str, Any], style: str) -> tuple[str | None, list[str], dict[str, str]]:
    """Build one style's table, its inert options, and its caveats."""
    rows: dict[str, dict[str, str]] = {}
    for theme in THEMES:
        entry = data[theme].get(style)
        if not entry:
            continue
        for option, verdict in entry["options"].items():
            rows.setdefault(option, {})[theme] = verdict["verdict"]
    live = sorted(o for o, r in rows.items() if any(v in ("configure", "map") for v in r.values()))
    if not live:
        return None, [], {}
    lines = [
        "| option | clam | alt | default | classic | read by |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for option in live:
        cells = " | ".join(CELL.get(rows[option].get(t, "none"), "?") for t in THEMES)
        lines.append(f"| `-{option}` | {cells} | {source(data, style, option)} |")
    inert = sorted(
        o
        for o, _ in rows.items()
        if o not in live
        and any(data[t][style]["options"][o].get("declared") for t in THEMES if style in data[t])
    )
    return "\n".join(lines), inert, caveats(data, style, live)


def merge_entry_family(data: dict[str, Any], path: Path) -> None:
    """Fold the separately measured selection and cursor verdicts into the results."""
    if not path.exists():
        return
    with path.open() as fh:
        extra = json.load(fh)
    for theme, styles in extra.items():
        for style, options in styles.items():
            for option, modes in options.items():
                entry = data[theme][style]["options"].setdefault(option, {})
                entry["verdict"] = modes.get("selection+focus") or modes.get("cursor")
                entry.setdefault("declared", False)
                entry.setdefault("elements", [])
                if option.startswith("select") and modes.get("selection") == "map":
                    note = "is overridden while the widget does not have focus, in "
                    have = _extra_caveats.get((style, option), note)
                    themes = sorted({*have.removeprefix(note).split(", "), theme} - {""})
                    _extra_caveats[style, option] = note + ", ".join(themes)


def main(argv: list[str]) -> int:
    """Print the tables for every group."""
    results = Path(argv[0] if argv else "results.json")
    with results.open() as fh:
        data = json.load(fh)
    merge_entry_family(data, results.with_name("entry_family.json"))
    for title, styles in GROUPS:
        print(f"\n### {title}\n")
        for style in styles:
            if style not in data[THEMES[0]]:
                continue
            body, inert, notes = table(data, style)
            print(f"**`{style}`**\n")
            print(body if body else "_No option had any observable effect._")
            if notes:
                print()
                for option in sorted(notes):
                    print(f"- `-{option}` {notes[option]}.")
            if inert:
                listed = ", ".join(f"`-{o}`" for o in inert)
                print(
                    f"\nDeclared by an element of this layout, and inert in every theme: {listed}."
                )
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
