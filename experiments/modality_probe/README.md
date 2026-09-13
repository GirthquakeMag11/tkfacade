# Modality probe

What the `Dialog` foundation can
rely on, witnessed under real conditions before anything is designed
on top of it. Run with:

```
xvfb-run -a uv run python -m experiments.modality_probe.probe
```

Eight checks, one per claim; the exit status is the number that
failed. Witnessed on Tk 8.6, x11, under Xvfb with no window manager,
with `xdotool` (XTEST) injecting the pointer events a grab actually
routes.

## Findings

- **Tk's waits are a nested event loop, and they genuinely block the
  caller.** `wait_window` parks the calling frame while `after`
  callbacks, bindings, and generated events keep running — the exact
  mechanic a synchronous `dialog.*` call needs to block its caller
  without freezing the application.
- **Nested waits unwind last-in, first-out.** An outer wait whose
  condition is met while an inner wait is still parked does not
  return until the inner one finishes. Dialog-over-dialog is
  therefore legal but stack-shaped: the second dialog must resolve
  before the first call can return, whatever order their results
  arrive in.
- **A grab redirects; it does not drop.** With a grab held, a real
  click aimed at another of the application's windows is delivered to
  the *grab holder* (which hears it alongside its own clicks), and
  the other window hears nothing. Interpreter-level `bind_all`
  bindings — the input observer's stratum — still see key events
  during the grab.
- **The async core's crossing lands mid-wait.** Under a running
  mainloop, a worker thread's `after(0, ...)` — the library's own
  off-thread marshalling, `Observable`'s included — fires while the
  main thread sits in `wait_window`. Coroutines keep running and
  their completions can end a dialog. (Under an `update()`-pumped
  bench with no mainloop, the same call raises `RuntimeError: main
  thread is not in main loop` — tkinter's thread wall, already
  documented on the observable as deliberately loud. The suite's
  pump-based tests must drive dialog completion from the main thread
  or run a real mainloop for that claim.)
- **Tk's file and color dialogs are Tk-drawn on x11 and open
  headless.** `askopenfilename` posts `.__tk_filedialog` (class
  `TkFDialog`), `askcolor` posts `.__tk__color` (`TkColorDialog`) —
  ordinary Tk windows under the parent, pumping the caller's `after`
  callbacks while posted. Their cancel procs
  (`::tk::dialog::file::CancelCmd`, `::tk::dialog::color::CancelCmd`)
  dismiss them programmatically: the file dialog then returns `()`
  and the color chooser `(None, None)` — the empty shapes a typed
  facade must normalize.
- **The file dialog window outlives its call.** After a cancel,
  `.__tk_filedialog` persists — withdrawn, kept by Tk for reuse — so
  "no foreign toplevels" is not an invariant a suite can assert once
  any file dialog has been shown.
- **Destroying a posted dialog is a cancellation, not a leak of the
  caller.** Tk's file dialog completes its wait when its window is
  destroyed; the caller returns promptly with the empty answer. A
  `Dialog` design should preserve the same property: completion bound
  to destruction, so abrupt teardown resolves the future rather than
  abandoning a parked caller.
- **Without a window manager,** `transient` reads back, `focus_force`
  lands (helped by an XTEST `windowfocus`), a grab reads back through
  `grab_current`, and destroying the grab holder leaves no grab —
  teardown needs no explicit `grab_release` on the death path.

## Instrument traps (for anyone re-running or extending)

- **`tk.call` answers Tcl lists as Python tuples.** `str()` on such a
  result yields a *tuple repr*, and splitting it produces garbage
  paths like `('.__tk_filedialog',)`. A first harness fed those to
  `destroy`, the destroy never landed, and the still-posted dialog
  read as "destroying a dialog leaves the caller parked forever" — a
  finding that survived until the instrument was checked. Use
  `tk.splitlist()`. The corrected check witnesses the opposite fact.
- **tkinter's `winfo_children` cannot see the Tk-drawn dialogs.**
  They are created by Tcl library code with no tkinter widget object,
  so enumerate them with raw `winfo children` through `splitlist`.
- **The thread-crossing check needs a real `mainloop`.** Driving it
  from an `update()` pump witnesses only the thread wall's refusal,
  not the crossing.
