# menu_probe

Measures what `tk.Menu` and the `-menu` configuration option actually do,
so the menubar rebuild is
designed against witnessed behaviour rather than against the analogy that
produced the item. Pure `tkinter`; nothing here imports tkfacade.

The question the probe was run to answer: a menubar is *conceptually* a
composition of menubuttons, but Tk's menubar is `misc["menu"] = <a
tk.Menu>`, which is a different mechanism. What is that mechanism, what
will it accept, and where does it fail quietly?

## Running it

```sh
xvfb-run -a uv run python -m experiments.menu_probe.probe
```

Every check prints its verdict; the exit status is the number that
failed. The expectations coded in the checks are the behaviour witnessed
below, so a different Tk build or platform can be held against them — a
failure is a finding, not necessarily a fault.

## Where this was measured

Tcl/Tk **8.6.14**, `tk windowingsystem` = **x11**, CPython 3.14, under
Xvfb **with no window manager running** (proven: the toplevel's X window
is never reparented, and its grandparent is the X root).

Two consequences run through everything below. Menubars on macOS go to
the system menu bar and on Windows are native, so the clone mechanism,
the pixel geometry, the wrapping, and the rendering findings should be
assumed **not** to hold there until measured. And every geometry result
that involves negotiation with a window manager was measured against
nobody; where that matters it is marked.

## The central fact

**Assigning a menu to a toplevel's `-menu` does not put that menu on
screen. Tk builds a hidden clone and displays that.**

```
before:  ['.', '.thebar', '.thebar.filemenu']
after:   ['.', '.#thebar', '.#thebar.#thebar#filemenu', '.thebar', '.thebar.filemenu']

.#thebar   type='menubar'  manager='menubar'  mapped=1  geom='400x28+0+0'
.thebar    type='normal'   manager='wm'       mapped=0  geom='1x1+0+0'
```

The object you created stays unmapped at 1x1 with its entries laid out
*vertically*, forever. The clone is what renders, what opens, and what a
user clicks. Every submenu is cloned too, recursively.

The clone is invisible to tkinter — `nametowidget('.#thebar')` raises
`KeyError` and `winfo_children()` drops it — but visible to Tcl's `winfo
children`. Configure propagates **both ways** across the boundary, so
reaching for the `#`-named path mutates the caller's object.

No clone is made in the menubutton (popup) role: there the menu itself is
posted.

## Attachment

- `-menu` exists on **toplevels and menubuttons only**. `Frame`, `Label`,
  `Canvas`, `PanedWindow`, `Notebook` and `Menu` all raise
  `TclError: unknown option "-menu"`.
- The option holds a **string path** and its value is **never validated**.
  A `Frame`'s path, a `Label`'s path, a path that names nothing, and a
  bare `nosuchwidget` are all accepted with no exception, no background
  error, and no menubar.
- Parentage is not enforced: a menu mastered on a `Frame`, or on an
  unrelated toplevel, is accepted as a bar and cloned in.
- One menu can be the bar of two toplevels **and** a menubutton's popup
  simultaneously. Each toplevel gets its own clone tree; all of them
  track later edits.
- The popup role is the one that enforces parentage, and it enforces it
  **at click time, not at configure time** — see `hazards/tkinter.md`, *Menus*.
- `config(menu="")` clears the bar and destroys the clone, leaving the
  master alive. `config(menu=None)` is a silent no-op: tkinter drops
  `None`-valued options before they reach Tcl.

## The top row

- All five entry kinds are accepted: cascade, command, checkbutton,
  radiobutton, separator. `type(i)` reports each faithfully.
- Checkbuttons and radiobuttons **draw their indicators** in the bar and
  track their variables.
- **Separators put zero ink in the bar.** A pixel diff of an identical
  bar with and without three interleaved separators: `0 differing
  pixels`. They still consume index positions.
- **A top-row cascade gets no visual affordance** — same pixel width and
  appearance as a plain command for the same label. A *nested* cascade
  one level down draws `▸`.
- **`-accelerator` on a top-row entry is silently discarded** — no text
  drawn, no width added. `hazards/tkinter.md` already records that accelerators
  are cosmetic everywhere; in the bar they are not even that.
- **The top row wraps.** It is not one strip. Six commands, varying the
  toplevel's width:

  ```
  width 600: geometry=600x28   ypositions=[1, 1, 1, 1, 1, 1]
  width 120: geometry=120x80   ypositions=[1, 1, 27, 27, 27, 53]
  width  60: geometry=60x106   ypositions=[1, 27, 27, 53, 53, 79]
  ```

- Nesting was measured to depth 12 with no degradation; the clone mirrors
  the whole chain.
- `invoke()` and a real click **disagree on cascades in both
  directions**: `invoke()` fires the cascade's `-command` and does not
  post; a click posts and does not fire the `-command`.
- A menubar's own `postcommand` **never fires** in the bar role — not on
  assign, map, click, or F10. A top-level cascade's own `postcommand`
  does fire when that cascade opens. In the popup role the menu's
  `postcommand` fires on every post.

## Addressing an entry

Tk addresses entries by index, and every route to a stable address is
compromised.

- **`index(label)` is Tcl glob matching, not string equality.**
  `index("*e*")` returns `0` in a `File/Edit/View/Help` row.
- **Integer parsing and reserved words beat label matching.** An entry
  labelled `end`, `last`, `active`, `none`, `@5`, or any decimal string
  is unreachable by its own label.
- A literal label containing glob metacharacters — `Wei[rd]*` — cannot be
  addressed by its own label at all.
- Duplicate labels: `index` answers the first match only. The second
  becomes reachable only once the first is deleted.
