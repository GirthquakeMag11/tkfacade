# tkfacade Project Operations Specification

Status: draft for review. This document specifies the bug tracking, feature
planning, and CI/CD scaffolding that lets tkfacade grow as a shared dependency
of downstream projects. Once approved, a roadmap is derived from it (see
"Roadmap derivation") and building begins.

## 1. Purpose and principles

tkfacade is a typed, imperative wrapper library over tkinter, reused across
the maintainer's other projects. Two project-level principles govern every
decision in this spec and every change to the library:

1. **No encapsulation violations.** A downstream developer must never need to
   reach through a facade to do something. If they do, that is a tkfacade
   gap: a bug or a missing feature, and it gets tracked as one.
2. **No stdlib tkinter imports.** A downstream developer must never need to
   `import tkinter` to do something. Same treatment when violated.

Downstream projects are expected to surface pain points as bug reports and
feature requests. This spec defines how those reports are filed, triaged,
planned, fixed, and released back to the downstream projects.

### Roles

- **Maintainer** — GirthquakeMag11 (human). Final authority; runs
  human-gated commands (`/plan`, `/release`); reviews escalations.
- **Downstream agents** — opencode sessions in consuming projects. File
  verified reports into this repo's GitHub Issues via `gh` CLI using the
  shipped `/tkf-*` command kit.
- **Triage agent** — an LLM agent (opencode on an OpenRouter key) running in
  GitHub Actions on this repo. Classifies, labels, dedupes, assigns, closes.
- **Fix agent** — an LLM agent (opencode on an OpenRouter key) running in
  GitHub Actions on this repo. Turns `ready-to-fix` issues into PRs.

## 2. Bug tracking and feature requests

### 2.1 Location

All tracking lives in **GitHub Issues** on
`GirthquakeMag11/tkfacade`. No in-repo issue ledgers. `docs/tracking/` holds
process documents only (this spec, ROADMAP.md, CONTRIBUTING.md, the
downstream kit).

The global opencode commands `/bug-report`, `/bug-sweep`, and `/bug-fix`
(ledger-based, writing `docs/tracking/bugs.md` in whatever repo they run in)
are **not** used for tkfacade tracking and must not be pointed at this repo's
`docs/tracking/`. Downstream projects may still use them for their own local
ledgers; the tkf- kit (2.3) is what files against tkfacade.

### 2.2 Intake channels

1. **Agent-submitted** (primary): downstream opencode sessions run
   `/tkf-report-bug` or `/tkf-request-feature`, which verify first (2.3) and
   then `gh issue create -R GirthquakeMag11/tkfacade`.
2. **Manual**: GitHub issue forms (YAML, `.github/ISSUE_TEMPLATE/`) for the
   maintainer or anyone else filing by hand.

Both channels produce the same field set, so the triage agent sees one
shape. The forms and the agent convention are kept in sync by this spec.

**Bug report fields** (form inputs; agent convention maps 1:1):

- tkfacade version (exact pin in use)
- Platform / OS and Python version
- Reporting project (repo name, optionally commit) — empty for manual
- Observed behavior vs expected behavior
- Minimal reproduction: tkfacade-only code, no downstream app code
- Evidence: traceback, output, or what was tried
- Principle implicated: encapsulation / forced tkinter import / neither
  (free choice; drives area labels)

**Feature request fields:**

- Use case: what the downstream project was trying to do
- Pain point: what tkfacade currently forces instead
- Proposed surface: API sketch consistent with tkfacade conventions
  (master first, typed options, `grid()`/`pack()`/`place()` chaining)
- Principle served: which of the two principles (or neither)
- Alternatives considered / workarounds in use
- Reporting project

### 2.3 Downstream reporting kit

Shipped at `docs/tracking/kit/` as copy-paste opencode command templates for
downstream repos' `.opencode/command/`:

