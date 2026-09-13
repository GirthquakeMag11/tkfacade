# experiments

Exploratory development. Things live here to see whether they work, because
they may be worth including but aren't settled, or because deciding takes
time. Nothing in this directory is part of the library's public surface, and
nothing here gates the build: mypy excludes it, and scratch files carry their
own lint pragmas.

Current contents:

- `callback_doctrine/` — witnesses how Tk delivers callbacks, per route:
  the thread, the fate of a raise, and the reentry cases. The evidence
  is a callback-delivery reference; its README holds
  the findings table, and the surprises are filed in `hazards/tkinter.md`.
- `menu_probe/` — measures what `tk.Menu` and the `-menu` option actually do,
  for the menubar rebuild. The
  central finding is that a toplevel's menubar is served by a hidden clone
  rather than by the menu handed to it, which is why every geometry and
  identity question asked of that menu answers about something else. Its
  README holds the whole record; the surprises are filed in `hazards/tkinter.md`
  under *Menus*. Pure `tkinter`, no tkfacade import.
- `scroll_probe/` — measures what Tk's scroll machinery actually couples,
  for the scrollbar-placement item and the home
  question behind it. The central finding is that the protocol couples
  callables, not widgets — placement and ownership are entirely the
  facade's choices — with the viewport mechanism's demands and the
  wheel's delivery mapped beside it. `probe.py` is pure `tkinter`;
  `facade.py` measures the library against the same facts. Its README
  holds the whole record; the surprises are filed in `hazards/tkinter.md`
  under *Scrolling*. The 2026-08-21 protocol facts live in
  `scroll_view/` beside it and are cited, not re-measured.
- `hazards_probe/` — re-creates the tkinter hazards that carried no other
  witness, one check per claim, so `hazards/tkinter.md` can point at a
  re-runnable record. Its checks are the witness for three entries that
  previously had none; a fourth (that `ttk.PanedWindow.insert` refuses the
  position one past the last pane) did not hold on Tk 9 and was removed.
- `fast_testing.py` — the scratch-pad harness: hang a widget on a window and
  look at it. Decorate a builder with `@demo` and run the file; see its
  module docstring for the rules.
- `print_stack.py` — pure-tkinter debugging tool: prints a widget tree's
  stacking order, geometry manager, mapped state, and grid cell per widget.
  Useful when diagnosing occlusion and `grid(in_=...)` mismatches.
- `interception_setup/` — dormant, Windows-only spike: a CLI that installs
  and verifies the Interception kernel input driver. Untouched since it was
  moved out of the package; its test file still targets the old in-package
  import path.
- `ttk_style_probe/` — works out which `ttk.Style` options each ttk widget
  actually honours, by setting each one and comparing what the widget draws
  on a virtual display. Wrote the note `ttk Style Options`; kept so that note
  can be checked again on another Tk build. `rules.py` re-tests every claim
  the note makes in about a minute and is the thing to run first. Pure
  `tkinter`, no `tkfacade` import, and it keeps to Python 3.11 syntax
  because it runs against whichever interpreter has `tkinter` built in.
