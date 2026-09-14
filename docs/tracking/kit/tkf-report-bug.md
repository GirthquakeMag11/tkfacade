---
description: "Verify a supposed tkfacade bug and file it into the tkfacade GitHub tracker — reproduce against the installed library, rule out downstream misuse, dedupe, then gh issue create. Usage: /tkf-report-bug <description of the supposed bug>"
agent: build
---

File a verified tkfacade bug report into the upstream tracker. You are
running in a *downstream* project; the bug belongs to the `tkfacade`
library, and the report is filed against `GirthquakeMag11/tkfacade` — never
into this project's own ledgers or issue tracker.

## 1. Take the report

Description of the supposed bug: $ARGUMENTS

- **Empty**: stop and ask the user what happened, what was expected, which
  tkfacade surface is involved (widget/window/dialog/menu/media/observable/
  events), and any repro they have. Do not proceed on an empty description.
- **Given**: extract the claim and locate the tkfacade surface involved.
  Read the installed library's source (`uv run python -c "import tkfacade,
  pathlib; print(pathlib.Path(tkfacade.__file__).parent)"`) or its
  docstrings — enough to know what contract the claim says is broken.

## 2. Verify — before anything is filed

The report must be a tkfacade defect, not downstream misuse:

1. **Reproduce in isolation.** Build a minimal tkfacade-only reproduction —
   no downstream application code — and run it against the installed
   tkfacade (scratch under `/tmp/opencode`; prefix `xvfb-run` on Linux when
   a display is needed). Record the exact command and output.
2. **Rule out intended behavior.** Check the tkfacade README, the
   surface's docstrings, and any type signatures. Documented design is not
   a bug: if the behavior is the promise, tell the user with the citation
   and stop — unless the user still wants it filed as a feature request
   (then point them at `/tkf-request-feature`).
3. **Rule out downstream misuse.** Wrong option types, missing layout call,
   misuse of observables/commands — if the isolated repro does not show the
   defect, the finding is `suspected`, not confirmed.
4. **Verdict**: `confirmed` (isolated repro reproduces), `suspected`
   (genuine attempt failed — record exactly what was tried), or
   `not-a-bug` (intended behavior or downstream misuse — do not file).

## 3. Dedupe

Search the upstream tracker:

```sh
gh issue list -R GirthquakeMag11/tkfacade --state all --search "<keywords>"
```

If an existing issue matches, do not file a duplicate: report its URL to
the user and, if this verification adds evidence (a cleaner repro, a new
platform), append it as a comment on that issue instead. Stop there.

## 4. File

Gather the facts:

- **version**: `uv run python -c "from importlib.metadata import version; print(version('tkfacade'))"`
- **platform/OS** and **Python version** of this environment
- **reporting project**: this repo's name and current commit
  (`git remote get-url origin`, `git rev-parse --short HEAD`)

Then file with the bug form's exact fields:

```sh
gh issue create -R GirthquakeMag11/tkfacade \
  --title "[bug]: <short title>" \
  --label bug --label agent-submitted [--label <area>] \
  --body "<markdown>"
```

Area label (best effort, one of: `widget`, `window`, `dialog`, `menu`,
`media`, `observable`, `events`, `layout`, `core`): omit if unsure — the
triage agent corrects labels.

Body template:

```markdown
### tkfacade version
<version>

### Platform and OS
<platform>

### Python version
<python>

### Reporting project
<repo> @ <commit>

### Observed behavior
<what happens>

### Expected behavior
<what should happen, per the contract>

### Minimal reproduction
\`\`\`python
<tkfacade-only repro>
\`\`\`
Run: `<exact command>`

### Evidence
<output, traceback — or, for suspected reports, what was tried and the
verification verdict>

### Principle implicated
<Encapsulation violation / Forced stdlib tkinter import / Neither>

### Severity
<critical | high | medium | low>
```

## 5. Close out

- Summary to the user: the claim, the verification verdict, the issue URL
  (or the duplicate that was augmented), and the key evidence.
- No commits in this project; the command files nothing locally.
- Mid-flight questions go through the question tool only when they fit it
  (compact multiple-choice, ≤30-char header, 1–5-word option labels);
  anything else is decided from context and noted in the summary.
