---
description: "Ground a missing-capability pain point in the downstream code, then file a feature request into the tkfacade GitHub tracker via gh. Usage: /tkf-request-feature <description of the missing capability>"
agent: build
---

File a tkfacade feature request into the upstream tracker. You are running
in a *downstream* project; the request is filed against
`GirthquakeMag11/tkfacade` — never into this project's own tracker.

## 1. Take the request

Description of the missing capability: $ARGUMENTS

- **Empty**: stop and ask the user what they were trying to do, what
  tkfacade forces instead, and any API shape they have in mind. Do not
  proceed on an empty description.
- **Given**: locate the downstream code path that hits the gap — the file
  and the workaround currently in use (raw `tkinter` import? reaching
  through a facade via a private attribute? restructuring the UI around the
  limitation?). The pain point must be grounded in real code, not imagined.

## 2. Classify the principle

Determine which project principle the gap implicates (this drives upstream
priority):

- **Encapsulation** — downstream must bypass or break a facade's
  encapsulation to get the behavior.
- **No stdlib tkinter** — downstream must `import tkinter` to get the
  behavior.
- **Both**, or **Neither** (pure convenience/API growth).

## 3. Sketch the proposed surface

Draft an API sketch consistent with tkfacade conventions: master first,
typed options at construction, typed mutable properties, `grid()` /
`pack()` / `place()` chaining. Read the neighboring tkfacade surfaces in
the installed library for the house style. The sketch is a proposal, not a
demand — keep it short.

## 4. Dedupe

```sh
gh issue list -R GirthquakeMag11/tkfacade --state all --search "<keywords>"
```

If the capability is already requested, do not file a duplicate: report the
existing issue's URL and, if this project adds a new use case, append it as
a comment there. Also check whether the capability already exists in the
installed tkfacade version under a different name — read the package
exports (`dir(tkfacade)`) before filing. Stop if either applies.

## 5. File

Gather: this repo's name and current commit, and the installed tkfacade
version. Then:

```sh
gh issue create -R GirthquakeMag11/tkfacade \
  --title "[feature]: <short title>" \
  --label enhancement --label agent-submitted [--label <area>] \
  --body "<markdown>"
```

Area label (best effort, one of: `widget`, `window`, `dialog`, `menu`,
`media`, `observable`, `events`, `layout`, `core`): omit if unsure — the
triage agent corrects labels.

Body template:

```markdown
### Use case
<what the downstream project was trying to do, with the file/path that hits
the gap>

### Pain point
<what tkfacade currently forces instead — quote the workaround in use>

### Proposed surface
\`\`\`python
<API sketch>
\`\`\`

### Principle served
<Encapsulation / No stdlib tkinter import / Both / Neither>

### Alternatives and workarounds
<what is used today; how costly it is to keep>

### Reporting project
<repo> @ <commit>, tkfacade <version>
```

## 6. Close out

- Summary to the user: the use case, the principle classification, the
  issue URL (or the duplicate augmented), and the proposed surface.
- No commits in this project; the command files nothing locally.
- Mid-flight questions go through the question tool only when they fit it
  (compact multiple-choice, ≤30-char header, 1–5-word option labels);
  anything else is decided from context and noted in the summary.
