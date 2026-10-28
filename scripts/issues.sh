#!/usr/bin/env bash
# Open, update or close this repository's two alert issues from one monitor run.
#   exit 1  open (or update) "monitor-down"; leave "monitor-coverage" as it is
#   exit 3  open (or update) "monitor-coverage"
#   exit 0  close both
#   exit 2  touch nothing: the monitor could not run, so nothing is known
# Opening an issue emails the repository's watchers. Updates edit the body, which
# sends no email, so a long outage is one email when it starts and one when it ends.
# Usage: scripts/issues.sh <exit code> <report file>
set -euo pipefail
code="$1"
report="$2"

gh label create monitor-down --color B60205 --description "A surface is down or answered wrong" --force >/dev/null
gh label create monitor-coverage --color FBCA04 --description "A surface could not be checked" --force >/dev/null

open_issue() {  # label title
  local number
  number="$(gh issue list --label "$1" --state open --json number --jq '.[0].number // empty')"
  if [ -n "$number" ]; then
    gh issue edit "$number" --body-file "$report" >/dev/null
    echo "updated #$number ($1)"
  else
    gh issue create --label "$1" --title "$2" --body-file "$report" >/dev/null
    echo "opened an issue ($1)"
  fi
}

close_issues() {  # label
  local number
  for number in $(gh issue list --label "$1" --state open --json number --jq '.[].number'); do
    gh issue close "$number" --comment "Recovered: every probe agreed at $(date -u +%Y-%m-%dT%H:%M:%SZ)." >/dev/null
    echo "closed #$number ($1)"
  done
}

case "$code" in
  0) close_issues monitor-down; close_issues monitor-coverage ;;
  1) open_issue monitor-down "Monitor: a surface is down or answered wrong" ;;
  3) open_issue monitor-coverage "Monitor: a surface could not be checked" ;;
  2) echo "the monitor could not run; no issue touched" ;;
  *) echo "unrecognized exit code $code; no issue touched" ;;
esac
