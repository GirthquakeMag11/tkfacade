# Changelog

All notable changes to tkfacade are documented in this file. Sections are
compiled from the release milestone's closed issues before the tag is pushed
(see the `/release` flow in CONTRIBUTING.md). The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
the policy in CONTRIBUTING.md.

## [Unreleased]

## [0.1.0] - 2026-09-13

First public release.

### Added

- Typed, imperative wrappers over the tkinter widget suite: `Button`,
  `Checkbutton`, `TextLabel`, `ImageLabel`, `Entry`, `TitleEntry`, `Text`,
  `TextBox`, `Listbox`, `Combobox`, `Scale` (int/float), `Spinbox`
  (int/float), `Separator`, `Scrollbar`, `Tree`, `Table`, progressbars, the
  choice family, and the frame family (`Frame`, `LabelFrame`, `PanedFrame`,
  `StackFrame`, `TabFrame`).
- `Window` and `Root` owning the interpreter, the asyncio core beside the
  mainloop, and error routing for plain-callable and coroutine commands.
- Message, confirm, textbox, field, and file dialogs.
- `Menubar`, `Menu`, `Menubutton`, `OptionMenu`, and menu row kinds.
- Media: `ImageDisplay`, `VideoDisplay`, `MediaPlayer`, and the Pillow-backed
  image helpers, with libmpv loaded lazily behind the `media` extra.
- Observables (`ObservableStr`, `ObservableBool`, `ObservableInt`,
  `ObservableFloat`) and their `Subscription` handle.
- The event vocabulary (`Event`, `Key`, `Press`, `Motion`, ...) and the
  keyboard-and-mouse `InputObserver`.
- `grid()` / `pack()` / `place()` layout chaining on every wrapper, with
  typed option dicts.
- Project operations scaffolding: CI on three OSes, PyPI publishing on tag,
  issue triage and fix automation, and the downstream reporting kit under
  `docs/tracking/kit/`.

[Unreleased]: https://github.com/GirthquakeMag11/tkfacade/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/GirthquakeMag11/tkfacade/releases/tag/v0.1.0