- **`/tkf-report-bug <description>`** — before filing, the downstream agent
  must verify the defect is in tkfacade, not downstream misuse: reproduce
  against the installed tkfacade in isolation (scratch under `/tmp/opencode`,
  `xvfb-run` where needed), rule out documented intended behavior (README,
  docstrings), and check existing issues via `gh issue list --search` to
  avoid duplicates (comment on / augment an existing issue instead). Files
  with labels `bug` + `agent-submitted` (+ best-effort area label) and the
  2.2 bug fields, repro and evidence included. If verification is
  inconclusive, the report is still filed but marked `suspected` in the body.
- **`/tkf-request-feature <description>`** — checks existing issues for
  duplicates, then files with labels `enhancement` + `agent-submitted`
  (+ best-effort area) and the 2.2 feature fields. The command elicits the
  use case from the developer's context, sketches a proposed surface, and
  cites the principle served.

Kit requirements: `gh` authenticated in the downstream environment with
permission to create issues on this repo. The kit documents that field
quality matters more than speed — the triage agent re-verifies, but a
verified repro saves a cycle.

### 2.4 Labels

| Category | Labels |
| --- | --- |
| Type | `bug`, `enhancement`, `docs`, `ci`, `packaging` |
| Area | `widget`, `window`, `dialog`, `menu`, `media`, `observable`, `events`, `layout`, `core` |
| Provenance | `agent-submitted` |
| Automation state | `triaged`, `ready-to-fix`, `fix-in-progress`, `escalation`, `automerge`, `stale` |

Severity is not a label; it is a body field (critical/high/medium/low)
carried over from the report contract the downstream agents already speak.
Closure of duplicates and won't-fixes uses GitHub close reasons plus a
comment, not labels.

## 3. Triage automation

An LLM agent runs inside GitHub Actions (opencode driven by an OpenRouter
API key stored as `OPENROUTER_API_KEY` secret; model pinned in workflow
config).

**Triggers:**

- Event: `issues.opened` (and `issues.edited` for substantial edits) —
  immediate triage of each new issue.
- Schedule: nightly sweep over all open, untriaged, or stale-state issues —
  catches stragglers, re-checks escalations that have been answered,
  re-validates labels/milestones.

**Authority (full):**

- Apply/correct type and area labels.
- Validate the report against the 2.2 field set; post a triage comment with
  the verdict: confirmed (repro reproduces or contract violation is clear),
  suspected (cannot reproduce; states what was tried), duplicate (closes,
  links original), intended behavior (closes with doc citation), or
  incomplete (comments requesting the missing fields; the stale policy
  eventually closes unanswered ones).
- Bug triage checks out the repo and attempts reproduction under xvfb where
  feasible; result goes in the triage comment.
- Assign milestones (per-version scheme, 4.1) and apply `ready-to-fix` to
  confirmed bugs and accepted features that are scoped small enough for the
  fix agent (5.2 scoping rules).
- Close duplicates and conflicting issues outright.
- The nightly sweep updates states the same way.

**Limits:** the triage agent never edits `ROADMAP.md` or any repo file, and
never pushes code. It operates on issues only (labels, milestones, comments,
open/close). Roadmap updates flow through `/plan` (4.2).

**No digest** is posted; issue state is the source of truth.

## 4. Feature planning

### 4.1 Milestones

Per-version: `v0.2.0`, `v0.3.0`, ... Each release closes its milestone.
Issues not targeted at a release carry no milestone. The triage agent
assigns; the maintainer adjusts via `/plan` or by hand.

### 4.2 ROADMAP.md and /plan

`docs/tracking/ROADMAP.md` records themes (e.g. API stabilization, docs,
media hardening), the milestone-to-theme mapping, and current status. It is
**seeded at build time by deriving from repo state**: a survey of README
promises vs implementation, docs gaps, test surface, `experiments/`
contents, and open issues — drafted for maintainer review, not invented.

Edits to ROADMAP.md happen only through **`/plan`**, a human-run
repo-local opencode command (`.opencode/command/plan.md`):

