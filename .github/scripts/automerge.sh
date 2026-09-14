#!/usr/bin/env bash
# Merge `automerge`-labeled PRs whose required checks have all been green
# for at least 24h and which carry no human objection (comment or review by
# a non-bot actor). SPEC.md 5.5.
set -euo pipefail

WINDOW_SECONDS=$((24 * 3600))
CUTOFF=$(( $(date +%s) - WINDOW_SECONDS ))
BOT_LOGINS='["github-actions[bot]", "dependabot[bot]", "renovate[bot]"]'

prs=$(gh pr list --label automerge --state open --json number --jq '.[].number')
if [ -z "$prs" ]; then
  echo "No open automerge PRs."
  exit 0
fi

for pr in $prs; do
  echo "== PR #${pr}"
  data=$(gh pr view "$pr" --json statusCheckRollup,reviews,comments)

  # 1. Every check concluded successfully; none pending.
  not_green=$(jq -r '
    [.statusCheckRollup[]
     | select((.conclusion // "") as $c
              | ($c != "SUCCESS" and $c != "NEUTRAL" and $c != "SKIPPED"))]
    | length' <<<"$data")
  if [ "$not_green" != "0" ] || [ "$(jq '.statusCheckRollup | length' <<<"$data")" = "0" ]; then
    echo "   not green (or no checks yet) — waiting"
    continue
  fi

  # 2. Green for at least 24h: the latest check completion is past cutoff.
  green_since=$(jq -r '[.statusCheckRollup[].completedAt // empty] | max // empty' <<<"$data")
  if [ -z "$green_since" ]; then
    echo "   no check completion timestamps — waiting"
    continue
  fi
  green_epoch=$(date -u -d "$green_since" +%s)
  if [ "$green_epoch" -gt "$CUTOFF" ]; then
    remaining=$(( (green_epoch + WINDOW_SECONDS - $(date +%s)) / 3600 + 1 ))
    echo "   green for under 24h (~${remaining}h left) — waiting"
    continue
  fi

  # 3. No human objection: any comment or review by a non-bot actor hands
  #    the PR to the maintainer for good.
  objections=$(jq --argjson bots "$BOT_LOGINS" -r '
    ([.comments[].author.login] + [.reviews[].author.login])
    | map(select(. as $l | ($bots | index($l)) | not))
    | unique | length' <<<"$data")
  if [ "$objections" != "0" ]; then
    echo "   human activity on the PR — left to the maintainer"
    continue
  fi

  echo "   green >24h, no objection — merging"
  gh pr merge "$pr" --merge --delete-branch
done
