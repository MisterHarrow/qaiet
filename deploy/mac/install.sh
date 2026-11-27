#!/usr/bin/env bash
# Install (or remove, with --remove) the launchd job that runs bulletin.sh each morning on this Mac.
# It runs at 07:10, 07:40, 08:10, 08:40, 09:40 and 11:10 local time; a run missed while the Mac sleeps happens
# when it wakes. Logs: ~/Library/Logs/qaiet-bulletin.log.
set -euo pipefail
label=com.qaiet.bulletin
plist="$HOME/Library/LaunchAgents/$label.plist"
launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
if [ "${1:-}" = "--remove" ]; then rm -f "$plist"; echo "removed $label"; exit 0; fi

script="$(cd "$(dirname "$0")" && pwd)/bulletin.sh"
times=""
for t in 7:10 7:40 8:10 8:40 9:40 11:10; do
  times+="<dict><key>Hour</key><integer>${t%%:*}</integer><key>Minute</key><integer>${t##*:}</integer></dict>"
done
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$script</string></array>
  <key>StartCalendarInterval</key><array>$times</array>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/qaiet-bulletin.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/qaiet-bulletin.log</string>
</dict></plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "installed $label: runs $script each morning"
