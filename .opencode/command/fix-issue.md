---
description: "Fix a GitHub issue locally: reproduce, branch, minimal fix with a fail-first regression test, verify gate, PR that closes the issue. Usage: /fix-issue <issue-number>"
agent: build
---

The manual counterpart to the automated fix agent (SPEC.md section 5) — same
guardrails, run locally by the maintainer. You do the work yourself; no
subagents.

## 1. Load the issue

Issue number: $ARGUMENTS

- **Empty**: stop and ask which issue.
- `gh issue view <n> --json number,title,body,labels,milestone,comments` —
  read the triage comment and any escalation thread before touching code.
- An issue labeled `escalation` is worked only with its thread's answer in
  hand; otherwise stop and say why.

## 2. Reproduce

Run the report's reproduction (scratch under `/tmp/opencode`;
`xvfb-run` on Linux). A bug that will not reproduce gets one genuine second
attempt (read the implicated code first), then: comment the failed attempt
on the issue, apply `escalation`, remove `ready-to-fix`, and stop.

## 3. Fix

1. Branch: `git checkout -b fix/<n>-<slug>`.
2. Minimal change that resolves the reported behavior, following repo
   conventions (read the surrounding module and its tests first).
3. **Regression test**: add or extend a test in `tests/` that fails before
   the fix and passes after — verify fail-first by running it against the
   pre-fix code (stash the fix). Follow the existing layout; mark it `gui`
   if it needs a display.
4. **Facade-principle check**: re-read the diff against CONTRIBUTING.md's
   two principles — the fix must not force downstream tkinter imports or
   encapsulation violations.

## 4. Verify gate

```sh
uv run ruff check src tests
uv run mypy src
xvfb-run uv run pytest -q
```

Red after a genuine attempt: revert, record the blocker as an issue comment
(the escalation format from SPEC.md 5.4), and stop. Do not push red.

## 5. Ship the PR

```sh
git add <only the files this fix touched>
git commit -m "Fix #<n> — <title>"
git push -u origin fix/<n>-<slug>
gh pr create --title "Fix #<n> — <title>" --body "<body below>"
```

Check `git status` and the staged diff first; never sweep unrelated state;
no amend, no force-push. PR body:

```markdown
Closes #<n>

**Repro:** <the verified reproduction, condensed>
**Fix:** <what changed and why it is minimal>
**Test:** <test added, fail-first verified>
**Verify gate:** ruff / mypy / pytest — all green
**Facade-principle check:** <one line per principle>
```

No `automerge` label on manual PRs — the maintainer merges after review.
Remove `ready-to-fix` from the issue if present; the PR closing the issue
on merge ends the lifecycle.

## 6. Close out

Summary: issue, verdict, branch, PR URL, verify-gate state. Mid-flight
questions through the question tool only when they fit it; anything else is
decided from repo conventions and noted.
