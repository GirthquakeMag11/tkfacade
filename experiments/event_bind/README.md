# event_bind

The binding-mechanics probe under the events design. The delivery-side
facts — thread, exceptions, destroy behavior, the unmapped-generate
drop — are `../callback_doctrine/`'s; this probe pins the registration
side: how
a binding is revoked, what `"break"` stops, what a user-defined event
can carry, and how generated events interact with modifier-qualified
and multi-click bindings. Three of the findings met the bar for
`hazards/tkinter.md` and are filed under *Bindings*.

## Running it

```sh
xvfb-run -a uv run python -m experiments.event_bind.probe
```

Every check prints its verdict; the exit status is the number that
failed. Expectations are the behavior witnessed on Tk 8.6.14 (threaded
Tcl, X11), CPython 3.14; like the sibling probes, a FAIL on another
build is a finding. A later Windows re-run of all seven on win32
agreed, the click counting included, so everything below stands
witnessed on both development platforms.

## Findings — 2026-08-20

Revocation (good news, both halves):

- `unbind(sequence, funcid)` is surgical on this floor: the sequence's
  other handlers stay bound and firing. The historical CPython behavior
  of clearing the whole sequence is fixed; the project's 3.14 floor
  means the design may rely on surgical revocation.
- The unbound funcid's Tcl command is deleted, so revocation does not
  leak the handler (and everything it closes over) into the
  interpreter's command table.

Chain control:

- A handler returning `"break"` stops the `add="+"` handlers bound
  after it on the same widget.
- It also stops the rest of the bindtag chain, class bindings included:
  a `<KeyPress-a>` handler returning `"break"` on an entry keeps the
  keystroke out of the widget — consuming input is real and reaches Tk's
  own default behavior.

Dispatch selection:

- When more than one binding on the same tag matches an event, the most
  specific fires **alone**: with `<Button-1>` and `<Control-Button-1>`
  both bound, a control-click reaches only the control binding
  (`hazards/tkinter.md`, *Bindings*). Generated state bits satisfy
  modifier-qualified bindings, so modifier specs round-trip through
  `event_generate`.
- Tk's click counter runs on event time and counts synthetic events:
  two back-to-back generated singles deliver a `<Double-Button-1>` for
  the second, exclusively — while generating a double *directly* is
  refused outright (`hazards/tkinter.md`, *Bindings*).

Payloads:

- The delivery boundary for generated events is X-window *creation*,
  not mapping: a fresh classic widget under an unrealized chain drops
  the event, `winfo_id()` alone forces creation and the same generate
  then delivers, and ttk widgets create eagerly at construction under a
  realized parent — which is why facade wrappers deliver where a bare
  `tk.Frame` drops (`hazards/tkinter.md`, *Bindings*, corrected from the
  earlier mapping-based reading after the facade's own tests refuted
  it).
- `event_generate(..., data=...)` is invisible through tkinter's own
  binding route — tkinter's substitution list has no `%d`, so the
  handler's event object simply lacks the field. The payload is
  reachable only via a raw Tcl binding with `%d`, and as a string
  (`hazards/tkinter.md`, *Bindings*). A library that controls both ends
  of a custom event can therefore carry object payloads itself and use
  `%d` only for correlation.

## The design — settled 2026-08-20

The rulings, in the order they were made: v1 specifications cover the
**common vocabulary plus user-defined custom events**, Tk's exotica
excluded and the spec type left extensible; **widgets and windows** are
bindable, application-global binding deferred to the keyboard-observer
item that is its real consumer; dispatch is **library fanout** — one Tk
binding per (widget, spec), the facade calling every registered
subscriber unconditionally, in registration order, so no subscriber can
silence a sibling; custom events carry **kwargs frozen into the
library's one payload container**; bind and watch return **one shared
subscription handle**; subscribers register in one of **two declared
roles**; and a consumer's verdict is **implicit in its successful
completion** — the pair of rulings that resolved consumption by moving
first the capability and then the verdict itself out of handler
behavior and into registration. Verbs and names below are working
names; contact with the road decides the final spelling.

