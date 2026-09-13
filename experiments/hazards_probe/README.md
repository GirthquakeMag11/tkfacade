# hazards_probe

Re-creates the tkinter hazards that carried no other witness, one check
per claim, so `hazards/tkinter.md` can point at a re-runnable record
rather than an assertion. Pure `tkinter`; nothing here imports tkfacade.

## Running it

```sh
xvfb-run -a uv run python -m experiments.hazards_probe.probe
```

Every check prints its verdict; the exit status is the number that
failed. Expectations are the behaviour witnessed on the build below; a
FAIL on another build is a finding needing a re-run on that platform.

## Where this was measured

Tcl/Tk 9.0.3, `tk windowingsystem` = x11, CPython 3.14, under Xvfb with
no window manager.

## Findings

- **A `name=` path is reissued, and generated names restart per master.**
  Confirmed: `name="fixed"` hands a successor the same string a destroyed
  widget held, generated names stay distinct within one master, and a
  rebuilt master starts its child counters over.
- **Boolean queries answer `int`, not `bool`.** `winfo_ismapped()` reads
  back `1` (an `int`), so `is True` is False on a mapped widget. Confirmed.
- **Classic pane methods are present but refused.** `ttk.PanedWindow`
  inherits `tkinter.PanedWindow` and carries `paneconfigure`; the Tcl
  command answers `bad command "paneconfigure"`. Confirmed.
- **`insert` refuses one past the last pane.** Not reproduced: on
  Tk 9.0.3 `insert(3, …)` appends rather than raising. The entry in
  `hazards/tkinter.md` no longer holds and was removed.

## What went to `hazards/tkinter.md`

Three of the four checks are confirmed and now cite this probe; the
fourth was dropped as no longer reproducible on this build.
