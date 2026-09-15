# tkfacade Roadmap

Seeded 2026-09-13 from a repo-state survey, per `SPEC.md` section 12.1.
Edited only through the `/plan` flow (SPEC.md 4.2): milestone assignments on
GitHub Issues are the authoritative plan; this document records themes,
milestone scope, and status. Issues, not this file, track individual work
items.

Legend: `active` (being worked now), `next` (scoped, not started),
`later` (direction only), `dormant` (parked).

## Themes

### T1 — Distribution and delivery — active

Get tkfacade installable and releasable: the CI matrix, the tag-triggered
PyPI pipeline, trusted publishing, CHANGELOG, and the v0.1.0 release. This
theme is the SPEC.md section 12 build itself; it completes when v0.1.0 is on
PyPI and downstream projects pin `tkfacade==0.1.0`.

### T2 — Platform hardening — next

The suite (688 tests, 83 gui-marked) had only ever run on Linux under
xvfb. The CI matrix now runs the full suite on Ubuntu (xvfb) and Windows
(native headless) — macOS is out of hosted CI entirely: GitHub's macOS
runners have no window server and no Xvfb equivalent, so no GUI test can
run there, and for a GUI library a non-GUI subset proves too little to be
worth a required job (SPEC.md 6.2). Windows first-run findings are being
deselected-and-filed per crash (`.github/ci/windows-deselect.txt`): a
read-only-input keyboard crash (#5) and an mpv render-context teardown
race. Scope: get the matrix green, shrink the deselect list to zero, and
keep it green.

### T3 — Documentation integrity — next

Fix the drift the survey found, then close the structural gaps:

- `examples/README.md` claimed the directory was empty while `showcase.py`
  exists and is substantial. (Fixed in the v0.1.0 scaffold.)
- The root README's widget list omitted exported families: progressbar,
  choice, scroll, `TitleEntry`, `TextBox`, and the media helper set.
  (Fixed in the v0.1.0 scaffold.)
- `experiments/README.md`'s references to `hazards/tkinter.md` and the
  `ttk Style Options` note point at the maintainer's external vault, not
  repo files — no drift, left as-is.
- CONTRIBUTING.md and the downstream kit docs (SPEC.md build targets).
- Later: an API reference beyond README + docstrings (decision deferred
  until downstream demand justifies a docs site).

### T4 — Downstream feedback loop — next

The automation that lets consuming projects drive this library: issue
forms, labels, triage agent, fix agent, escalation, stale policy,
Dependabot. Completes when a `/tkf-report-bug` filed from a downstream
project is triaged, fixed, and released end-to-end without manual GitHub
clicking.

### T5 — API growth from experiments — later

Unsettled probes in `experiments/` are the feature pipeline; each graduates
into the library when a downstream need (or a sweep finding) justifies it:

- `modality_probe` — dialog modality surface
- `observable_settle` — observable completion/settling semantics
- `input_state_probe` — input-state queries on the observer
- `ttk_style_probe` — Look/style coverage per ttk widget
- `interception_setup` — dormant, Windows-only; stale test paths; decide
  keep-or-delete
- `composite_events`, `async_route`, `event_bind`, `scroll_view` — already
  informed shipped surfaces; remain as witnesses

Growth here is demand-driven: feature requests from downstream projects are
the primary input, per SPEC.md section 4.

## Milestones

### v0.1.0 — first release (active)

Scope is exactly the SPEC.md section 12 build order:

1. Tracking scaffold: labels, issue forms, CONTRIBUTING.md, downstream kit,
   CHANGELOG.md
2. CI upgrade: 3-OS matrix, full media tests everywhere, green
3. CD: release.yml, PyPI trusted publishing, GitHub Release automation
4. Triage agent (event + nightly)
5. Fix agent (ready-to-fix gate, automerge, escalation)
6. Stale policy + Dependabot
7. Tag and publish v0.1.0

Plus the T3 quick wins found by the survey (stale examples README, root
README widget list) — small, safe, and they make the first published face
of the library accurate.

### v0.2.0 — first downstream cycle (next)

Candidate scope; concrete items become issues once the tracker is live and
are assigned by `/plan` or triage:

- Platform fixes surfaced by T2 (expected: the bulk of this milestone)
- First downstream bug reports and accepted feature requests
- Resolution of the `interception_setup` keep-or-delete decision
- Any principle violations (forced tkinter imports, encapsulation gaps)
  reported from consuming projects

### Backlog (no milestone)

- macOS support: a self-hosted runner on real Mac hardware (logged-in user
  session) is the only path to macOS GUI testing. Blocked on hardware;
  demand-driven — downstream macOS projects wait until this exists.
- API reference / docs-site decision (T3, later half)
- Experiment graduations from T5 without downstream demand yet
- Python 3.13 support if a downstream project ever needs it (currently
  3.14-only by design)

## Status log

- 2026-09-13 — Roadmap seeded from repo-state survey (SPEC.md 12.1).
  No issues filed yet; tracker goes live with the v0.1.0 build.
- 2026-09-15 — v0.1.0 build underway: scaffold committed, labels and
  milestones created, first matrix runs analyzed. macOS dropped from the
  matrix (hosted runners cannot run Tk at all; backlog item added for the
  self-hosted-Mac path). Windows crashes being deselected and filed
  (#5 keyboard edit; mpv teardown race next).
