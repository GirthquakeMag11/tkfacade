# Downstream reporting kit

Copy-paste opencode commands that let a project consuming tkfacade file
verified bug reports and feature requests into the tkfacade tracker
(GitHub Issues on `GirthquakeMag11/tkfacade`).

## Install

Copy both command files into the downstream repo's opencode command
directory:

```sh
mkdir -p .opencode/command
cp <path-to-tkfacade>/docs/tracking/kit/tkf-report-bug.md .opencode/command/
cp <path-to-tkfacade>/docs/tracking/kit/tkf-request-feature.md .opencode/command/
```

(Or into `~/.config/opencode/command/` to make them available in every
project. The names are namespaced `tkf-` precisely so they never collide
with the ledger-based global `/bug-report`, `/bug-sweep`, and `/bug-fix`
commands — those track a project's own local ledger and must not be pointed
at tkfacade.)

## Requirements

- `gh` CLI authenticated (`gh auth status`) with permission to create issues
  on `GirthquakeMag11/tkfacade` — any authenticated GitHub user can, the
  repo being public.
- tkfacade installed in the downstream project (the commands verify against
  the installed library).

## Usage

```text
/tkf-report-bug     <description of the supposed tkfacade bug>
/tkf-request-feature <description of the missing capability>
```

Both commands verify before filing: the bug command reproduces against the
installed tkfacade in isolation and rules out downstream misuse and
documented intended behavior; the feature command grounds the pain point in
the actual code path being used. Both deduplicate against existing issues.
A verified report saves the tkfacade triage agent a cycle — field quality
matters more than filing speed.

## What gets filed

Issues carry the `agent-submitted` provenance label plus the type label
(`bug` / `enhancement`) and a best-effort area label, with exactly the
fields of the tkfacade issue forms (SPEC.md 2.2): version, platform, Python,
reporting project, observed/expected, minimal tkfacade-only reproduction,
evidence, principle implicated, severity. The tkfacade triage agent
re-verifies every report, assigns milestones, and routes it into the fix
pipeline; escalations and status live on the issue thread.
