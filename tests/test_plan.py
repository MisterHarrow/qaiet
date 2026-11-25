"""The workflow's run planner (.github/scripts/plan.sh): publish once a morning, even when GitHub
drops the scheduled run that was meant to do it."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "plan.sh"
COLLECT, MORNING = "17 */2 * * *", "10,30,50 4-9 * * *"


def plan(event="schedule", schedule=MORNING, time="06:30", live="2026-11-24T14:35", **extra) -> str:
    env = {"PATH": os.environ["PATH"], "EVENT": event, "SCHEDULE": schedule, "COLLECT_CRON": COLLECT,
           "LOCAL_DATE": "2026-11-25", "LOCAL_TIME": time, "LIVE_AT": live, **extra}
    out = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=True)
    return out.stdout.strip()


@pytest.mark.parametrize("kw, expected", [
    ({"event": "workflow_dispatch", "INPUT_MODE": "collect"}, "collect"),
    ({"event": "workflow_dispatch"}, "publish"),
    ({"schedule": COLLECT, "time": "03:17"}, "collect"),            # night: just collect
    ({"time": "06:10"}, "skip"),                                     # morning, too early
    ({"time": "06:30"}, "publish"),                                  # due, yesterday's page is live
    ({"time": "06:50", "live": "2026-11-25T06:34"}, "skip"),         # already published today
    ({"schedule": COLLECT, "time": "08:17"}, "publish"),             # every morning run dropped: backstop
    ({"schedule": COLLECT, "time": "08:17", "live": "2026-11-25T06:52"}, "collect"),
    ({"time": "07:30", "live": "2026-11-25T01:10"}, "publish"),      # a manual run after midnight isn't the morning edition
    ({"time": "06:50", "live": ""}, "skip"),                         # live page unreadable: don't publish blind
    ({"schedule": COLLECT, "time": "10:17", "live": ""}, "collect"),
])
def test_plan(kw, expected):
    assert plan(**kw) == expected


def test_publish_time_comes_from_settings():
    assert plan(time="06:29") == "skip" and plan(time="06:31") == "publish"
    assert plan(time="07:59", PUBLISH_AT="08:00") == "skip"