1. Reads open triaged issues, milestone assignments, and ROADMAP.md.
2. Proposes the next release's scope: which issues join which milestone,
   which themes advance, what is explicitly deferred.
3. Applies milestone changes via `gh` and rewrites ROADMAP.md.
4. Opens a PR with the roadmap diff (milestone changes take effect
   immediately; the PR documents them).

The maintainer runs `/plan` when planning a release or when the issue
backlog has shifted meaningfully.

## 5. Fix automation

### 5.1 Trigger and runtime

Label-gated: when the triage agent (or maintainer) applies `ready-to-fix`,
a workflow dispatches the fix agent — opencode in GitHub Actions on the same
`OPENROUTER_API_KEY` — against that issue. A nightly batch picks up any
`ready-to-fix` issues not yet attempted.

### 5.2 Scoping rules (what becomes ready-to-fix)

The fix agent handles issues that are: a confirmed bug with a reproduction,
or a small, well-specified feature whose proposed surface the triage agent
can state concretely. Large features, API redesigns, anything touching the
two principles ambiguously, and anything the triage agent cannot scope stay
unlabeled for human planning via `/plan`.

### 5.3 Fix workflow and guardrails

Per issue, the agent:

1. Reproduces the issue from its report (bugs must reproduce first; a
   failed repro attempt escalates instead of guessing).
2. Branches (`fix/<issue>-<slug>`), implements the minimal change following
   repo conventions.
3. **Regression test required**: adds/extends a test that fails before the
   fix and passes after.
4. **Local verify gate**: `uv run ruff check src tests`, `uv run mypy src`,
   `xvfb-run uv run pytest -q` must pass before the PR opens.
5. **Facade-principle check**: the agent reviews its own diff against the
   two principles (does the fix keep downstream from needing tkinter or
   breaking encapsulation?) and records the check in the PR body.
6. Opens a PR: body links the issue (`Closes #N`), includes repro, fix
   summary, test added, verify-gate results, and the principle check.
7. One fix attempt per issue. Failure at any step → escalation (5.4), not a
   retry loop.

**Budget caps (conservative):** max 3 concurrent fix runs; nightly batch
caps at 5 issues; one attempt per issue before escalation. Model choice and
caps are workflow-config values, revisited as spend is observed.

### 5.4 Escalation — direct channel to the maintainer

When the agent is blocked (repro fails, fix exceeds scope, verify gate red
after a genuine attempt, design decision needed, principle conflict), it:

1. Posts an escalation comment **on the issue**, mentioning
   `@GirthquakeMag11`, stating precisely what is blocked and what decision
   or information is needed.
2. Applies the `escalation` label and removes `ready-to-fix`.
3. Stops work on that issue.

The maintainer answers in-thread. The nightly triage sweep detects answered
escalations: it re-applies `ready-to-fix` (with the answer folded into the
issue context) or re-routes the issue per the maintainer's reply.

### 5.5 Merge policy — self-merge when green

- A fix-agent PR carries an `automerge` label.
- CI (full 3-OS matrix) must be green.
- A scheduled merge job (hourly) merges `automerge` PRs that have been green
  for **24h** with no maintainer objection (no `changes-requested` review,
  no human comment, no `escalation`).
- Merging closes the linked issue automatically; the triage sweep confirms
  closure state.
- The maintainer can intervene any time before merge by commenting,
  requesting changes, removing `automerge`, or closing the PR. An intervened
  PR is never self-merged.
- Branch protection on `main`: required status checks = the CI matrix; the
  automation bot is permitted to merge; direct pushes are not (the
  maintainer works through PRs too).

## 6. Development flow and CI

### 6.1 Flow

PR-based for everything: agent fix PRs, `/plan` roadmap PRs, maintainer
work. Releases are tagged from `main`. Conventional-commit style is not
required; repo-style one-line imperative messages continue.

### 6.2 CI matrix

`ci.yml` runs on push to `main` and on every PR:

