"""Decide, by rendering, which ttk.Style options each ttk widget honours.

Run with::

    Xvfb :99 -screen 0 800x600x24 -fbdir /tmp/ttkfb &
    DISPLAY=:99 python -m experiments.ttk_style_probe.probe /tmp/ttkfb/Xvfb_screen0

For every theme, every style in :data:`~experiments.ttk_style_probe.specs.SPECS`,
and every option in :data:`~experiments.ttk_style_probe.specs.VALUES`, a widget is
built under a style that sets the option and compared against the same widget
built under a style that sets nothing. An option is honoured when the pixels
inside the widget change, or when the size it asks for changes.

Options are tried whether or not the layout's elements declare them, because
some widgets read style options no element mentions -- ``Treeview -rowheight``
and ``Entry -foreground`` among them. Both ways of setting an option are tried,
because a theme's ``style map`` beats a ``style configure`` and can defeat it
outright.

Four traps make a naive version of this quietly wrong, and each one is guarded
here:

- **The pointer is a state.** A widget under the mouse is ``active``, and every
  theme maps ``-background`` for ``active`` on the root style, which masks the
  value being tested. The pointer is warped into a corner, after the toplevel is
  mapped -- a warp before that is silently dropped.
- **Configured styles persist.** Every attempt gets a style name of its own, so
  no measurement can inherit another's leftovers.
- **A widget option beats the style.** An option the widget also carries is only
  reachable when the widget's own value is empty, so the probe retries with it
  cleared before recording nothing.
- **Some options need content.** ``-justify`` needs a second line, ``-space``
  needs an image beside the text; both are retried with that content present.

Verdicts land in ``results.json``: for each theme, style and option, whether it
was honoured and by which route, which element declares it, and what the widget
had to be doing for it to show.
"""

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from .capture import Framebuffer, count_diff
from .specs import (
    NEEDS_COMPOUND,
    NEEDS_MULTILINE,
    SPECS,
    STATES,
    VALUES,
    Spec,
)

#: States tried for options no element declares. Fewer than :data:`STATES`,
#: because that sweep is every option against every style rather than the
#: handful a layout declares.
EXTRA_STATES: list[tuple[str, ...]] = [(), ("selected",)]

Shot = tuple[bytes, tuple[int, int]]


class Probe:
    """A Tk interpreter with a mapped toplevel and the pointer parked away."""

    def __init__(self, framebuffer: Framebuffer, theme: str) -> None:
        self.framebuffer = framebuffer
        self.root = tk.Tk()
        self.root.geometry(f"{framebuffer.width}x{framebuffer.height}+0+0")
        self.root.update()  # the toplevel must be mapped before a warp will take
        self.style = ttk.Style(self.root)
        self.style.theme_use(theme)
        self.photo = tk.PhotoImage(master=self.root, width=16, height=16)
        self.photo.put("#ff0000", to=(0, 0, 16, 16))
        self.counter = 0
        self.park()

    def park(self) -> None:
        """Move the pointer off the widgets, which hover would otherwise activate."""
        self.root.event_generate(
            "<Motion>", warp=True, x=self.framebuffer.width - 2, y=self.framebuffer.height - 2
        )
        self.sync()

    def sync(self) -> None:
        """Let Tk draw, then wait for the server to have done it."""
        self.root.update()
        self.root.winfo_pointerx()  # a round trip: X has processed our drawing

    def grab(self, widget: tk.Widget) -> bytes:
        """Return the pixels inside ``widget``."""
        return self.framebuffer.region(
            widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
        )

    def close(self) -> None:
        """Tear the interpreter down."""
        self.root.destroy()


def walk(layout: list[Any], found: list[str]) -> list[str]:
    """Collect every element name in a layout tree, parents before children."""
    for name, options in layout:
        found.append(name)
        walk(options.get("children", []), found)
    return found