- `delete(i)` shifts every later entry down one; `insert_*(i, …)` shifts
  every entry at or after `i` up one. The index is a position, not a
  handle.
- `index("end")` is `None` on an empty non-tearoff menu and `0` on an
  empty tearoff menu — the two differ in the *type* of the answer, so
  `range(m.index("end") + 1)` raises `TypeError` on one and not the
  other.
- `@n` hit-tests the **x** axis on the horizontal row, and `"active"`
  resolves only while something is activated.

## Geometry

Measured with no window manager; treat absolute positions as artefacts
and the deltas as the finding.

- **The bar does not come out of the interior when the program sets the
  geometry.** `geometry("400x300")` leaves the interior 400x300 and grows
  the outer window to 400x328. Neither the toplevel's nor a fill-child's
  width, height or `reqheight` changes; only `rooty` moves.
- **When the frame is resized instead — what a real WM does — the bar
  comes out of the interior.** The same numbers give opposite results:

  ```
  program: geometry('500x400') -> interior=500x400  wrapper=500x428
  WM-like: wrapper forced to 500x400 -> interior=500x372
  ```

- **Bar height is a function of window *width*,** because the row wraps.
  Narrowing a window silently makes the whole window taller: 10 cascades
  at width 600 give a 228px-tall window, at width 100 a 306px one, with
  the interior pinned at 200 throughout.
- An entry-less menu still reserves 2px. Height tracks `-borderwidth` and
  the entry font.
- `wm minsize`/`maxsize`/`wm grid` publish hints that **omit** the bar;
  `wm resizable(0, 0)` publishes hints that **include** it. Two adjacent
  APIs, two conventions. *(Values measured; enforcement not — no WM.)*
- Assign and unassign after mapping is fully reversible and leaks
  nothing across repeated cycles.

## Lifecycle

- A menu mastered on the toplevel that holds it as a bar is destroyed
  with it, submenus and clones included.
- A menu mastered elsewhere **survives** that toplevel's destruction —
  only the clones die — and can be reassigned to a new toplevel.
- Destroying the assigned menu returns the geometry immediately, but
  `cget("menu")` keeps naming the dead path. The two disagree.
- Deleting a cascade entry does **not** destroy its submenu widget: it
  leaks, alive and unreachable.
- Destroying a submenu leaves its cascade entry fully live and
  configurable, doing nothing when invoked. It can be repaired by
  pointing `-menu` at a fresh menu.

## What a facade can be built on

`facade.py` beside `probe.py` measures tkfacade against Tk rather than Tk
alone. Thirteen checks; run it the same way.

**The menu facade survives the bar unchanged.** All five `add_*` kinds
seat in the top row and hand back the right handles — the probe's bar
wears `RuledMenu`, so the rule call `Menubar` refuses by absence is
witnessed seating there too; a top-row `Submenu`
is a row and a menu at once and nests as deep as anywhere; a row's own
command fires. Crucially, two top-row rows carrying one label stay
distinct — delete the first and the second's `index` moves from 1 to 0 —
because `MenuPart.index` scans `_owner._parts` by identity and never
consults Tk's index space. Every addressing hazard above is unreachable
through this design rather than defended against.

**Where the menu is mastered decides whether the window grows an unowned
child.** Mastered on the window it is a window child that
`nametowrapper` raises on; mastered on a `Frame` inside the window it is
not a window child *and* still dies with the window.

**A `BaseWidget` can own a `tk.Menu`.** It constructs, registers,
resolves through `nametowrapper`, and evicts itself when the menu is
destroyed. It offers no `grid`, `pack` or `place` — those live on
`Widget`, not `BaseWidget` — so containment does not arise for it any
more than it does for a `Window`.

**The bar's state is readable from Tk, just not by the obvious query.**
`winfo_ismapped()` answers 0 on a plainly visible bar. Four checks
together answer honestly: the option names our menu, the path exists, it
is a `Menu`, and a `-type menubar` clone exists under the window. Those
distinguish *installed and rendering*, *not ours*, and *dead*.

**A binding on the bar cannot say what it heard.** Generating on the
clone does reach a binding placed on the master, because the clone's
bindtags splice the master's path in — but the delivered `event.widget`
is the clone's path, arrives as a bare `str`, and `nametowidget` raises
on it. So a real interaction with the bar cannot be resolved back to a
wrapper. What a user chooses arrives as the row's command instead, which
is the position `Menubutton` already takes for its own popup.

**One destroy is heard twice**, the submenu's included — the binding
hazard already recorded under *Bindings*.

## What went to `hazards/tkinter.md`

The findings that meet that file's bar — Tk accepting something and then
doing nothing, or doing something other than what was asked, with no
error — are filed there under *Menus*. This README keeps the whole
record, the unsurprising rows included.

## Unmeasured

- **macOS and Windows, entirely.** The clone mechanism is the X11 code
  path. Nothing above should be assumed to hold on `aqua` or `win32`,
  including the special `.apple`/`Help`/`Window` menu names on macOS.
- **Behaviour under a real window manager.** The published-vs-enforced
  gap in the size hints, the interactive-resize asymmetry, and every
  absolute coordinate are unsettled without one.
- **Keyboard traversal** — F10, `-underline` mnemonics, arrow movement
  along the bar. Requires focus and grab behaviour a WM-less Xvfb does
  not reliably provide, so a negative result would not be trustworthy.
- **Whether a real click on a top-row cascade posts the submenu.** The
  `-command` result is established; the posting was confirmed only
  through `postcascade`, which is not the click code path.
- **Tk 8.7 and 9.0.** Only 8.6.14 was present.
