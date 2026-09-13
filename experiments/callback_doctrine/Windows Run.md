# Windows Run

A handoff in two halves: the top half asks an agent working in the
project's Windows environment to run the callback-doctrine probe and
says exactly what to bring back; the bottom half — *Findings* — is
where that agent records the results, editing this file in place. When
the findings are filled in, this document's job is done: the session
that requested the run folds the results into the callback-delivery
picture and into `hazards/tkinter.md` where they qualify.
If you are reading it somewhere without the `callback_doctrine`
directory around it, you have the wrong checkout.

## Why this run matters

`probe.py`, beside this file, witnesses how Tk delivers callbacks —
which thread each route runs on, what a raise inside a callback does,
and what a callback may do to the thing that called it. The delivery
picture rests on those facts, and they are
per-platform: the expectations coded into the probe are the behavior
witnessed on Tk 8.6.14 with threaded Tcl under X11 on Linux, and the
project's other development platform is Windows. The picture is not
finalized until this run says whether Windows behaves the same way.

A **FAIL is a finding, not a fault.** A failing check means the Windows
Tk build does not behave the way the Linux one did — which is exactly
the information this run exists to collect. Nothing is broken and
nothing needs fixing; it needs *recording*.

## What to run

From the repository root:

```sh
uv run python -m experiments.callback_doctrine.probe
echo exit status: $LASTEXITCODE
```

(`$LASTEXITCODE` is PowerShell; use `%ERRORLEVEL%` under cmd.exe.)

- Use `uv run` so the probe runs on the project's own interpreter and
  the Tk build the library actually ships against; the first output
  line reports what actually ran.
- The probe is pure tkinter — it imports no tkfacade and needs no
  media libraries — and finishes in a few seconds. Each check carries
  its own timeout, so a hang, if one happens at all, resolves within a
  couple of seconds per check.
- A handful of small blank windows may flash up during the run; that
  is the probe mapping widgets so generated events deliver, and they
  close themselves.
- **If any line prints FAIL, run the probe a second time** and record
  both outputs, so a flaky failure is distinguishable from a stable
  fact.

## What to record

Fill in the *Findings* section below, in this file, with:

1. **The full output, verbatim**, in the fenced block provided — the
   platform header line included (it carries the Tk patchlevel and the
   threaded-Tcl flag), every verdict line, and the exit status. The
   detail text on each line embeds the witnessed values, so verbatim
   matters more than summary.
2. **The second run's output**, only if the first had any FAIL.
3. **The environment**: the Windows version and how the run was
   launched (PowerShell, cmd, terminal in an IDE), in the fields
   provided.
4. **Anomalies**, if any: a check that hung past its timeout (name the
   last verdict line printed before the hang), a Python traceback
   (verbatim), a window that needed closing by hand, or anything else
   the sections above have no slot for. Write "none" otherwise, so
   silence is distinguishable from an unfilled template.

## Rules for the agent running this

- **Do not modify `probe.py`**, its expectations, or anything else in
  the repository. A FAIL must reach the requesting session as a FAIL;
  editing a check until it passes destroys the finding this run exists
  to collect.
- **Do not file entries** in any to-do or known-issues list, or in
  `hazards/tkinter.md`, and do not update the README here — the requesting
  session folds findings into the project's records under their own
  conventions.
- Edit only this file, below this line; commit only this file for this
  task.

---

## Findings

- Date of run: 2026-08-19
- Windows version: Windows 11 Home, version 10.0.26200 (build 26200), 64-bit
- Shell / launcher: Windows PowerShell 5.1 (5.1.26100.8875), non-interactive,
  driven by an agent session on the machine's interactive desktop; working
  directory `Projects/tkfacade`
- Interpreter behind `uv run`: CPython 3.14.3, MSC v.1944, 64-bit (AMD64)
- Exit status: 0 — all fifteen checks `ok`, no FAIL

### Output, run 1

```
Tk 8.6.14, threaded Tcl 1, win32
generate on unmapped widget is dropped       ok    unmapped delivery dropped, mapped delivery ran ['unmapped'], no error
event handler on interpreter thread          ok    handler threads [21300] vs caller 21300: synchronous, same thread
trace on the setting thread                  ok    trace ran synchronously on the setting thread
worker set() delivers trace on mainloop      ok    worker's set() blocked while the trace ran on the mainloop thread
after-callback on mainloop thread            ok    after-job ran on the mainloop thread
handler raise reported, loop survives        ok    reports 1, later after fired True: loop survived
handler raise spares add='+' handlers        ok    ran ['first', 'second']; the second handler fired after the first raised
handler raise spares the bindtag chain       ok    ran ['widget', 'all']; the bindtag chain continued past the raise
command raise reported, invoke returns       ok    invoke() returned normally; the raise went to report_callback_exception
trace raise swallowed, write lands           ok    set() returned normally, the value changed, the raise was reported
trace raise spares other traces              ok    ran ['bad', 'second']; the raise was reported and the other trace fired
write inside a trace fires no traces         ok    firing order ['sibling', 'writer'], final value 'inner': the inner write triggered nothing
destroy mid-chain drops later handlers       ok    ran ['first', 'first-after-destroy'], reports 0; the add='+' handler after the destroy did not
second destroy is harmless                   ok    <Destroy> fired 1 time(s); the second destroy() was a no-op
update() nests dispatch in a callback        ok    order ['outer-start', 'inner', 'outer-end']; the inner callback ran inside the outer one's frame
exit status: 0
```

### Anomalies

None. No check hung, nothing raised a traceback, no window had to be closed
by hand, and no `python`, `tcl`, or `wish` process was left behind once the
probe returned.

Two things the sections above have no slot for. First, the probe was run a
second time even though run 1 had no FAIL, to tell a stable pass from a lucky
one; the two runs agreed line for line, differing only in the thread ids
quoted by `event handler on interpreter thread` (21300 in run 1, 15668 in
run 2 — a fresh process each time, and in both runs the handler's id matched
the caller's, which is what that check asserts). The run-2 section is deleted
rather than filled in, as this document instructs. Second, this run was driven
by an agent, which cannot see the screen: the brief window flashes described
above may well have happened, but that part is unwitnessed. Everything else
recorded here comes from the probe's own output and from the process table
after it exited.