- **OS**: `ubuntu-latest`, `windows-latest`, `macos-latest`.
- **Python**: 3.14 only (matches `requires-python >= 3.14`).
- **Tooling**: uv (pinned, cached).
- **System deps for full media tests everywhere**:
  - Ubuntu: `libmpv-dev`, `xvfb` (tests run under `xvfb-run`).
  - Windows: the Git-LFS-vendored `src/tkfacade/media/libmpv` DLLs
    (checkout with `lfs: true`).
  - macOS: `mpv` via Homebrew.
- **Steps**: `uv sync --all-extras --dev`, `ruff check src tests`,
  `mypy src`, full `pytest` suite (including gui-marked tests under the
  virtual display / native display per OS).

The media extra is exercised on all three platforms; no smoke-only jobs.

## 7. Release and delivery

### 7.1 Versioning

- Semver-shaped manual versioning in `pyproject.toml`, starting at 0.1.0.
  0.x: minor bumps may break API; patch bumps must not.
- Python 3.14 only.

### 7.2 CHANGELOG.md

Manual, maintainer-or-/release-maintained at repo root. Sections per version
(Added / Changed / Fixed), compiled from the milestone's closed issues.
Updated **before** the tag is pushed.

### 7.3 Release flow — manual bump + tag trigger

A repo-local **`/release`** command (human-run) performs:

1. Verify `main` CI is green and the milestone is empty (all issues closed
   or moved).
2. Compile the CHANGELOG.md section from closed milestone issues.
3. Bump `version` in `pyproject.toml`, commit (`Release vX.Y.Z`), open a PR,
   and after merge tag `vX.Y.Z` on `main` and push the tag.

(Steps may be done by hand identically; the command exists to keep the order
and the checks consistent.)

### 7.4 CD — PyPI

- Package name **`tkfacade`** (verified available on PyPI at spec time).
- Tag push `v*` triggers `release.yml`:
  1. Build sdist + wheel with `uv build` (the existing hatch build config
     stands: vendored libmpv excluded from distributions; installed
     tkfacade finds libmpv on the system path, `tkfacade[media]` for the
     python-mpv dependency).
  2. Publish via **PyPI trusted publishing** (OIDC; `pypa/gh-action-pypi-publish`).
     One-time setup: a PyPI project `tkfacade` configured to trust this
     repo's `release.yml` workflow. No API tokens stored.
  3. Create a **GitHub Release** for the tag with the CHANGELOG section as
     notes and the built artifacts attached.
- **First release**: once CI/CD is green on the scaffolded repo, tag and
  publish **v0.1.0** immediately so downstream projects can depend on it
  from day one.

### 7.5 Consumption policy (downstream)

- Downstream projects pin exactly: `uv add tkfacade==X.Y.Z`, bumping
  deliberately after reading the CHANGELOG and GitHub Release notes.
- Documented in README and CONTRIBUTING.md.

## 8. Repository automation (non-agent)

- **Stale issues**: `actions/stale` (or equivalent). Idle 30 days → comment;
  15 more days → close. Exempt: issues with a milestone, `ready-to-fix`,
  `escalation`, or an open linked PR.
- **Dependency updates**: **Dependabot**, weekly, two ecosystems: `uv`
  (pip) for dev/runtime deps and `github-actions` for workflow action
  versions. Auto-merge for patch-level action bumps is acceptable; library
  bumps go through normal PR review.

## 9. Contributor documentation

- **CONTRIBUTING.md** (repo root): the two principles as acceptance criteria
  for every change; the PR flow; how to run the verify gate locally
  (ruff/mypy/pytest+xvfb); the release/versioning policy; the downstream
  consumption policy; how automation works (triage, fix agent, escalation,
  self-merge) so contributors understand the `automerge`/`escalation`
  lifecycle.
- **docs/tracking/kit/README.md**: how a downstream project installs the
  `/tkf-*` commands and what `gh` permissions it needs.
