#!/usr/bin/env bash
# Decide what this workflow run does: publish | collect | skip (manual runs: the chosen mode, also deploy).
#   publish: collect, labels, summaries, the page, the daily edition, deploy
#   collect: fetch sources only, no model calls
#
# GitHub drops scheduled runs under load (from 24 to 25 Nov 2026 only 1 of 11 fired, and neither
# morning publish), so publishing can't hang on one cron. Every scheduled run checks the live
# site: once it is past publish time in Stockholm and the live front page is older than today's
# publish time, it publishes. The morning cron fires every 20 minutes so a dropped run is retried,
# and the 2-hourly collect run is the backstop. A published edition makes later runs skip.
set -euo pipefail
event="${EVENT:?}"
schedule="${SCHEDULE:-}"
input_mode="${INPUT_MODE:-publish}"
collect_cron="${COLLECT_CRON:?}"
site_url="${SITE_URL:-}"
settings="$(dirname "$0")/../../config/settings.yaml"
publish_at="${PUBLISH_AT:-$(sed -n 's/^ *publish_at: *"\{0,1\}\([0-9][0-9]:[0-9][0-9]\).*/\1/p' "$settings" 2>/dev/null | head -1)}"
publish_at="${publish_at:-06:30}"
today="${LOCAL_DATE:-$(TZ=Europe/Stockholm date +%F)}"
now="${LOCAL_TIME:-$(TZ=Europe/Stockholm date +%H:%M)}"

# When the live front page was generated, as Stockholm "YYYY-MM-DDTHH:MM"; empty if unknown.
live_at() {
  if [ -n "${LIVE_AT+x}" ]; then echo "$LIVE_AT"; return; fi
  [ -n "$site_url" ] || return 0
  # The query string skips the Pages CDN cache (max-age 600) right after a deploy.
  curl -fsS --max-time 20 "$site_url/edition.json?nocache=$(date +%s)" 2>/dev/null | python3 -c '
import json, sys
from datetime import datetime
from zoneinfo import ZoneInfo
try:
    at = datetime.fromisoformat(json.load(sys.stdin)["generated_at"])
    print(at.astimezone(ZoneInfo("Europe/Stockholm")).strftime("%Y-%m-%dT%H:%M"))
except Exception:
    pass
' || true
}

if [ "$event" = "workflow_dispatch" ]; then
  mode="$input_mode"
else
  mode=skip
  if [ "$schedule" = "$collect_cron" ]; then mode=collect; fi
  if [[ ! "$now" < "$publish_at" ]]; then
    due="${today}T${publish_at}"
    live="$(live_at)"
    if [ -z "$live" ]; then
      echo "could not read the live edition; a scheduled run won't publish blind" >&2
    elif [[ "$live" < "$due" ]]; then
      echo "live front page is from $live, today's is due $due: publishing" >&2
      mode=publish
    fi
  fi
fi
echo "$mode"
