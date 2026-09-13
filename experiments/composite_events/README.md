# composite_events

The evidence probe for the composite-widget events repair: a wrapper whose
`_tk` is a frame holding the working widget
hears nothing a user does inside it. Several wrappers are that shape —
`TextBox`, `Tree`, `Listbox`, `TitleEntry`, the scales, and `Surface`
with every media display built on it.

The proposed repair routes each inner widget's bindtags through the
frame, so Tk delivers the events and the facade's `bind`, `unbind` and
dispatch need no change. Delivery that way was easy to witness before
this probe; three things were not, and they are what it was written
for.

## Running it

```sh
xvfb-run -a uv run python -m experiments.composite_events.probe
```

Every check prints its verdict; the exit status is the number that
failed. Expectations are the behavior witnessed on Tk 8.6.14 (threaded
Tcl, X11), CPython 3.14.

## Findings — 2026-08-22

All eleven checks pass, and the repair stands unchanged in substance.
One finding improved it.

The defect and the road out:

- **Unrouted, an inner event reaches nobody.** A click on the text
  widget ran none of the frame's bindings; a click on the frame ran
  them. The inner chain is `('.!frame.!text', 'Text', '.', 'all')` —
  the frame is absent, because Tk's bindtags are the widget, its
  class, the toplevel and `all`, never the parent.
- **A routed tag delivers.** With the frame's path in the chain, the
  same click arrives.
- **Delivery is exactly once** from either side, and a toplevel
  binding still fires once rather than twice — the toplevel is
  already in every chain, and routing to the frame does not put it
  there again.

The three that were open:

- **A consumer's `break` suppresses the inner widget's class binding
  through a routed tag.** The insert cursor stayed at `1.0` after a
  click that would otherwise have moved it. The consumer
  role therefore survives the repair, which was the one thing that
  could have sunk it.
- **Either tag position carries that verdict.** Head and second place
  both suppressed. **This decided the design against the original
  proposal:** the tag goes in *second*, after the inner widget's own
  tag, not first. Both deliver and both consume, and second place
  leaves any binding already on an inner widget running before ours —
  `VideoPlayer` has two, on its seek scale — so the repair changes no
  existing precedence.
- **An observer suppresses nothing.** It ran and the cursor still
  moved, which is what keeps the consumer's verdict meaningful.

What the repair depends on:

- **A raw binding on an inner widget survives routing**, running after
  a head-inserted tag and before a second-place one.
- **Unbinding the frame silences the routed road too**, so the
  subscription bookkeeping needs no change.
- **The delivered event names the inner widget**, which no wrapper
  answers for — `.!frame.!text`, not `.!frame`. So the dispatch must
  walk up rather than give up at the first miss, as it does today.
- **Walking the master chain finds the owning frame**, which is the
  resolution to put in its place.
