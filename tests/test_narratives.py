from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from quiet_ai.config import load_sources
from quiet_ai.pipeline import narratives
from quiet_ai.site import build
from quiet_ai.store.db import Store, iso
from quiet_ai.store.models import Item
from tests.test_site import edition

NOW = datetime(2026, 11, 26, 8, tzinfo=timezone.utc)   # 09:00 in Stockholm
STARTED = datetime(2026, 11, 24, 8, tzinfo=timezone.utc)  # collection began; earlier days come from the feeds' backlog
_n = 0


def story(st, sid, merged_into=None):
    with st.conn:
        st.conn.execute("INSERT INTO stories (id, created_at, updated_at, item_count, merged_into) VALUES (?, ?, ?, 0, ?)",
                        (sid, iso(STARTED), iso(STARTED), merged_into))


def article(st, sid, source, day, title, stance=None, confidence="high", kind="news"):
    """An item in story `sid`, published at noon UTC on 2026-11-<day>, seen when collection could have seen it."""
    global _n
    _n += 1
    at = datetime(2026, 11, day, 12, tzinfo=timezone.utc)
    st.upsert_items([Item(id=f"i{_n}", source=source, kind=kind, url=f"https://e.com/{_n}", title=title, published_at=at,
                          fetched_at=max(at, STARTED))], max(at, STARTED))
    with st.conn:
        st.conn.execute("UPDATE items SET relevant = 1, story_id = ? WHERE id = ?", (sid, f"i{_n}"))
        if stance is not None:
            st.conn.execute("INSERT INTO item_labels (item_id, task, prompt_version, model, track, stance, confidence, data, created_at) "
                            "VALUES (?, 'news', 'v', 'm', 'political', ?, ?, '{}', ?)", (f"i{_n}", stance, confidence, iso(at)))


def fill(st):
    story(st, "s-long")
    for src, s in (("nyt", -1), ("wsj", -1), ("cnbc", -2)):            # 21: three critical voices
        article(st, "s-long", src, 21, "Chip maker chief resigns amid smuggling inquiry", s)
    article(st, "s-long", "nyt", 22, "Chip maker board weighs the chief's return", 0)
    article(st, "s-long", "wapo", 23, "Chip maker chief returns to the board", 0)
    article(st, "s-long", "bloomberg", 24, "Chip maker chief reinstated as markets rally", 1)
    article(st, "s-long", "npr", 24, "Chip maker chief reinstated after a week of turmoil", 0)
    article(st, "s-long", "wsj", 24, "Recipe: a better sourdough", -2)   # a stray item that joined the story
    article(st, "s-long", "cnbc", 24, "Chip maker chief reinstated, shares jump", None)
    for src, s in (("nyt", 1), ("wsj", 1), ("npr", 2)):               # 25 is quiet; 26 (today) turns positive
        article(st, "s-long", src, 26, "Chip maker chief sets out plans after return", s)
    article(st, "s-long", "ainews", 25, "Digest mention", 0, kind="newsletter")  # digests don't count as coverage
    story(st, "s-short")
    for d in (24, 25, 26):
        article(st, "s-short", "nyt", d, "Three days only", 0)
    story(st, "s-digest")
    for d in (21, 22, 23, 24):
        article(st, "s-digest", "ainews", d, "Only in a digest", 0, kind="newsletter")
    story(st, "s-gone", merged_into="s-long")
    for d in (21, 22, 23, 24):
        article(st, "s-gone", "npr", d, "Merged away", 0)
    with st.conn:
        st.conn.execute("INSERT INTO editions (date, data, updated_at) VALUES (?, ?, ?)", ("2026-11-24", json.dumps({"stories": [
            {"id": "s-long", "rank": 3, "headline": "Chip maker reinstates its chief", "summary": {"coverage": "Most outlets report it plainly."}}]}), iso(STARTED)))


def test_streak_and_trend():
    assert narratives.streak(["2026-11-21", "2026-11-22", "2026-11-24", "2026-11-25", "2026-11-26"]) == 3
    assert narratives.streak(["2026-11-30", "2026-12-01"]) == 2
    assert narratives.streak([]) == 0
    assert narratives.trend(-1.0, 0.5) == "turned more positive" and narratives.trend(0.2, 0.1) == "held steady"
    assert narratives.trend(None, 1.0) is None


def test_headlines_represent_the_day():
    def it(src, title, stance):
        return {"source": src, "title": title, "title_en": None, "lang": "en", "at": src, "stance_key": stance}
    items = [it("a", "Chip maker chief reinstated", "0"), it("b", "Chip maker chief reinstated today", "0"),
             it("c", "Chip maker chief back at the helm", "0"), it("d", "Recipe: a better sourdough", "-2")]
    picked = [h["source"] for h in narratives._pick_headlines(items, 3)]
    assert "d" not in picked and len(picked) == 3  # a stray critical item doesn't win a slot for its stance


