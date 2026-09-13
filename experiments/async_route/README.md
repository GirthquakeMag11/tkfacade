# async_route

The evidence probe under the async callback route's design gate. The
gate must decide where the
asyncio loop lives, what an off-loop coroutine may touch, how
completion and exceptions route, and what widget death does to an
in-flight coroutine; this probe pins the loop-beside-Tk facts those
decisions rest on. The delivery-side facts for synchronous callbacks
are `../callback_doctrine/`'s; the last two checks here import the
library, because the facts they pin are about tkfacade's own
observable rather than about Python.

## Running it

```sh
xvfb-run -a uv run python -m experiments.async_route.probe
```

Every check prints its verdict; the exit status is the number that
failed. Expectations are the behavior witnessed on Tk 8.6.14 (threaded
Tcl, X11), CPython 3.14; a FAIL on another build is a finding needing a
re-run on that platform.

## Findings — 2026-08-21

The loop beside Tk:

- An asyncio loop on its own thread serves coroutines scheduled from
  Tk's thread with `run_coroutine_threadsafe`, with no pumping anywhere:
  scheduling returns before the coroutine completes, the coroutine runs
  off the Tk thread, and its result crosses back on the scheduling
  future.

The thread wall, two-moded:

- A Tk call from any other thread is **refused outright** —
  `RuntimeError: main thread is not in main loop` — while the main
  thread is out of Tk's event loop (sleeping, joining, waiting on a
  future). The marshalling `../callback_doctrine/` witnessed (the
  worker blocking while its work runs on the mainloop) happens only
  while the main thread is *in* the loop. One API, two modes, selected
  by what the main thread happens to be doing (`hazards/tkinter.md`,
  *Threads*).
- `after()` called from the loop thread is a working road back onto the
  mainloop — the callback runs on Tk's thread — but only under a
  genuinely running mainloop, per the same wall.

Cancellation and teardown:

- Cancelling the scheduling future is **fire-and-forget toward the
  coroutine**: the future reports cancelled immediately, and the
  `CancelledError` arrives at the coroutine's await point later, on the
  loop, running its `except` and `finally` there. Nothing about the
  future's state says the unwinding has happened.
- Stopping the loop without cancelling freezes pending tasks
  mid-await, `finally` blocks unrun — and the task is frozen, not
  gone: the same loop revived delivers a later cancel and the
  `finally` runs.
- The orderly teardown is therefore *cancel, wait for the unwind,
  stop, join* — witnessed completing in milliseconds. The wait is the
  step the fire-and-forget cancel makes mandatory; skipping it is how
  a `finally` dies unrun.
- One spelling detail: the scheduling future raises
  `concurrent.futures.CancelledError`, distinct from
  `asyncio.CancelledError` on this floor — a caller catching
  cancellation on the Tk side must catch that flavor.

Exceptions:

- A coroutine's raise parks on its scheduling future and surfaces to
  whoever retrieves it; the loop's exception handler is never invoked
  for it. Routing is therefore wholly the retriever's problem — which
  is the design's opening, since the facade will be the retriever.

Today's observable, written from the loop:

- With no transport attached, the write goes through and **the watcher
  runs on the writing thread** — the mainloop-affinity posture is the
  caller's to honor and nothing guards it.
- With a transport attached, the write **half-lands**: tkinter's
  thread wall refuses the transport push, `_push`'s dead-transport
  suppress swallows the refusal, and the result is the value and its
  watchers moved (off-thread) while the widget silently keeps the old
  text — split state with no report anywhere, an observability gap.

## The design — settled 2026-08-21

Four rulings, taken in order on the evidence above.

**Where the loop lives.** `Root` lazily owns one *core* — an asyncio
loop on its own thread with a paired thread pool as its default
executor — started on first async need, reachable through the widget
relations back to the root, and torn down inside `Root.destroy()`. The
shape is adapted from an asyncio-loop-per-thread `AsyncCore` draft;
the adaptation is vendored here, no external dependency. There is no
per-handler loop routing: the core coexists with any other loops an
application runs,
blocking sync work inside a coroutine belongs on the paired pool
(`asyncio.to_thread`), and users with real concurrency architecture
bring their own — this is a GUI library, not a concurrency one.

**What a coroutine may touch.** One set of touch rules for any
coroutine on the core, however admitted: it never touches Tk or a
widget directly — the thread wall's two modes and the teardown
deadlock window (`hazards/tkinter.md`, *Threads*) are the whole reason — and
it works on values. In: the immutable `Event`, observable reads. Out,
two doors. **Observable writes** are the implicit door: the library
detects an off-thread write and marshals the whole settle — transport
push and watcher dispatch — onto the mainloop, sanctioned because a
write is a complete instruction with no answer flowing back and the
settle semantics already mean "effects follow." **One awaitable
crossing** — await a sync function run on the mainloop, its result
delivered back — is the explicit door for every crossing an answer or
a completion promise flows back from: widget reads, method calls,
`emit`. The asymmetry is physics, not style: suspension is syntactic
in Python, so a result-bearing crossing must be spelled ``await``,
where an implicit one could only block the whole core behind a hidden
hop. The ban is documented rather than enforced in v1. Admission
routes are their own enumerated list, grown by amendment — the
observer role of `bind` and coroutine watchers first, later routes (a
Button command) as they arrive — and consumers stay structurally
refused, unchanged.

**How completion and exceptions route.** Async adds no third delivery
category. Notification routes stay fire-and-forget: the dispatch
schedules the coroutine and does not wait, returns are ignored, and a
raise is retrieved by the facade and routed to the `Root` callback
error hook, delivered on the mainloop by a wall-safe route. Explicit
channels report through themselves: the awaitable crossing re-raises
its function's exception into the awaiting coroutine, and any
future-returning surface owns its own retrieval. Cancellation is
lifecycle, never error — in both witnessed spellings of
`CancelledError` — silent everywhere, always unwinding `finally`.

**What death does.** Death narrows the future, never the present,
mirroring the witnessed sync rule that a running handler finishes its
own body. Widget death ends future deliveries and cancels nothing in
flight: a running coroutine keeps its values, its observable writes
stay valid, and a crossing to the dead widget raises into it through
the channel. `Subscription.cancel()` is the explicit stop and
does reach in flight — no further deliveries, and that subscription's
live tasks are cancelled, the events design's door-keeping constraint
fulfilled. Only `Root.destroy()` ends everything: a short grace for
the briefly busy, cancellation for the stragglers, the mandatory wait
for their unwinds, then stop and join.

**Paper-fit.** The dispatch's coroutine leg is a scheduling call plus
a done-callback that reports or prunes; the observer and watcher
refusal messages retire when the route lands; the off-thread
observable write's marshal closes the half-landing entry by
making the broken act's sanctioned form; and the declarative bridge
stays six lines —
`@on(spec)` storing a spec works unchanged whether the decorated
method is a function or a coroutine, which is the requirement this
gate exists to keep. The crossing's spelling settled at the build's
checkpoint, by ruling: `async_submit`, `submit`'s async twin — twins
carry one surname with the mark naming what varies, so "which one
here?" is answered by the keyword the caller is standing inside.