**The two roles.** An *observer* witnesses the event: it is called with
the immutable event value, its return is ignored entirely, and it has
authority over nothing — this is the role coroutine handlers will
occupy when the async route lands, because witnessing needs no
synchronous voice. A *consumer* is registered as one — the role is a
registration parameter, not a behavior — and its verdict is implicit:
running to completion *is* the consumption signal, so a consumer's body
carries no protocol at all, and returns are ignored in both roles
alike. A raising consumer is reported per the callback rules and has
not completed, so it consumed nothing and the default proceeds — a
buggy consumer degrades to Tk's own behavior rather than eating input.
Consumers run before observers, each group in registration order, and
any consumer's completion suppresses the default: the witnessed
`"break"` mechanics carry that verdict downward to Tk's class default
(the probe's eaten keystroke) and only downward — siblings, observers,
and the rest of the facade's dispatch are untouchable by design. What
this shape gives up is per-event judgment: a consumer consumes every
event it survives, so the spec is the predicate — which fits the real
cases, where what to consume *is* a spec (a chord, a key, a click) —
and a *conditionally-consuming* flavor, declared at registration like
everything else here, is the named seam if a consumer ever arrives
needing one.

**Specs are values.** Immutable, hashable, composable from the `events`
package's vocabulary — the enums for keys, buttons, click counts,
modifiers, crossing, focus, and virtual events, plus named custom
events — storable by a decorator before any widget exists and usable as
registry keys. One spec maps to one Tk sequence; across *different*
specs on one widget Tk's most-specific-wins selection still applies and
is documented as competition, not fought (`hazards/tkinter.md`,
*Bindings*): fanout guarantees every subscriber *of the spec that
fired*, never that a broad spec hears a specific spec's events.

**The event value.** One immutable object per delivery: the typed
fields of the raw event (through the `events` enums), the spec that
fired, the wrapper the event landed on (resolved through the registry;
None for a widget no wrapper built), and — for custom events — the
frozen payload. Immutable because one event is delivered to many
subscribers and later to other threads: a fact, not a handle.

**Emit and payloads.** `emit(spec, key=value, ...)` freezes the kwargs
into the library's one container type and delivers it on the event —
arbitrary data without arbitrary types, immutability enforced at the
container (shallowly, stated honestly: a mutable object passed as a
value stays mutable). The transport is the probe's proven route: the
object is stashed library-side and `%d` carries only a correlation
token; events arriving from raw Tcl carry an empty payload. One
spelling wrinkle recorded: bare-kwargs payloads mean
`emit` can never grow keyword options of its own, so either it stays
option-free forever or the payload moves into one parameter.

**Handles and lifecycle.** Both roles return the shared subscription
handle (one type with the observable's watch), carrying `cancel()` —
honest and thin, since the probe witnessed surgical, leak-free
revocation on the 3.14 floor — and the future async route maps task
cancellation onto the same object. Wrapper-internal bookkeeping
registers through the same machinery it hands callers: the card
stacks' IOU sites are the first customers.

**The doors, kept open.** A coroutine offered to the observer role is
refused with a raise naming the pending async design; offered to the
consumer role it is refused
*permanently and structurally*, with the reason in the message —
consumption is completion, and a coroutine has not completed when the
verdict is due. The dichotomy the consumption rulings surfaced is
thereby architecture: async arrives later as a new kind of observer,
and consumption never needed the door at all.

**Paper-fit.** The IOU sites become destroy-observers through the
public route; the probe's eaten keystroke is the consumer's worked
example — an unconditional consumer on `<KeyPress-a>`, exactly as
witnessed; the declarative bridge stays six lines, the consumer flag
riding the same decorator (`@on(spec)` for observers,
`@on(spec, consume=True)` or its own `@consume(spec)` — the
registration-parameter spelling is the ruled lean) plus the same
walk-and-register loop, still costing the declarative layer nothing
but the walk. What the implementation iterates on contact: the verbs, the
consumer flag's spelling, the event value's exact field set, and the
emit spelling above.

### Amended at the milestone-3 checkpoint — 2026-08-20

Contact with the road produced rulings that supersede spellings above.
`emit` takes its payload as one mapping parameter rather than bare
kwargs (the earlier amendment log carried the entry). The key and
button specifications are unified and stripped to the memoryless
hardware occurrence: `Press(input)` and `Release(input)` over one
input vocabulary — `Key` (renamed from `KeyPress`) and `MouseButton` —
replace `KeyChord` and `Click`, and `ClickCount` is deleted. Modifier
filters and repeat counts left the specification vocabulary entirely:
what else is held and what happened just before are judgments about
input-device *state*, owed to the keyboard-and-mouse observer
that will make them uniformly for every input — Tk's
modifier prefixes and click counting are that system's work half-done
for a privileged few inputs, and building the vocabulary on those
fragments would have baked the privilege in. The witnessed facts about
those mechanics stay filed (`hazards/tkinter.md`, *Bindings*, and the findings
above): they describe Tk, and raw bindings beside the facade still
meet them.

A further ruling collapsed `Custom` into `Virtual`: the only
user-defined event Tk offers *is* a virtual event, so the class split
was a nominal distinction the mechanism does not have. One `Virtual`
kind takes a name — a `VirtualEvent` member for Tk's shipped events,
any bracketless string for a user's own — its `type` attribute
answers with the member where the name is Tk-shipped and None
otherwise, and the enum's values dropped their `<<>>` brackets so
member-built and name-built specs compare as the one specification
they are. The payload right rides `Virtual` now, wherever this
document says custom events.

The event value slimmed to the occurrence's own facts under the same
lens: `state`, `keysym`, and `char` left it — the first is a sample of
device state riding the packet (the input-state layer's answer to
give), the second repeats what the specification already names, and
the third is a state-derived translation belonging to text input, not
to the occurrence. What remains is spec, widget, position, time, and
payload, with the coordinates renamed to say what they are:
`widget_x`/`widget_y` within the wrapper the event landed on,
`screen_x`/`screen_y` on the screen. Position itself was then ruled a
pointer fact: each specification answers `at_pointer`, and the
dispatch takes coordinates from the packet only where that answer is
True — Tk stuffs the pointer's idle position into keyboard packets
too, and the facade drops it there as the state sample it is.