def declared_options(style: ttk.Style, name: str) -> dict[str, list[str]]:
    """Map each option a style's elements declare to the elements declaring it."""
    by_option: dict[str, list[str]] = {}
    for element in walk(style.layout(name), []):
        try:
            options = style.element_options(element)
        except tk.TclError:
            continue
        for option in options:
            by_option.setdefault(option, []).append(element)
    return by_option


def prepare(widget: tk.Widget, option: str, prep: str, photo: tk.PhotoImage) -> bool:
    """Give the option something to act on. False when this widget cannot."""
    try:
        if prep in ("content", "content+unshadow"):
            if option in NEEDS_COMPOUND:
                widget.configure(image=photo, compound="left")
            elif option in NEEDS_MULTILINE:
                widget.configure(text="first line\nsecond line here")
            else:
                return False
        if prep in ("unshadow", "content+unshadow"):
            # .keys() is not redundant: a Tk widget has no __contains__, so `in`
            # would fall back to __getitem__ and index it like a sequence.
            if option not in widget.keys():  # ruff: ignore[in-dict-keys]
                return False
            widget.configure(**{option: ""})
    except tk.TclError:
        return False
    return True


def draw(
    probe: Probe, spec: Spec, stylename: str, option: str, prep: str, state: tuple[str, ...]
) -> Shot | None:
    """Build the widget under ``stylename`` and return its pixels and requested size.

    Returns ``None`` when the widget cannot be prepared, or when two grabs of the
    same rendering disagree -- a focused entry blinks its insert cursor, and a
    blinking frame cannot be compared against anything.
    """
    widget = spec.build(probe.root, stylename)
    if prep != "plain" and not prepare(widget, option, prep, probe.photo):
        widget.destroy()
        return None
    widget.place(x=10, y=10, width=spec.size[0], height=spec.size[1])
    if state:
        widget.state(list(state))
    probe.sync()
    shot = probe.grab(widget)
    requested = (widget.winfo_reqwidth(), widget.winfo_reqheight())
    stable = shot == probe.grab(widget)
    widget.destroy()
    return (shot, requested) if stable else None


def render(
    context: tuple[Framebuffer, str, Probe],
    spec: Spec,
    setting: tuple[str, object] | None,
    option: str,
    prep: str,
    state: tuple[str, ...],
) -> Shot | tk.TclError | None:
    """Render the widget with ``setting`` applied before it is built.

    A style is configured first and the widget built afterwards, which is the
    order an application uses. Styles that a widget cannot prefix -- the
    panedwindow sash, which reads the fixed name ``Sash`` -- have to be
    configured under that name, so those get an interpreter of their own each
    time rather than a fresh style name.
    """
    framebuffer, theme, shared = context
    own = spec.scope == "global"
    probe = Probe(framebuffer, theme) if own else shared
    try:
        if own:
            target, widget_style = spec.configure_as, ""
        else:
            probe.counter += 1
            tag = f"Q{probe.counter}"
            target = f"{tag}.{spec.style}"
            widget_style = f"{tag}.{spec.widget_style}"
        if setting is not None:
            how, value = setting
            if value == "@PHOTO@":
                value = probe.photo
            try:
                if how == "configure":
                    probe.style.configure(target, **{option: value})
                else:
                    probe.style.map(target, **{option: [("disabled", value), ("!disabled", value)]})
            except tk.TclError as error:
                return error
        return draw(probe, spec, widget_style, option, prep, state)
    finally:
        if own:
            probe.close()


