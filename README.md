# tkfacade

[![CI](https://github.com/GirthquakeMag11/tkfacade/actions/workflows/ci.yml/badge.svg)](https://github.com/GirthquakeMag11/tkfacade/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/tkfacade)](https://pypi.org/project/tkfacade/)

Typed, imperative wrappers over tkinter's widgets, and the vocabulary their
signatures speak. The library names every option a widget takes, gives each a
typed property instead of a bag of keyword strings, and ships one consistent
surface over the whole toolkit.

## Installation

```sh
uv add tkfacade==0.1.0
# video playback also needs the media extra and libmpv on the system path
uv add "tkfacade[media]==0.1.0"
```

Downstream projects pin exactly and bump deliberately after reading
`CHANGELOG.md` and the release notes — during `0.x`, minor versions may
break the API.

Requires Python 3.14 or later. Tk must be available on the interpreter
(tkinter ships with CPython on the common platforms).

## The idea

tkinter is capable but kind-unfriendly: options are passed as keyword
strings, everything reads back as `Any`, booleans sometimes answer `int`,
and a widget's real behavior is a theme-dependent fact rather than a class
contract. tkfacade wraps each widget so its options are named and typed at
construction and mutable through typed properties afterwards, and so what a
wrapper promises is what it does.

A command can be a plain callable — run inline on the mainloop when Tk
invokes it — or a coroutine function — scheduled fire-and-forget on a
per-root asyncio core beside the mainloop. Both raise into the same error
hook, so an application sets error routing once and every callback failure
arrives there.

## Quick start

```python
import tkfacade

win = tkfacade.Window(title="Example")
label = tkfacade.TextLabel(win, "Ready").grid()
button = tkfacade.Button(win, "Start", command=do_work).grid(row=1)
win.run_mainloop()
```

Every wrapper takes its master first, then its options, and answers with
`grid()`, `pack()`, or `place()` for layout.

## What's here

- **Widgets** — `Button`, `Checkbutton`, `TextLabel`, `ImageLabel`, `Entry`,
  `TitleEntry`, `Text`, `TextBox`, `Listbox`, `Combobox`, `IntScale` /
  `FloatScale`, `IntSpinbox` / `FloatSpinbox`, `Separator`, `Scrollbar`, the
  progressbars, the choice family (`ChoiceBox`, `ChoiceButton`,
  `ChoiceButtons`, `ChoiceSet`, `ChoiceSpinner`), `Tree`, `Table`, and the
  frame family (`Frame`, `LabelFrame`, `PanedFrame`, `StackFrame`,
  `TabFrame`).
- **Windows** — `Window` and `Root`, owning the interpreter and the event
  loop.
- **Dialogs** — message, confirm, textbox, field, and file dialogs.
- **Menus** — `Menubar`, `Menu`, `Menubutton`, `OptionMenu`, and row kinds.
- **Media** — `ImageDisplay`, `VideoDisplay`, and `MediaPlayer`, with the
  image half powered by Pillow and the video half by libmpv, loaded lazily so
  importing tkfacade never loads libmpv.
- **Observables** — `ObservableStr`, `ObservableBool`, `ObservableInt`,
  `ObservableFloat`, and the `Subscription` their watchers hold.
- **Events and input** — the event vocabulary behind every binding, and the
  keyboard-and-mouse observer.

## More

- `examples/` — runnable demonstrations, a one-window tour of the suite in
  `showcase.py`.
- `experiments/` — exploratory probes written while each area was designed;
  nothing there is part of the public surface.
- `CONTRIBUTING.md` — the two project principles, the verify gate, the PR
  flow, and the automation lifecycle.
- `docs/tracking/` — the operations spec, the roadmap, and the downstream
  reporting kit (`/tkf-report-bug`, `/tkf-request-feature`) for projects
  consuming tkfacade.
- `CHANGELOG.md` — per-release notes.
