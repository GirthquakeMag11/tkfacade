"""Measure the selection and insert-cursor options of Entry, Combobox and Spinbox.

Run with::

    DISPLAY=:99 python -m experiments.ttk_style_probe.entry_family /tmp/ttkfb/Xvfb_screen0

The main sweep cannot see these. Selection colours need a selection to exist, the
insert cursor only appears while the widget holds the focus, and a focused entry
blinks that cursor -- which makes the sweep's two-grabs-must-agree check throw
every frame away. Here the widget is given a selection and the focus, and the
cursor options are judged across a whole blink cycle instead of one frame.

Two modes are measured for the selection colours, because they differ: with a
selection alone, and with a selection while focused. In ``clam`` the root style
maps ``-selectbackground`` and ``-selectforeground`` for ``!focus``, so an
unfocused entry ignores a ``configure`` on its own style and needs a ``map``.

Verdicts land in ``entry_family.json``, which
:mod:`~experiments.ttk_style_probe.tables` folds into the sweep's results.
"""

import json
import sys
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import Any

from .capture import Framebuffer

WIDGETS: list[tuple[Callable[..., ttk.Entry], str]] = [
    (ttk.Entry, "TEntry"),
    (ttk.Combobox, "TCombobox"),
    (ttk.Spinbox, "TSpinbox"),
]
SELECTION: list[tuple[str, object]] = [
    ("selectbackground", "#ff00ff"),
    ("selectforeground", "#ffff00"),
    ("selectborderwidth", 5),
]
CURSOR: list[tuple[str, object]] = [("insertcolor", "#ff0000"), ("insertwidth", 8)]


class Bench:
    """A Tk interpreter for building one entry-like widget at a time."""

    def __init__(self, framebuffer: Framebuffer) -> None:
        self.framebuffer = framebuffer
        self.root = tk.Tk()
        self.root.geometry(f"{framebuffer.width}x{framebuffer.height}+0+0")
        self.root.update()
        self.style = ttk.Style(self.root)
        self.root.event_generate(
            "<Motion>", warp=True, x=framebuffer.width - 2, y=framebuffer.height - 2
        )
        self.root.update()

    def sync(self) -> None:
        self.root.update()
        self.root.winfo_pointerx()

    def build(self, cls: Callable[..., ttk.Entry], stylename: str, mode: str) -> ttk.Entry:
        """Place a widget with the content and focus that ``mode`` calls for."""
        widget = cls(self.root, style=stylename) if stylename else cls(self.root)
        widget.place(x=20, y=20, width=240, height=40)
        if cls is ttk.Spinbox:
            widget.set("value here")
        else:
            widget.insert(0, "entry text")
        if mode in ("selection", "selection+focus"):
            widget.selection_range(0, 5)
        if mode in ("selection+focus", "cursor"):
            widget.icursor(4)
            widget.focus_set()
        self.sync()
        return widget

    def pixels(self, widget: tk.Widget) -> bytes:
        return self.framebuffer.region(
            widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
        )

    def frames(self, widget: tk.Widget, count: int = 12, gap: int = 110) -> set[bytes]:
        """Grab across a blink cycle, so a flashing cursor is caught in some frame."""
        seen = set()
        for _ in range(count):
            self.sync()
            seen.add(self.pixels(widget))
            self.root.tk.call("after", gap)
        return seen

    def close(self) -> None:
        self.root.destroy()


def measure(framebuffer: Framebuffer) -> dict[str, Any]:
    """Return the verdicts for every theme, widget, option and mode."""
    bench = Bench(framebuffer)
    results: dict[str, Any] = {}
    for theme in bench.style.theme_names():
        bench.style.theme_use(theme)
        results[theme] = {}
        for cls, base in WIDGETS:
            entry: dict[str, dict[str, str]] = results[theme].setdefault(base, {})
            for mode in ("selection", "selection+focus"):
                for option, value in SELECTION:
                    verdict = "none"
                    for how in ("configure", "map"):
                        name = f"{theme}{cls.__name__}{option}{how}{mode}.{base}"
                        if how == "configure":
                            bench.style.configure(name, **{option: value})
                        else:
                            bench.style.map(
                                name, **{option: [("disabled", value), ("!disabled", value)]}
                            )
                        plain = bench.build(cls, "", mode)
                        reference = bench.pixels(plain)
                        plain.destroy()
                        styled = bench.build(cls, name, mode)
                        got = bench.pixels(styled)
                        styled.destroy()
                        if got != reference:
                            verdict = how
                            break
                    entry.setdefault(option, {})[mode] = verdict
            for option, value in CURSOR:
                name = f"{theme}{cls.__name__}{option}.{base}"
                bench.style.configure(name, **{option: value})
                plain = bench.build(cls, "", "cursor")
                reference = bench.frames(plain)
                plain.destroy()
                styled = bench.build(cls, name, "cursor")
                got = bench.frames(styled)
                styled.destroy()
                entry.setdefault(option, {})["cursor"] = "configure" if got - reference else "none"
    bench.close()
    return results


def main(argv: list[str]) -> int:
    """Run the measurement and write the verdicts beside the framebuffer."""
    if not argv:
        print(__doc__)
        return 2
    with Framebuffer(argv[0]) as framebuffer:
        results = measure(framebuffer)
    out = Path(argv[0]).with_name("entry_family.json")
    with out.open("w") as fh:
        json.dump(results, fh, indent=1)
    for theme, styles in results.items():
        print(f"--- {theme} ---")
        for base, options in styles.items():
            for option, modes in options.items():
                shown = "  ".join(f"{mode}={verdict}" for mode, verdict in modes.items())
                print(f"  {base:<10} -{option:<18} {shown}")
    print("\nwrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
