#!/usr/bin/env bash
# Voice today's spoken bulletin on this Mac with Ming-3.0-tts, then put it on the site.
#
# The GitHub publish (06:30 Stockholm) writes the day's script with Sonnet and keeps it as an `audio` release
# asset; Ming runs only on Apple Silicon, so this Mac voices it:
#   1. skip if today's MP3 is already in the release, or if the script isn't there yet (the publish hasn't run);
#   2. download the script and voice it (qa bulletin --reuse-script: no model call, free, offline);
#   3. upload the MP3 and its details to the release;
#   4. start the workflow's deploy run, which restores the audio, rebuilds the site with the player and deploys it.
# launchd runs it several times each morning (install.sh); every run after the first one that succeeds just skips.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export HF_HUB_OFFLINE=1   # the weights come from the local cache, never the network

day=$(TZ=Europe/Stockholm date +%F)
echo "$(date '+%F %T') bulletin for $day"
assets=$(gh release view audio --json assets --jq '.assets[].name' 2>/dev/null || true)
if grep -qx "bulletin-$day.mp3" <<<"$assets"; then echo "already voiced"; exit 0; fi
if ! grep -qx "bulletin-$day.txt" <<<"$assets"; then echo "no script yet: today's publish hasn't run"; exit 0; fi

mkdir -p data/audio
gh release download audio --pattern "bulletin-$day.txt" --dir data/audio --clobber
uv run --extra voice qa bulletin --date "$day" --reuse-script --force
gh release upload audio "data/audio/bulletin-$day.mp3" "data/audio/bulletin-$day.json" --clobber
gh workflow run run.yml -f mode=deploy
echo "uploaded; deploy started"
