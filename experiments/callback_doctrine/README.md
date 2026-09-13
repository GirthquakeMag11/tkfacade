# callback_doctrine

Witnesses how Tk delivers callbacks — the facts the delivery picture
rests on, feeding the Observability and Events design. Those facts say
what thread a callback runs on, what a raise inside one does, and what a
callback may do to the library that called it; each check in
`probe.py` pins one fact those answers rest on, per delivery route: an
event binding, a variable trace, an `after` job, a `-command` callback.
Nothing here imports tkfacade — the library's own delivery primitive
(`BaseWidget.submit`) is pinned by the suite in `tests/test_submit.py`.

Four of the findings met the bar for `hazards/tkinter.md` and are filed there
under *Bindings* and *Variables*; this README keeps the whole table,
the unsurprising rows included, because the delivery picture cites them
all.

## Running it

```sh
xvfb-run -a uv run python -m experiments.callback_doctrine.probe
```

Every check prints its verdict; the exit status is the number that
failed. The expectations coded in the checks are the behavior witnessed
below, so a different Tk build or platform can be held against them
without re-reading anything — a failure is a finding, not necessarily a
fault. The Windows run this record waited on is documented in
`Windows Run.md` beside this file: all fifteen checks agree with the
findings below (Tk 8.6.14, threaded Tcl, win32, CPython 3.14.3), so
the findings stand witnessed on both development platforms.

## Findings — Tk 8.6.14, threaded Tcl, X11 (Linux), 2026-08-19

Witnessed identically on win32 (Windows 11, 2026-08-19) — see
`Windows Run.md` for that run's record. Everything below holds on both.

Delivery thread:

- An event handler, a variable trace, and an `after` job all run on the
  interpreter's own (mainloop) thread.
- A `set()` from a worker thread blocks while its trace runs on the
  mainloop thread — threaded Tcl marshals the call; the callback never
  runs on the worker.

Exceptions:

- A raise in any route — handler, trace, `-command` — is routed to
  `report_callback_exception` and swallowed; the loop keeps running and
  the triggering call (`event_generate`, `set()`, `invoke()`) returns
  normally.
- A raising write trace does not undo or veto the write: the value has
  already changed, and the setter is told nothing (`hazards/tkinter.md`,
  *Variables*).
- A raise in one handler spares the handlers added after it with
  `add="+"` and the rest of the bindtag chain; a raise in one trace
  spares the variable's other traces.

Reentry:

- A write made inside any write trace fires none of the variable's
  traces: no recursion, and no visibility either — the other watchers
  never see the inner write (`hazards/tkinter.md`, *Variables*). Traces fire
  most-recently-added first.
- A handler destroying its own widget finishes its own body; the
  handlers bound after it are silently dropped (`hazards/tkinter.md`,
  *Bindings*). A second `destroy()` is a no-op and `<Destroy>` fires
  once.
- `update()` inside a callback dispatches other callbacks within the
  outer callback's frame: the loop is genuinely reentrant.

Delivery:

- `event_generate` is silently dropped until the widget's X window
  exists; `winfo_id()` alone creates it and the same generate then
  delivers. Mapping is not the boundary — corrected 2026-08-20 from
  this probe's original never-mapped reading, after the facade's own
  tests refuted it (`hazards/tkinter.md`, *Bindings*; the sharper legs are in
  `../event_bind/`'s findings). The Windows run on record predates the
  rename of this check; the later Windows run beside this file re-ran
  all fifteen on win32 and they agree, the renamed check included —
  win32 draws the delivery boundary at window creation too.
