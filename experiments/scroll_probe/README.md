# scroll_probe

The evidence probe under the scrollbar-placement item, run to answer a
prior question that item raised: **where does
scrollbar management belong** — the per-widget spec as it stands, a
container component facade in the menubar's mold, a standalone bar, or
a viewport container that scrolls anything. `probe.py` is pure
`tkinter`; nothing in it imports tkfacade. `facade.py` beside it
measures the library against the same facts. The protocol facts the
2026-08-21 rebuild rested on are in `experiments/scroll_view/` and are
cited here rather than re-measured.

## Running it

```sh
xvfb-run -a uv run python -m experiments.scroll_probe.probe
xvfb-run -a uv run python -m experiments.scroll_probe.facade
```

Every check prints its verdict; the exit status is the number that
failed. Expectations are the behaviour witnessed on the build below; a
FAIL on another build is a finding, not necessarily a fault — the
wheel checks in particular are x11 facts and should be expected to
fail elsewhere, which is the measurement.

## Where this was measured

Tcl/Tk 8.6.14, `tk windowingsystem` = x11, CPython 3.14, under Xvfb
with no window manager. Two consequences qualify the results: no
manager means no focus model beyond Tk's own, and no real input
devices means wheel *delivery* is witnessed through generated events —
what a physical wheel does on this display server is documented Tk
behaviour (buttons 4/5), not a measurement here.

## The central fact

**The scroll protocol couples callables, not widgets.** A bar's
`-command` and a widget's `-yscrollcommand` are both bare callables
with no widget identity in them: a bar in one container drives a
target in another (witnessed across nested frames), one bar's command
fans out to two targets that then track identically, and the only
thing Tk ever checks is that the Tcl command still exists when called.
Placement and ownership are therefore entirely the facade's choices —
Tk imposes no relationship a design would have to respect, and every
candidate home is mechanically possible. What discriminates between
them is lifetime and geometry, below.

## Wiring and lifetime

- **A bar drives and tracks across containers.** Parentage never
  enters the protocol; the gutter is a convention, not a mechanism.
- **One bar drives two targets.** The drive end fans out freely once
  the command is ours; the report end cannot (one option per axis —
  `hazards/tkinter.md`, *Scrolling*), so shared bars need the same fanout the
  library already runs.
- **A target outliving its bar raises into a swallowed report.** The
  converse of scroll_view's finding: the widget's next view change
  calls the dangling `-yscrollcommand`, `TclError: invalid command
  name ".!scrollbar"` lands in the callback machinery, is printed and
  swallowed, and the widget keeps working. Either death order ends in
  a silent stderr raise, so any home must unwire on both teardowns.

## The population

Which widgets speak the protocol, and on which axes, witnessed rather
than taken from the documentation: `Text`, `Listbox`, `Treeview` and
`Canvas` speak both; `Entry`, `ttk.Entry`, `Spinbox` and
`ttk.Combobox` speak x alone. The facade currently models four of the
eight (`TextBox`, `Listbox`, `Tree`, and Canvas to come); the x-only
half is unwrapped and unclaimed.

## The viewport

The canvas-window mechanism — the classic route to scrolling arbitrary
content, and what the compounding entry list (a future-version shelf item) would
ride:

- **It works, given a region.** A frame embedded by `create_window`
  scrolls once `-scrollregion` is declared from `bbox("all")`.
- **Without a region the canvas reports everything-fits.** `(0.0,
  1.0)` over content three times its height — and that pair is the
  whole auto-hide predicate, so on a bare canvas the predicate lies.
  Nothing maintains the region but the caller.
- **A `<Configure>`-synced region stays truthful through growth**, in
  the same settle that grew the content.
- **The default highlight ring skews the edge fractions.** A resting
  default canvas reports `0.00196`, never `0.0`, so an "at the top"
  comparison fails forever; `highlightthickness=0` restores the exact
  edge.
- **Events inside the viewport bypass the canvas.** An embedded
  child's bindtags are itself, its class, the toplevel and `all` — a
  canvas-level binding hears nothing over its own content, while the
  toplevel hears everything. A viewport wrapper owns exactly the
  routing problem `BaseWidget._route_events` already solves.

## The wheel

- **Delivery is per-widget, never per-focus.** A wheel button lands on
  the widget it is aimed at while another holds focus, and
  `winfo_containing` answers the pointer's widget — the two facts a
  pointer-routed wheel manager needs.
- **`<MouseWheel>` binds legally on x11 and a generated one carries
  its delta**, but real x11 devices deliver buttons 4/5 instead — the
  split the events package's `Wheel` spec documents and delegates.
  Portable wheel handling binds both routes; nothing in the library
  does yet.
- **Half the population scrolls on wheel with no bar at all.** Class
  bindings exist for `Text`, `Listbox`, `Treeview` and `TCombobox`;
  `Canvas` and `Entry` have none. So bars are not the scrolling story
  for most widgets — but the viewport's host is exactly one of the
  two widgets the wheel ignores, a second gap a viewport wrapper must
  fill by hand.

## What a facade can be built on

`facade.py` beside `probe.py` measures tkfacade against Tk. Three
checks; run it the same way.

- **Placement is nothing but the gutter cells.** A live `TextBox`'s
  bar re-gridded into the left cell — bar's cell, content's cell,
  stretch weight, the three coupled facts — keeps driving and
  tracking with the machinery none the wiser. What the placement item
  would mechanize is exactly this and no more.
- **Auto-hide is placement-blind.** `grid_remove`/`grid` round-trips
  the relocated cell exactly, so hiding needs no remembered geometry
  in any gutter.
- **`AbstractScrollable` transfers to a canvas viewport.** The
  smallest subclass — a ringless canvas, an embedded frame, a
  `<Configure>`-synced region — navigates, reports and tracks through
  the existing machinery unchanged. The mixin already *is* a viewport
  wrapper short of the region maintenance and the wheel.

## What went to `hazards/tkinter.md`

Four findings met that file's bar and were filed under *Scrolling*:
the converse lifetime raise (a target outliving its bar), the
region-less canvas's everything-fits lie, the highlight ring's edge
skew, and the wheel's delivery-and-population facts. This README
keeps the whole record, the unsurprising rows included.

## Unmeasured

- Real-device wheel delivery (no devices under Xvfb): that x11
  hardware speaks buttons 4/5 and never `<MouseWheel>` is documented
  Tk behaviour, witnessed here only as bindability.
- The win32 and macOS wheel story (`<MouseWheel>` deltas, their
  signs and magnitudes) — untested.
- Keyboard scrolling (Prior/Next class bindings) — untouched.
- `ttk.Scrollbar.identify`/`delta`/`fraction` — the drag-geometry
  methods nothing yet needs.
- Horizontal wheel (buttons 6/7) — rejected by the floor Tk, per the
  events package's own note.
- Scrolling performance at depth (thousands of embedded children) —
  the viewport was witnessed for mechanism, not for scale.
