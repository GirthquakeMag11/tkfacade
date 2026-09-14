---
description: "Cut a release: preflight checks, compile CHANGELOG from the milestone, bump the version, PR, tag, and watch the PyPI publish. Usage: /release [version]"
agent: build
---

Run the release flow defined in `docs/tracking/SPEC.md` 7.3. Nothing here
publishes by itself — the tag push at the end triggers `release.yml`.

## 1. Preflight — all must hold, or stop

Optional version argument: $ARGUMENTS

1. Working tree clean (`git status`), on `main`, up to date with origin.
2. CI green on latest `main`:
   `gh run list --branch main --workflow ci.yml --limit 1` shows
   `completed` / `success`.
3. The target milestone exists and is empty of open issues:
   `gh issue list --milestone <vX.Y.Z> --state open` returns nothing.
4. Version: from the argument, else propose the next per the 0.x policy in
   CONTRIBUTING.md (minor may break API, patch must not) based on what the
   milestone contains; confirm through the question tool.
5. No existing tag `vX.Y.Z` (`git tag -l`).

Report any failure and stop — do not paper over a red preflight.

## 2. Compile the CHANGELOG section

```sh
gh issue list --milestone <vX.Y.Z> --state closed --json number,title,labels --limit 200
```

Group into Added / Changed / Fixed by type label (`enhancement` → Added or
Changed by nature of the title, `bug` → Fixed, others by judgment). Write
the `## [X.Y.Z] - <today>` section into `CHANGELOG.md` above the previous
release, move anything under `## [Unreleased]` into it, and update the
compare links at the bottom. One line per issue: `- <title> (#<n>)`.

## 3. Bump and PR

1. Set `version = "X.Y.Z"` in `pyproject.toml`.
2. `uv lock` to refresh `uv.lock`.
3. Branch, commit, PR:

```sh
git checkout -b release/vX.Y.Z
git add CHANGELOG.md pyproject.toml uv.lock
git commit -m "Release vX.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --title "Release vX.Y.Z" --body "<changelog section + milestone summary>"
```

## 4. Merge, tag, publish

Wait for CI on the PR, then ask through the question tool: merge now
(`gh pr merge --merge`) or the user merges manually — resume after. Then:

```sh
git checkout main && git pull
git tag vX.Y.Z && git push origin vX.Y.Z
```

Watch the release run: `gh run watch` on the triggered `release.yml`. On
success verify both artifacts:

- `curl -s https://pypi.org/pypi/tkfacade/json | python -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"`
  reports X.Y.Z;
- `gh release view vX.Y.Z` exists with the notes and the sdist/wheel
  attached.

## 5. Close out

Close the milestone (`gh api -X PATCH .../milestones/<n> -f state=closed`).
Summary: version, changelog line count, PR URL, tag, PyPI version seen,
GitHub Release URL. On any publish failure: report the run logs, do not
re-tag; a failed PyPI upload is re-run from the Actions UI (tags are
immutable — never move a tag).