def try_option(
    context: tuple[Framebuffer, str, Probe],
    spec: Spec,
    option: str,
    values: list[object],
    attempts: list[tuple[str, tuple[str, ...]]],
    baselines: dict[tuple[str, tuple[str, ...]], Shot | tk.TclError | None],
) -> dict[str, Any]:
    """Return the verdict for one option: how it was reached, or that it was not."""
    errors: list[str] = []
    for prep, state in attempts:
        key = (prep if prep == "plain" else f"{prep}:{option}", state)
        if key not in baselines:
            baselines[key] = render(context, spec, None, option, prep, state)
        base = baselines[key]
        if not isinstance(base, tuple):
            continue
        before, before_size = base
        for how in ("configure", "map"):
            for value in values:
                shot = render(context, spec, (how, value), option, prep, state)
                if isinstance(shot, tk.TclError):
                    errors.append(str(shot))
                    continue
                if not isinstance(shot, tuple):
                    continue
                after, after_size = shot
                if len(after) != len(before):
                    continue
                pixels = 0 if after == before else count_diff(before, after)
                if pixels or after_size != before_size:
                    return {
                        "verdict": how,
                        "value": str(value),
                        "state": list(state),
                        "prep": prep,
                        "pixels": pixels,
                        "reqsize": (
                            [list(before_size), list(after_size)]
                            if after_size != before_size
                            else None
                        ),
                    }
    if errors:
        return {"verdict": "error", "error": errors[0]}
    return {"verdict": "none"}


def sweep(framebuffer: Framebuffer, only: str | None = None) -> dict[str, Any]:
    """Measure every style in every theme, and return the verdicts."""
    boot = tk.Tk()
    themes = list(ttk.Style(boot).theme_names())
    boot.destroy()

    results: dict[str, Any] = {}
    for theme in themes:
        results[theme] = {}
        wanted = [spec for spec in SPECS if not only or only == spec.style]
        # global-scope styles open their own toplevel, so they go last
        ordered = [s for s in wanted if s.scope == "probe"] + [
            s for s in wanted if s.scope == "global"
        ]
        probe = Probe(framebuffer, theme)
        for spec in ordered:
            if spec.scope == "global":
                probe.root.withdraw()  # get the shared toplevel off the screen
            context = (framebuffer, theme, probe)
            by_option = declared_options(probe.style, spec.style)
            entry: dict[str, Any] = {
                "scope": spec.scope,
                "note": spec.note,
                "layout": repr(probe.style.layout(spec.style)),
                "elements": {},
                "options": {},
            }
            for element in walk(probe.style.layout(spec.style), []):
                try:
                    entry["elements"][element] = list(probe.style.element_options(element))
                except tk.TclError:
                    entry["elements"][element] = []

            declared_attempts = [("plain", s) for s in (STATES if spec.states else STATES[:1])] + [
                (prep, ()) for prep in ("content", "unshadow", "content+unshadow")
            ]
            extra_attempts = [("plain", s) for s in EXTRA_STATES]

            baselines: dict[tuple[str, tuple[str, ...]], Shot | tk.TclError | None] = {}
            for option in sorted(VALUES):
                declared = option in by_option
                verdict = try_option(
                    context,
                    spec,
                    option,
                    VALUES[option],
                    declared_attempts if declared else extra_attempts,
                    baselines,
                )
                verdict["declared"] = declared
                verdict["elements"] = by_option.get(option, [])
                entry["options"][option] = verdict

            results[theme][spec.style] = entry
            works = [o for o, v in entry["options"].items() if v["verdict"] in ("configure", "map")]
            undeclared = [o for o in works if not entry["options"][o]["declared"]]
            print(
                f"{theme:>8} {spec.style:<26} {len(works):>2} honoured"
                f"  ({len(undeclared)} of them undeclared:"
                f" {','.join(undeclared) if undeclared else '-'})",
                flush=True,
            )
        probe.close()
    return results


def main(argv: list[str]) -> int:
    """Run the sweep and write the results beside the framebuffer."""
    if not argv:
        print(__doc__)
        return 2
    only = argv[1] if len(argv) > 1 else None
    with Framebuffer(argv[0]) as framebuffer:
        results = sweep(framebuffer, only)
    stem = "results" if not only else f"results_{only.replace('.', '_')}"
    # beside the framebuffer, which is scratch space by construction, rather
    # than in the working directory, which is somebody's checkout
    out = Path(argv[0]).with_name(f"{stem}.json")
    with out.open("w") as fh:
        json.dump(results, fh, indent=1)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
