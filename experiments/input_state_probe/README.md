# input_state_probe

Witnesses, by real device injection, the Tk facts the keyboard and
mouse observer stands on: what a root-level ``bind_all`` sees, what
X11 autorepeat delivers while a key is held, what is lost when focus
leaves the application mid-press, what a menu grab starves (nothing,
it turns out), and that generated events register identically — the
route the suite drives the observer by.

Injection is `xdotool` (XTEST), so a held key meets the X server's own
autorepeat rather than a synthesized imitation. Nothing here imports
tkfacade.

## Running it

```sh
xvfb-run -a uv run python -m experiments.input_state_probe.probe
```

Requires `xdotool` on the PATH. Exit status is the number of failed
checks.

## Where measured

Tk 8.6.14, Tcl threaded, x11 under Xvfb (no window manager), xdotool
3.20160805.1. Six checks, all passing, 2026-08-27.

## What was witnessed

- **One root binding sees everything.** ``bind_all`` on the four kinds
  (KeyPress/KeyRelease/ButtonPress/ButtonRelease) receives every real
  press and release wherever focus sits, and the focused widget's own
  binding still fires — the ``all`` tag runs after the widget's, so
  observation steals nothing.
- **Autorepeat is phantom release/press pairs.** A key held past the
  repeat delay delivered 21 presses and 21 releases; every repeat
  arrived as a KeyRelease immediately followed by a KeyPress **with
  the identical X timestamp** (20 of 20 pairs). The state filter this
  dictates: defer acting on a KeyRelease until the next event is
  known, and drop the pair when a same-key KeyPress shares its
  timestamp — held state then never flickers.
- **The stuck-key trap is real.** Press inside, move the input focus
  to another client, release: the release never arrives — no event
  will ever say the key came up — while ``FocusOut`` is delivered
  reliably. The clearing policy follows: all held state drops when
  the application loses focus.
- **A posted menu's grab starves nothing here.** Key press and
  release both reached the root binding while a ``tk.Menu`` was
  posted — a popped menu's bindtags keep ``all`` (the composite-events
  record), so global observation keeps working where per-widget
  routing cannot.
- **Left and right modifiers are distinct keys.** ``Shift_L`` and
  ``Shift_R`` arrive under their own keysyms and track separately.
- **Generated events register identically**, keysym and button intact,
  so the suite can drive the observer without a device.

## Traps

- **xdotool resolves keysyms through the keymap.** Asked for the
  *keysym* ``Shift_R``, it presses a helper ``Shift_L`` alongside —
  two shifts down at one timestamp. Inject modifiers by raw keycode
  (50/62 under the Xvfb keymap) as the probe does, or the variant
  check reads double.
- **No focused widget, no key events.** ``windowfocus`` alone puts X
  focus on the toplevel; a widget must hold Tk's focus
  (``focus_force``) before key events are delivered at all.

## Unmeasured

Windows and macOS deliver autorepeat differently (typically repeated
KeyPress without the release), and the grab and focus stories are the
platform's own; the checks are the instrument to re-run there. Wheel
events carry no press state and are outside the observer's tracking
by design (`hazards/tkinter.md`, *Scrolling*, wheel delivery).
