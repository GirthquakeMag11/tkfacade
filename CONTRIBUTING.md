# Contributing to tkfacade

tkfacade is a shared library: downstream projects depend on exact pins and
discover pain points in real use. This document is the contract for every
change, human or automated. The full operations design lives in
[`docs/tracking/SPEC.md`](docs/tracking/SPEC.md); the current plan lives in
[`docs/tracking/ROADMAP.md`](docs/tracking/ROADMAP.md).

## The two principles

Every change is measured against the reason this library exists. A
downstream developer:

1. **must not need to violate a facade's encapsulation** to do something —
   if they must reach through a wrapper, that is a tkfacade gap;
2. **must not need to import stdlib `tkinter`** to do something — if they
   must, that is a tkfacade gap.

Gaps are filed as bugs or feature requests (see below) and fixed through the
normal flow. A PR whose diff would force either violation downstream is
rejected regardless of green CI. Fixes and features carry a
facade-principle check in their PR body confirming the change keeps both
promises.

## Filing bugs and features

- **From a downstream project**: use the reporting kit in
  [`docs/tracking/kit/`](docs/tracking/kit/README.md) — `/tkf-report-bug`
  and `/tkf-request-feature` verify first, then file via `gh`.
- **By hand**: the GitHub issue forms. Bugs need a minimal tkfacade-only
  reproduction; features need the use case and the pain point.

All tracking lives in GitHub Issues. Milestones are per version (`v0.2.0`,
...); the triage agent assigns them, `/plan` revises them.

## Development setup

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --all-extras --dev
```

Media tests need libmpv: `libmpv-dev` (Linux, plus `xvfb` for display),
`brew install mpv` (macOS, for local runs — macOS has no hosted CI, see
below), or the Git-LFS-vendored DLLs (Windows — clone with LFS enabled).
The vendored copy is development-only; distributions exclude it and find
libmpv on the system path.

## The verify gate

Every change must pass, in this order:

```sh
uv run ruff check src tests
uv run mypy src
xvfb-run uv run pytest -q      # plain `uv run pytest -q` on Windows/macOS
```

mypy runs strict; ruff enforces the lint set in `pyproject.toml`. Tests
needing a display carry the `gui` marker.

## PR flow

- Branch from `main`: `fix/<issue>-<slug>` for issue work, a descriptive
  name otherwise.
- Bug fixes require a regression test that fails before the fix and passes
  after.
- One-line imperative commit messages, repo style.
- PRs must pass the CI matrix (Ubuntu and Windows, full suite including
  media on both) before merge. macOS is not in CI: GitHub's macOS runners
  cannot run Tk at all, so macOS coverage waits on a self-hosted Mac
  runner (SPEC.md 6.2, ROADMAP backlog). Known Windows-only process
  crashes are deselected via `.github/ci/windows-deselect.txt`, each entry
  backed by an issue.
- `main` is protected: no direct pushes; required checks enforced.

## Automation lifecycle

Agents run in GitHub Actions on an OpenRouter key; both are opencode
sessions with the prompts versioned in `.github/prompts/`.

- **Triage agent** — on every new issue and nightly. Validates fields,
  attempts reproduction under xvfb, labels (`bug`/`enhancement` + area),
  comments a verdict (confirmed / suspected / duplicate / intended /
  incomplete), assigns milestones, closes duplicates, and applies
  `ready-to-fix` to scoped, confirmed work. It never edits repo files.
- **Fix agent** — dispatched for `ready-to-fix` issues (immediately after
  triage, or by the nightly batch), in parallel per issue with no volume
  caps: downstream throughput is the priority. Reproduces, fixes on a
  branch, adds the regression test, passes the verify gate, runs the
  facade-principle check, and opens a PR labeled `automerge`.
- **Escalation** — the maintainer is reachable *while agents run*, through
  the escalation relay (`ops/escalation/`): when an agent needs
  maintainer intent — ambiguous scope, a design decision, a principle
  conflict, a repro contradicting the report — it asks directly via its
  `ask_user` tool and blocks for the answer (2h window) instead of
  guessing. Every Q&A is recorded on the issue. If the window lapses or
  the relay is unreachable, the agent falls back to a GitHub escalation
  comment mentioning `@GirthquakeMag11` with the `escalation` label and
  stops; the nightly sweep re-routes once answered. Answer escalations
  in-thread.
- **Self-merge** — an hourly job merges `automerge` PRs whose CI has been
  green for 24h with no human objection. Comment, request changes, or
  remove the label to intervene; an intervened PR is never self-merged.
- **Stale policy** — idle issues get a comment after 30 days and close
  after 15 more. Milestones, `ready-to-fix`, `fix-in-progress`, and
  `escalation` are exempt.

Throughput is uncapped — no concurrency or per-night limits on fix runs;
the only ceilings are GitHub's job limits and the OpenRouter spend. The
regression-test, verify-gate, and principle-check guardrails are quality
gates and always apply.

## Labels

| Category | Labels |
| --- | --- |
| Type | `bug`, `enhancement`, `docs`, `ci`, `packaging` |
| Area | `widget`, `window`, `dialog`, `menu`, `media`, `observable`, `events`, `layout`, `core` |
| Provenance | `agent-submitted` |
| Automation | `triaged`, `ready-to-fix`, `fix-in-progress`, `escalation`, `automerge`, `stale` |

## Versioning and releases

- Semver-shaped, manual. During `0.x`, minor bumps may break the API;
  patch bumps must not. Python 3.14 only.
- `CHANGELOG.md` is compiled from the milestone's closed issues **before**
  the tag is pushed; the `/release` command (`.opencode/command/release.md`)
  runs the whole sequence: preflight checks, changelog, version bump, PR,
  tag.
- Pushing a `v*` tag triggers the release workflow: build, publish to PyPI
  via trusted publishing, and create the GitHub Release with artifacts.

## Consuming tkfacade downstream

Pin exactly — `uv add tkfacade==X.Y.Z` — and bump deliberately after
reading the changelog and release notes. Video playback additionally needs
the `media` extra and libmpv on the system path.
