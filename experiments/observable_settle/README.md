# observable_settle

The prototype and probe under the observability design. The architecture
was ruled 2026-08-20 — the value is Python-held, a `tk.Variable` attaches
as transport — and `probe.py`'s `PrototypeObservable` is the minimal
reference of the machinery that ruling commits to: a watcher list with
per-watcher last-seen bookkeeping, a settle loop capped at eight
rounds, equal-write dropping, and a two-way transport sync. It is the
machinery's proof, not the design; everywhere a policy is still open
the prototype deliberately records instead of deciding.

## Running it

```sh
xvfb-run -a uv run python -m experiments.observable_settle.probe
```

Every check prints its verdict; the exit status is the number that
failed. The settle-machinery checks are pure Python and have no
platform to vary with; the Tk-facing checks (transport sync, trace
echo, interpreter lifetime, the unreadable typed variable) carry
expectations witnessed on Tk 8.6.14 under X11 — and, since the later
Windows re-run, under win32 too:
all eleven checks agree on both development platforms.

## Findings — 2026-08-20

Consistency (the floor this design holds):

- A clamping watcher's write-back settles every sibling: whoever runs
  after the correction is called with the corrected value, whoever ran
  before it is called again. Registration order decides which
  intermediates a watcher sees — a sibling registered after the
  corrector never sees the uncorrected value at all (natural
  coalescing) — and never affects the settled value reaching everyone.
- An equal write notifies nobody, and that same rule is what makes the
  transport echo silent: Python-side writes land in the variable once,
  widget-side writes land in Python once, and a widget-side write a
  watcher clamps ends with the *variable* holding the clamp — the
  Entry-plus-normalizer case the raw-trace hazard makes impossible.

Fights (discovered, not designed):

- The per-watcher last-seen dedupe converges every fight whose values
  repeat: two watchers overwriting each other's values (ping/pong)
  settle without reaching the cap, because each fighter only reacts to
  values it has not seen. Only a fight minting fresh values every round
  (a counter) diverges; it is cut off at the cap with the fighter
  lagging its own last write — consistency at a true divergence is
  unattainable by definition, which is why what-to-do-at-the-cap is a
  design ruling the prototype refuses to take.

Transport lifetime:

- Detach is clean: the variable is left traceless and inert, and a
  re-attach seeds a fresh variable from the Python value and tracks on.
- `root.destroy()` does not kill the transport: Tcl variables are
  interpreter-level, the interpreter outlives the widget tree, and a
  tkinter `Variable` holds the Tkapp object — so an attached transport
  keeps its interpreter alive and ghost writes land silently
  (`hazards/tkinter.md`, *Variables*). The design guards its pushes
  regardless, but "root destroyed, therefore transport dead" is wrong
  in both directions.
- The widget route can put text a typed variable cannot read into that
  variable; the trace fires first and the typed `get()` raises after
  (`hazards/tkinter.md`, *Variables*). The design's inbound sync reads
  under a guard and keeps the last good value.

## The design — settled 2026-08-20

The rulings, in the order they were made: the value is **Python-held**,
with a `tk.Variable` as attachable transport; v1 covers the **four
Tk-native kinds** (str, bool, int, float), the codec seam for arbitrary
types named but not built; delivery is the **witnessed per-watcher
settle semantic**; a divergence at the cap is **reported through the
`Root` error hook with the last value kept**; `watch()` **calls the new
watcher immediately** with the current value; a watcher receives **the
new value only**. Class names below (`ObservableStr` and kin) are
working names — final naming is settled on contact with the road.

**The contract.** An observable is constructed from a plain initial
value, with no root required and no tkinter type in sight. `get()`
answers the value; assigning through `set()` (or a property — the
implementation's call) notifies watchers under the settle semantic: each watcher is
called with the value current at its turn and re-called until it has
seen the value the write settled at, a write equal to the current value
notifies nobody, and a fight that mints fresh values is cut off at the
settle cap and reported through the `Root` hook, the last value kept.
`watch(watcher)` calls the watcher immediately with the current value
and returns a cancellation handle — the handle's exact shape is settled
alongside the events design, which needs the symmetric object for
bindings. Observables are mainloop-affine, per the callback rules: a
cross-thread write goes through `submit`, and v1 documents rather than
enforces this, matching Tk's own posture.

**The transport.** A widget built with (or assigned) an observable asks
it for a transport on the widget's interpreter; the observable creates
the matching `tk.Variable` seeded with the current value, registers its
one inbound trace, and hands the variable over for the widget's
`-textvariable`/`-variable` option. One transport serves every widget
on that interpreter. The equal-write drop is the echo suppression in
both directions, as witnessed. Two facts filed in `hazards/tkinter.md` shape
the lifecycle: a `Variable` pins its interpreter, so the observable
counts the widgets riding the transport — each deregisters through its
construction-time `<Destroy>` bind, safe from the swallow — and detaches the
transport when the count hits zero, unpinning the interpreter; and the
widget route can fill a typed variable with unreadable text, so the
inbound sync reads under a `TclError` guard and keeps the last good
value — defensively, since the v1 pairing table never binds a non-str
observable to a free-text widget: entries and headings pair with str,
scales and progress bars with float and int (widgets that only write
valid numbers), check and choice state with bool and str.

**The paper-fit** — every public Variable site on the audit's
allowlist, plus the queue's next widgets:

| Site | Becomes |
|---|---|
| `Entry.text_variable`, `TitleEntry`'s pair | `ObservableStr`, exposed and acceptable at construction |
| Progress bars' `variable=` | `ObservableFloat` / `ObservableInt` behind `current` |
| `Menu.add_checkbox(variable=)` | `ObservableBool` |
| `Menu.add_choice(group=)` | one shared `ObservableStr`, selection as value |
| `TreeColumnHeading.textvariable`, `TreeColumnSpec.heading_textvar` | `ObservableStr` |
| `MediaVariables` (ten) | a bundle of the four kinds, same names |
| Paper `Checkbutton` / `Radiobutton` / `Scale` | `ObservableBool` / shared `ObservableStr` / `ObservableFloat` |

`Table`'s internal sort plumbing stays internal and converts or not at
the implementation's discretion — the audit tracks the public surface. The design
depends on the `Root` error hook as its divergence channel; the
implementation lands the hook before or with the first retrofit. What
the implementation is expected to iterate on contact: final names,
property-versus-method spelling of reads and writes, the handle's shape
(jointly with the events design), and the exact seam the arbitrary-type
codec enters through.
