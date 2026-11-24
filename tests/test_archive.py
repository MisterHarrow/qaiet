from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from quiet_ai.pipeline import archive
from quiet_ai.site import build
from quiet_ai.store.db import Store
from quiet_ai.store.models import Item, Metrics
from tests.test_site import edition

TZ = "Europe/Stockholm"


def test_local_date_rolls_over_at_stockholm_midnight():
    assert archive.local_date(datetime(2026, 11, 24, 22, 59, tzinfo=timezone.utc), TZ) == "2026-11-24"
    assert archive.local_date(datetime(2026, 11, 24, 23, 1, tzinfo=timezone.utc), TZ) == "2026-11-25"  # CET = UTC+1


def test_freeze_writes_finished_days_once(tmp_path):
    st = Store(":memory:")
    day1 = datetime(2026, 11, 24, 20, tzinfo=timezone.utc)
    archive.save_day_edition(st, edition(weather="first"), day1, TZ)
    archive.save_day_edition(st, edition(weather="last of the day"), day1 + timedelta(hours=2), TZ)  # 23:00 local, same date
    assert archive.freeze(st, tmp_path, day1 + timedelta(hours=2), TZ) == []  # the day isn't over yet

    next_morning = datetime(2026, 11, 25, 6, tzinfo=timezone.utc)
    archive.save_day_edition(st, edition(weather="new day"), next_morning, TZ)
    assert archive.freeze(st, tmp_path, next_morning, TZ) == ["2026-11-24"]
    frozen = json.loads((tmp_path / "2026-11-24.json").read_text())
    assert frozen["weather"] == "last of the day" and frozen["frozen"]["date"] == "2026-11-24"
    assert archive.freeze(st, tmp_path, next_morning, TZ) == []  # never rewritten
    assert [e["frozen"]["date"] for e in archive.load_frozen(tmp_path)] == ["2026-11-24"]


def test_archive_pages(tmp_path):
    e = edition(weather="Quiet day.")
    e["frozen"] = {"date": "2026-11-24", "at": "2026-11-25T00:17:00+00:00"}
    index = build.render_archive([e], tmp_path)
    html = index.read_text()
    assert '<a href="2026-11-24/">Tuesday 24 November 2026</a>' in html and "Quiet day." in html
    day = (tmp_path / "archive" / "2026-11-24" / "index.html").read_text()
    assert "Edition of Tuesday 24 November 2026" in day and "The edition published on Tuesday 24 November 2026" in day
    assert 'href="../../static/style.css"' in day and 'class="periods"' not in day
    empty = build.render_archive([], tmp_path / "empty").read_text()
    assert "Editions appear here the morning after" in empty


def test_prune_rules():
    st = Store(":memory:")
    now = datetime(2026, 12, 30, tzinfo=timezone.utc)
    old = now - timedelta(days=20)
    items = [
        Item(id="irrelevant-old", source="nyt", kind="news", url="https://e.com/1", title="Sport", fetched_at=old),
        Item(id="relevant-old", source="nyt", kind="news", url="https://e.com/2", title="AI", fetched_at=old),
        Item(id="repo", source="github", kind="repo", url="https://github.com/o/r", title="o/r", metrics=Metrics(stars=1), fetched_at=old),
    ]
    st.upsert_items(items, old)
    for h in range(0, 24, 2):  # 12 snapshots on one old day
        st.upsert_items([items[2].model_copy(update={"metrics": Metrics(stars=10 + h)})], old + timedelta(hours=h))
    with st.conn:
        st.conn.execute("UPDATE items SET relevant = 0 WHERE id = 'irrelevant-old'")
        st.conn.execute("UPDATE items SET relevant = 1 WHERE id != 'irrelevant-old'")
    counts = archive.prune(st, now, vacuum=True)
    ids = {r[0] for r in st.conn.execute("SELECT id FROM items")}
    assert ids == {"relevant-old", "repo"} and counts["irrelevant_items"] == 1
    snaps = st.conn.execute("SELECT metrics FROM metric_snapshots WHERE item_id = 'repo'").fetchall()
    assert len(snaps) == 1 and json.loads(snaps[0][0])["stars"] == 32  # the day's last snapshot survives