def test_detect_finds_four_days_in_a_row(settings):
    st = Store(":memory:")
    fill(st)
    found = narratives.detect(st, settings, load_sources(), NOW)
    assert [n["id"] for n in found] == ["s-long"]  # 3 days, digest-only and merged-away stories don't qualify
    n = found[0]
    assert (n["first"], n["last"], n["days"], n["covered"], n["streak"], n["ongoing"]) == ("2026-11-21", "2026-11-26", 6, 5, 4, True)
    assert n["headline"] == "Chip maker reinstates its chief"  # the latest front-page headline
    t = {d["date"]: d for d in n["timeline"]}
    assert [d["date"] for d in n["timeline"]] == [f"2026-11-{d}" for d in range(21, 27)]
    assert t["2026-11-25"]["quiet"] and t["2026-11-25"]["outlets"] == 0  # only a digest that day
    assert [t[f"2026-11-{d}"].get("partial") for d in (21, 22, 23, 24, 26)] == [True, True, True, False, False]
    assert t["2026-11-26"]["today"] and not t["2026-11-24"]["today"]
    assert t["2026-11-24"]["front"] == {"rank": 3, "headline": "Chip maker reinstates its chief", "coverage": "Most outlets report it plainly."}
    assert t["2026-11-21"]["mean"] == -1.33 and t["2026-11-26"]["mean"] == 1.33
    assert (n["first_mean"], n["last_mean"], n["trend"]) == (-1.33, 1.33, "turned more positive")
    assert t["2026-11-24"]["stance"]["unlabeled"] == 1 and t["2026-11-24"]["outlets"] == 4
    # Up to three headlines from different outlets; the stray item shares no words with the day's others and sinks.
    heads = [h["title"] for h in t["2026-11-24"]["headlines"]]
    assert len(heads) == 3 and "Recipe: a better sourdough" not in heads
    card = narratives.by_story(found)["s-long"]
    assert (card["days"], card["first"], card["last"], card["ongoing"], len(card["timeline"])) == (6, "2026-11-21", "2026-11-26", True, 6)
    compact = narratives.compact(n)
    assert set(compact["timeline"][0]) == {"date", "quiet", "outlets", "mean"} and "headlines" not in json.dumps(compact)


def test_ended_after_a_quiet_day(settings):
    st = Store(":memory:")
    fill(st)
    later = narratives.detect(st, settings, load_sources(), NOW + timedelta(days=2))
    assert later[0]["ongoing"] is False and later[0]["days"] == 6  # an ended narrative stops counting


def test_narrative_pages(tmp_path, settings):
    st = Store(":memory:")
    fill(st)
    found = narratives.detect(st, settings, load_sources(), NOW)
    index = build.render_narratives(found, tmp_path, min_days=4).read_text()
    assert "Ongoing" in index and 'href="../narratives/s-long/"' in index and "21–26 Nov" in index
    assert "stance −1.33 → +1.33, turned more positive" in index and '<svg class="nchart mini"' in index
    assert 'aria-current="page">Narratives</a>' in index
    page = (tmp_path / "narratives" / "s-long" / "index.html").read_text()
    assert page.count('class="nl-day') == 6 and "Day 6" in page and "Today, so far" in page
    assert page.count("Before collection began: partial") == 3 and "No new coverage." in page
    assert "Front page that morning" in page and "Most outlets report it plainly." in page
    assert '<svg class="nchart" viewBox' in page and "Sat 21 Nov: average −1.33, 3 outlets" in page
    assert "Recipe: a better sourdough" not in page
    for html in (index, page):  # nothing from other hosts, no images
        for tag in re.findall(r"<(?:link|script|img)[^>]*>", html):
            assert "://" not in tag.replace("http://www.w3.org/2000/svg", ""), tag
    empty = build.render_narratives([], tmp_path / "empty", min_days=4).read_text()
    assert "No story has been covered 4 days in a row yet." in empty


def test_front_page_section(tmp_path, settings):
    st = Store(":memory:")
    fill(st)
    found = narratives.detect(st, settings, load_sources(), NOW)
    html = build.render(edition(narratives={"min_days": 4, "total": 1, "items": [narratives.compact(found[0])]}), tmp_path).read_text()
    assert '<section class="narratives"' in html and 'href="narratives/s-long/"' in html and 'aria-label="6 days"' in html
    assert "covered 4 days or more in a row" in html
    assert '<section class="narratives"' not in build.render(edition(), tmp_path / "none").read_text()


def test_date_labels():
    assert build.date_range("2026-11-21", "2026-11-25") == "21–25 Nov"
    assert build.date_range("2026-11-28", "2026-12-02") == "28 Nov – 2 Dec"
    assert build.date_range("2026-12-30", "2027-01-03") == "30 Dec 2026 – 3 Jan 2027"
    assert build.day_label("2026-11-21") == "Sat 21 Nov"


def test_seal_on_card_rows_and_page(tmp_path, settings):
    st = Store(":memory:")
    fill(st)
    found = narratives.detect(st, settings, load_sources(), NOW)
    story = edition()["stories"][0] | {"narrative": narratives.by_story(found)["s-long"]}
    html = build.render(edition(stories=[story], narratives={"min_days": 4, "total": 1, "items": [narratives.compact(found[0])]}), tmp_path).read_text()
    # The card carries the seal on its corner, linking to the narrative; the lattice curve is defined once per page.
    assert '<a class="seal-link" href="narratives/s-long/" aria-label="Part of a narrative: 6 days of coverage. See how it evolved"' in html
    assert html.count('<svg class="seal-defs"') == 1 and html.count('id="seal-k12"') == 1  # 6 days: 12 petals
    assert html.count('<span class="seal"') == 2  # the card and the row
    seal = build.seal(narratives.compact(found[0]))
    assert seal.count('class="day ') == 6 and 'class="day quiet"' in seal and 'class="day s-2"' in seal and 'class="day s2"' in seal  # an arc per day, by stance
    assert seal.count('<use href="#seal-k12"') == 6 and 'class="seal-n"' in seal and ">6</text>" in seal
    page = (build.render_narratives(found, tmp_path / "n", min_days=4).parent / "s-long" / "index.html").read_text()
    assert '<span class="seal big" role="img"' in page and "QAIET TIMES ✦ NARRATIVE ✦ 06 DAYS ✦ 21–26 NOV ✦ 6 OUTLETS" in page
    assert build.seal({"timeline": []}) == "" and build.seal_defs([None, {}]) == ""
    assert build.render(edition(), tmp_path / "plain").read_text().count("seal") == 0  # no narrative, no seal
