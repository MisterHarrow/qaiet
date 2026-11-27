"""Desks: the site covers AI, energy, biotech, space and food, each as its own copy of the page."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from typer.testing import CliRunner

from quiet_ai.cli import app
from quiet_ai.config import ClusterSettings
from quiet_ai.pipeline import archive, cluster, embed, sentiment
from quiet_ai.site import build
from quiet_ai.store.db import MIGRATIONS, Store, iso
from quiet_ai.store.models import Item
from tests.conftest import NOW

EMB = embed.HashEmbedder()
CFG = ClusterSettings(join_threshold=0.3, strict_join_threshold=0.9, merge_threshold=0.5, confident_threshold=0.3)


def add(store, items, desk):
    for it in items:
        it.published_at = NOW
    store.upsert_items(items, NOW)
    with store.conn:
        store.conn.executemany("UPDATE items SET relevant = 1, relevance_by = 'test', desk = ? WHERE id = ?", [(desk, it.id) for it in items])
    embed.embed_pending(store, EMB, iso(NOW - timedelta(days=3)), 300, NOW)


def news(i, title, source="nyt"):
    return Item(id=f"n{i}", source=source, kind="news", url=f"https://news.example/{i}", title=title, fetched_at=NOW)


def test_items_join_only_stories_of_their_own_desk():
    st = Store(":memory:")
    add(st, [news(1, "Nvidia data center power deal with utility"), news(2, "Nvidia data center power deal signed", "bbc")], "ai")
    add(st, [news(3, "Utility signs data center power deal with Nvidia", "dw")], "energy")
    cluster.run(st, EMB.name, CFG, NOW)
    rows = {r["id"]: (r["story_id"], r["desk"]) for r in st.conn.execute("SELECT i.id, i.story_id, s.desk FROM items i JOIN stories s ON s.id = i.story_id")}
    assert rows["n1"][0] == rows["n2"][0] and rows["n1"][1] == "ai"
    assert rows["n3"][0] != rows["n1"][0] and rows["n3"][1] == "energy"


def test_migration_6_moves_everything_so_far_to_the_ai_desk():
    st = Store(":memory:")  # a new database runs every migration, 6 included
    cols = {r["name"] for r in st.conn.execute("PRAGMA table_info(editions)")}
    assert {"desk", "date"} <= cols and any("desk = 'ai' WHERE relevant = 1" in m for m in MIGRATIONS[6])
    assert st.conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "6"
    st.conn.execute("INSERT INTO editions (date, data, updated_at) VALUES ('2026-11-24', '{}', 'x')")  # desk defaults to ai
    assert st.conn.execute("SELECT desk FROM editions").fetchone()[0] == "ai"


def test_sentiment_is_kept_per_desk(settings):
    st = Store(":memory:")
    now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    for desk, stance in (("ai", -1), ("energy", 2)):
        for n, src in enumerate(("a", "b", "c")):
            iid = f"{desk}{n}"
            st.upsert_items([Item(id=iid, source=src, kind="news", url=f"https://e.com/{iid}", title=f"{desk} {n}", fetched_at=now, published_at=now)], now)
            st.conn.execute("UPDATE items SET relevant = 1, desk = ? WHERE id = ?", (desk, iid))
            st.conn.execute("INSERT INTO item_labels(item_id, task, prompt_version, model, track, frame, stance, confidence, data, created_at) "
                            "VALUES (?, 'news', 'v', 'm', 'economic', 'neutral', ?, 'high', '{}', 'x')", (iid, stance))
    st.conn.commit()
    for desk in ("ai", "energy"):
        sentiment.compute(st, settings, now, desk=desk)
    assert sentiment.history(st, desk="ai")["all"][-1]["value"] == -1
    assert sentiment.history(st, desk="energy")["all"][-1]["value"] == 2


def test_desk_editions_freeze_into_their_own_folder(tmp_path):
    st = Store(":memory:")
    day = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    archive.save_day_edition(st, {"weather": "ai"}, day, "Europe/Stockholm")
    archive.save_day_edition(st, {"weather": "energy"}, day, "Europe/Stockholm", "energy")
    written = archive.freeze(st, tmp_path, day + timedelta(days=1), "Europe/Stockholm")
    assert written == ["2026-11-24", "energy/2026-11-24"]
    assert json.loads((tmp_path / "energy" / "2026-11-24.json").read_text())["weather"] == "energy"
    assert [e["weather"] for e in archive.load_frozen(tmp_path)] == ["ai"]  # AI's folder holds only AI's days


def test_desk_row_links_from_any_depth():
    desks = [{"key": "ai", "label": "AI", "prefix": "", "value": -0.2}, {"key": "energy", "label": "Energy", "prefix": "energy/", "value": None}]
    assert [(d["href"], d["active"]) for d in build.desk_row("", desks, "ai")] == [("./", True), ("energy/", False)]
    assert [d["href"] for d in build.desk_row("../../", desks, "energy")] == ["../../", "../../energy/"]
    assert build.desk_row("", desks[:1], "ai") == []  # one desk: no row


def test_build_renders_every_desk_with_its_own_pages(tmp_path):
    res = CliRunner().invoke(app, ["build", "--dry-run", "--out", str(tmp_path)])
    assert res.exit_code == 0, res.output
    front = (tmp_path / "index.html").read_text()
    assert '<nav class="desks" aria-label="Desks">' in front and '<a href="energy/">' in front and "Rising" in front
    energy = (tmp_path / "energy" / "index.html").read_text()
    assert "<title>Qaiet Times · Energy · 24 hours" in energy and 'href="../static/style.css"' in energy
    assert '<a href="../energy/" aria-current="page"><span class="desk-name">Energy' in energy
    assert 'href="../energy/sentiment/">Index</a>' in energy and 'href="../about/">About</a>' in energy
    assert "Rising" not in energy and "The gap" not in energy  # builder listings belong to AI
    for page in ("energy/week", "energy/sentiment", "energy/narratives", "energy/archive", "food/year", "space/sentiment"):
        assert (tmp_path / page / "index.html").exists(), page
    index = (tmp_path / "biotech" / "sentiment" / "index.html").read_text()
    assert "Biotech &amp; health tech sentiment index" in index and "medical technology" in index
