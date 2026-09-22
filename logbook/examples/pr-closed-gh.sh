#!/bin/sh
# Exit 0 PR merged or closed, 1 still open, 2 unknown. gh exits 1 for
# "no such PR" and for "not logged in" alike, so the verdict is read
# off the state field, never off gh's own exit code.
#
# Runs in the checkout the entry was written from, so gh resolves the
# repository the way it did when the PR was recorded.
[ -n "$LOGBOOK_PR" ] || exit 2
[ -d "$LOGBOOK_REPO_PATH" ] || exit 2
state=$(cd "$LOGBOOK_REPO_PATH" && \
        gh pr view "$LOGBOOK_PR" --json state --jq .state 2>/dev/null) \
  || exit 2
case "$state" in
  MERGED|CLOSED) exit 0 ;;
  OPEN) exit 1 ;;
  *) exit 2 ;;
esac
