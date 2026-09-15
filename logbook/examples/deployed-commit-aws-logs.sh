#!/bin/sh
# Prints the commit last deployed for $LOGBOOK_SERVICE at
# $LOGBOOK_STAGE. Paging matters: filter-log-events caps a page at 1MB
# and without --start-time the first page is arbitrary, so a recent
# deploy goes missing.
set -e
start=$(( ($(date +%s) - 30 * 86400) * 1000 ))
token=""
best=""
best_ts=""
while : ; do
  if [ -n "$token" ]; then
    page=$(aws logs filter-log-events --region REGION --profile PROFILE \
             --log-group-name "/my-deploy-logs/$LOGBOOK_STAGE" \
             --start-time "$start" --output json --next-token "$token")
  else
    page=$(aws logs filter-log-events --region REGION --profile PROFILE \
             --log-group-name "/my-deploy-logs/$LOGBOOK_STAGE" \
             --start-time "$start" --output json)
  fi
  row=$(printf '%s' "$page" | jq -r --arg svc "$LOGBOOK_SERVICE" '
    [.events[].message | fromjson? | select(.service == $svc)]
    | sort_by(.timestamp) | last | select(.) | "\(.timestamp) \(.commit)"')
  if [ -n "$row" ]; then
    ts=${row%% *}
    if [ -z "$best_ts" ] || [ "$ts" \> "$best_ts" ]; then
      best_ts=$ts
      best=${row##* }
    fi
  fi
  token=$(printf '%s' "$page" | jq -r '.nextToken // empty')
  [ -n "$token" ] || break
done
[ -n "$best" ] || exit 1
printf '%s\n' "$best"
