# scroll_view

The evidence probe under the scrollbar item. The item must decide what
a scrollbar wrapper is *for*,
given that `ttk.Scrollbar` carries almost no options of its own and
that `TextBox` and `Tree` already own and wire their bars correctly.
This probe pins the protocol facts that decision rests on. The last
check imports the library, because the fact it pins is about
tkfacade's own settle machinery rather than about Tk.

## Running it

```sh
xvfb-run -a uv run python -m experiments.scroll_view.probe
```

Every check prints its verdict; the exit status is the number that
failed. Expectations are the behavior witnessed on Tk 8.6.14 (threaded
Tcl, X11), CPython 3.14; a FAIL on another build is a finding needing a
re-run on that platform.

## Findings — 2026-08-21

The protocol, both ends:

- **The drive end is stringly typed.** A scrollbar's `-command`
  receives `('scroll', '1', 'units')` — Tk's words *and its numbers* as
  strings.
- **The report end is stringly typed too.** A widget's
  `-yscrollcommand` receives `('0.0', '0.025')`, a pair of strings. So
  the conversion has two boundaries, not one, and
  a wrapper that converts only where a caller looks would still be
  handing Tk's strings to itself.
- **`ttk.Scrollbar` carries six options** — `class`, `command`,
  `cursor`, `orient`, `style`, `takefocus` — of which two mean
  anything. A wrapper's worth here cannot come from the options it
  covers; it has to come from the relationship it names.

What the numbers mean:

- **`(0.0, 1.0)` is Tk's everything-fits signal.** Content shorter
  than its widget reports the full span, and content that scrolls
  reports less. That pair is the whole of the auto-hide predicate.
- **`moveto` past the end clamps silently.** Asking for `9.0` settles
  the view at its maximum — here `(0.975, 1.0)` — with no raise. Tk
  treats nonsense as a request to go as far as possible, which leaves
  refusing it to the facade.

Wiring and lifetime:

- **One scroll-command option, several listeners.** Tk offers exactly
  one `-yscrollcommand` per widget, so a second scrollbar silently
  replaces the first one's tracking unless something fans out. Two
  bars driven through one fanout track identically — the same fanout
  the library already runs for events and observables.
- **A bar outliving its target raises inside a Tk callback.** Driving
  a destroyed target raises `TclError: invalid command name ".!frame.!text"`;
  reached through the bar's own `-command`, that raise lands where Tk
  prints and swallows it. The result is a scrollbar that looks alive
  and does nothing.
- **Hiding a bar is reversible for free.** `grid_remove()` unmaps it
  and a bare `grid()` restores row, column and sticky exactly, so
  auto-hide needs no remembered geometry.

Against today's observable:

- **A two-way wiring converges rather than ringing.** With the
  observable driving `yview` and the widget's report adopting back, a
  reachable write notifies once (`[0.5]`) and settles there. An
  out-of-range write notifies `[9.0, 0.975]` and settles at `0.975`,
  where the widget actually sits: the equal-write drop stops the
  ping-pong, and the settle machinery delivers the truth last. It
  works — but a watcher sees the impossible value first, which is the
  argument for refusing out-of-range at the facade boundary rather
  than letting Tk's clamp be the only correction.
