#!/bin/sh
# Exit 0 ticket closed, 1 still open, 2 unknown. "Closed" must be a
# positive finding: an expired token, a 404 on a deleted issue and a
# network failure all have to hold the entry, not retire it.
#
# Needs JIRA_EMAIL and JIRA_API_TOKEN, forwarded by naming them in
# retire.env_passthrough. Reads the status category, not the status
# name, so a workflow whose final column is "Shipped" still counts.
[ -n "$JIRA_EMAIL" ] && [ -n "$JIRA_API_TOKEN" ] || exit 2
out=$(curl -sS --fail-with-body --max-time 20 \
        -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
        -H "Accept: application/json" \
        "https://myorg.atlassian.net/rest/api/3/issue/$LOGBOOK_TICKET?fields=status" \
        2>/dev/null) || exit 2
category=$(printf '%s' "$out" | python3 -c '
import json, sys
try:
    doc = json.load(sys.stdin)
    print(doc["fields"]["status"]["statusCategory"]["key"])
except Exception:
    sys.exit(2)
') || exit 2
case "$category" in
  done) exit 0 ;;
  new|indeterminate) exit 1 ;;
  *) exit 2 ;;
esac
