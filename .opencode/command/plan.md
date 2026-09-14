---
description: "Plan the next release: group triaged issues into milestones, update docs/tracking/ROADMAP.md, and open the roadmap PR. Usage: /plan [milestone]"
agent: build
---

Run the planning pass defined in `docs/tracking/SPEC.md` 4.2. You operate on
GitHub Issues directly and on `ROADMAP.md` through a PR; milestone
assignments take effect immediately, the roadmap diff is reviewed.

## 1. Load state

Optional milestone argument: $ARGUMENTS

- Read `docs/tracking/SPEC.md` (sections 3-5) and `docs/tracking/ROADMAP.md`.
- `gh issue list --state open --json number,title,labels,milestone,updatedAt`
  (paginate with `--limit 200` as needed).
- `gh api repos/GirthquakeMag11/tkfacade/milestones?state=open`
- If a milestone argument was given, it is the planning target (create it
  with `gh api` if it does not exist — per-version naming `vX.Y.Z`, next
  number derived from the existing set). Otherwise the target is the
  earliest open milestone, or a newly proposed next version.

## 2. Propose the scope

Group the open triaged issues into a proposal:

- what joins the target milestone (confirmed bugs first by severity, then
  accepted features, then docs/ci/packaging);
- what stays unassigned (backlog) or moves to a later milestone, with a
  one-line reason each;
- which ROADMAP.md themes advance, and the status line changes.

Confirm through the question tool once: adopt as proposed / adjust (user
types the change) / cancel. This is the only upfront question.

## 3. Apply milestone assignments

For every issue in the confirmed scope:

```sh
gh issue edit <n> --milestone "<vX.Y.Z>"
```

Issues leaving the milestone get `--milestone` cleared via
`gh api ... -f milestone=`(empty). Report every change.

## 4. Update ROADMAP.md

Rewrite the affected sections only:

- the milestone's scope bullets to match what was just assigned;
- theme statuses (`active` / `next` / `later` / `dormant`) where the
  assignments shifted them;
- append a dated entry to the status log: what was planned, into which
  milestone, counts.

Keep the file's voice: prose scopes, issues are authoritative for items,
the roadmap records themes and milestone scope only.

## 5. Open the roadmap PR

```sh
git checkout -b plan/<vX.Y.Z>
git add docs/tracking/ROADMAP.md
git commit -m "Plan <vX.Y.Z> in the roadmap"
git push -u origin plan/<vX.Y.Z>
gh pr create --title "Plan <vX.Y.Z>" --body "<summary: scope adopted, issues assigned, deferrals>"
```

Stage only `ROADMAP.md`. Check `git status` and the staged diff first;
never sweep unrelated state; no force-push, no amend.

## 6. Close out

Summary: milestone targeted, issues assigned (numbers + titles), issues
deferred with reasons, PR URL. Mid-flight questions go through the question
tool only when they fit it (compact multiple-choice, ≤30-char header, 1-5
word option labels); anything else is decided from the spec and noted.