- **Principle enforcement** is three-layered: the fix agent's self-check
  (5.3.5), triage's principle field on intake (2.2), and CONTRIBUTING.md as
  the human-facing contract. A PR whose diff forces downstream tkinter use
  or encapsulation violations is rejected in review regardless of green CI.

## 10. Secrets and settings inventory

| Item | Where | Notes |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | repo Actions secret | triage + fix agents |
| PyPI trusted publishing | pypi.org project config | trusts `release.yml` on this repo; no secret stored |
| Branch protection on `main` | repo settings | required checks = CI matrix; bot merge allowed; direct push disallowed |
| Labels | repo settings | the 2.4 set, created by scaffold |
| Issue forms | `.github/ISSUE_TEMPLATE/*.yml` | bug + feature, matching 2.2 |
| Dependabot | `.github/dependabot.yml` | uv + github-actions, weekly |
| Stale config | workflow | 30/15, exemptions per 8 |
| Automation bot identity | workflow `GITHUB_TOKEN` or a dedicated bot PAT if the token cannot self-merge under branch protection | decided at build time |

## 11. Repository deliverables (build targets)

```text
.github/
  ISSUE_TEMPLATE/bug_report.yml
  ISSUE_TEMPLATE/feature_request.yml
  ISSUE_TEMPLATE/config.yml
  prompts/triage.md           # triage agent instructions (versioned)
  prompts/fix.md              # fix agent instructions (versioned)
  scripts/automerge.sh        # 24h-green automerge logic
  workflows/ci.yml            # 3-OS matrix (upgrade of existing)
  workflows/release.yml       # tag -> build -> PyPI (OIDC) -> GitHub Release
  workflows/triage.yml        # issues.opened + nightly sweep
  workflows/fix.yml           # ready-to-fix -> fix agent -> PR
  workflows/automerge.yml     # hourly 24h-green automerge job
  workflows/stale.yml
  dependabot.yml
.opencode/command/
  plan.md                     # /plan  (roadmap + milestone planning)
  release.md                  # /release (changelog, bump, tag)
  fix-issue.md                # manual fallback: fix a specific issue locally
docs/tracking/
  SPEC.md                     # this document
  ROADMAP.md                  # seeded from repo-state survey
  kit/
    README.md
    tkf-report-bug.md
    tkf-request-feature.md
CHANGELOG.md
CONTRIBUTING.md
README.md                    # add: releases, consumption policy, links
```

## 12. Roadmap derivation and build order

After this spec is approved:

1. **Survey & seed** — derive initial ROADMAP.md themes and the v0.2.0
   milestone candidate list from repo state (README promises vs
   implementation, docs gaps, test surface, `experiments/`), for maintainer
   review.
2. **Tracking scaffold** — labels, issue forms, CONTRIBUTING.md, downstream
   kit, CHANGELOG.md skeleton.
3. **CI upgrade** — 3-OS matrix with full media tests; verify green.
4. **CD** — release.yml, PyPI trusted-publishing setup (one maintainer step
   on pypi.org), tag **v0.1.0**, confirm installability downstream.
5. **Triage agent** — triage.yml event + nightly; observe on seeded test
   issues before granting routine full authority.
6. **Fix agent** — fix.yml + automerge.yml + escalation flow; branch
   protection configured; observe first cycles under the budget caps.
7. **Housekeeping automation** — stale.yml, dependabot.yml.

Each step is independently verifiable; steps 5–6 run in observation mode
(agent comments proposals, maintainer applies) for their first cycle if the
maintainer prefers before full authority engages.

## 13. Open implementation decisions (build time)

- Exact OpenRouter models for triage vs fix agents (cost/capability split),
  pinned in workflow config.
- Bot identity for self-merge under branch protection (`GITHUB_TOKEN`
  sufficiency vs dedicated bot app/PAT).
- Whether the triage nightly sweep and the fix nightly batch share one
  schedule slot.
- Windows CI confirmation that the LFS-vendored libmpv DLLs load under the
  test suite (fallback: winget/choco mpv install).
