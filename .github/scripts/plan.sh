#!/usr/bin/env bash
# Decide what this workflow run does: publish | collect | skip.
#   publish: everything (collect, labels, summaries, page, daily edition, deploy) at 06:30 Stockholm
#   collect: fetch sources only, every 2 hours, no model calls
# GitHub cron runs in UTC and can't follow daylight saving, so the publish cron fires at both
# 04:30 and 05:30 UTC and only the one that is 06:xx in Stockholm goes ahead.
set -euo pipefail
event="${EVENT:?}"
schedule="${SCHEDULE:-}"
input_mode="${INPUT_MODE:-publish}"
publish_cron="${PUBLISH_CRON:?}"
local_hour="${LOCAL_HOUR:-$(TZ=Europe/Stockholm date +%H)}"

if [ "$event" = "workflow_dispatch" ]; then
  mode="$input_mode"
elif [ "$schedule" = "$publish_cron" ]; then
  if [ "$local_hour" = "06" ]; then mode=publish; else mode=skip; fi
else
  mode=collect
fi
echo "$mode"
