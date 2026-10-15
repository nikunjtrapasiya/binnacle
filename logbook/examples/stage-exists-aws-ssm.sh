#!/bin/sh
# Exit 0 stage up, 1 definitely gone, 2 unknown. "Gone" must be a
# positive finding: AWS CLI v2 exits 254 and v1 exits 255 for every
# client error, so the parameter-missing case is read off the message.
out=$(aws ssm get-parameter \
        --region REGION \
        --profile PROFILE \
        --name "/myorg/$LOGBOOK_STAGE/base-url" 2>&1) && exit 0
case "$out" in
  *ParameterNotFound*) exit 1 ;;
  *) echo "$out" >&2; exit 2 ;;
esac
