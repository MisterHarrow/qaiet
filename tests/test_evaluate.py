from __future__ import annotations

from quiet_ai import evaluate
from quiet_ai.config import load_sources
from quiet_ai.store.db import Store
from tests.test_gap_sentiment import labeled


def store_with_labels():
    st = Store(":memory:")
    rows = [("nyt", "political", -1), ("nyt", "political", -2), ("ft", "economic", 1), ("ft", "economic", 0),
            ("verge", "technical", 2), ("verge", "technical", 0), ("atlantic", "technical", -1), ("svd", "economic", -1)]
    for i, (src, track, stance) in enumerate(rows):
        labeled(st, i, src, track, stance)
    with st.conn:
        st.conn.execute("UPDATE item_labels SET frame = 'grounded' WHERE track = 'technical'")
    return st


def test_sample_is_blind_stratified_and_skips_opt_outs(tmp_path):
    st, sources = store_with_labels(), load_sources()
    items = evaluate.sample(st, sources, 50)
    ids = {g["id"] for g in items}
    assert "n6" not in ids  # The Atlantic opts out of AI processing
    assert all(g["track"] is None and g["stance"] is None for g in items)  # blind
    tracks = {st.conn.execute("SELECT track FROM item_labels WHERE item_id = ?", (g["id"],)).fetchone()[0] for g in items}
    assert tracks == {"political", "economic", "technical"}
    path = tmp_path / "gold.yaml"
    evaluate.write_gold(items, path)
    assert path.read_text().startswith("# Hand labels") and evaluate.load_gold(path) == []  # nothing filled in yet


def test_score_agreement():
    st = store_with_labels()
    gold = [
        {"id": "n0", "track": "political", "frame": None, "stance": -1},   # exact
        {"id": "n2", "track": "economic", "stance": 0},                     # stance off by one
        {"id": "n4", "track": "technical", "frame": "hype", "stance": 0},   # frame differs, stance off by two
        {"id": "n5", "track": "economic", "stance": None},                  # track differs, no stance
        {"id": "gone", "track": "technical", "stance": 0},                  # not in the database
    ]
    res = evaluate.score(st, gold)
    assert res["n"] == 4 and res["missing"] == 1
    assert res["track"] == {"agree": 75, "n": 4} and res["frame"] == {"agree": 0, "n": 1}
    assert res["stance_exact"] == {"agree": 33, "n": 3} and res["stance_within_1"] == {"agree": 67, "n": 3}
    assert res["stance_mae"] == 1.0
    assert evaluate.score(st, []) == {"n": 0}


def test_audit_by_group():
    st, sources = store_with_labels(), load_sources()
    with st.conn:
        st.conn.execute("UPDATE item_labels SET confidence = 'low' WHERE item_id = 'n7'")
    rows = {r["key"]: r for r in evaluate.audit(st, sources, by="group")}
    groups = {f.id: f.group for f in sources.feeds}
    nyt = rows[groups["nyt"]]
    assert nyt["n"] >= 2 and nyt["critical"] is not None
    svd = rows[groups["svd"]]
    assert svd["unclear"] > 0
    means = [r["mean"] for r in evaluate.audit(st, sources, by="group") if r["mean"] is not None]
    assert means == sorted(means)


def test_score_reports_signed_stance_bias():
    st = store_with_labels()
    gold = [{"id": "n0", "track": "political", "stance": -1}, {"id": "n2", "track": "economic", "stance": 0},
            {"id": "n4", "track": "technical", "stance": 0}]
    res = evaluate.score(st, gold, load_sources())  # site minus reference: 0, +1, +2
    assert res["stance_bias"] == 1.0
    groups = {f.id: f.group for f in load_sources().feeds}
    assert res["stance_bias_by_group"][groups["verge"]] == {"bias": 2.0, "n": 1}


def test_crosscheck_uses_the_site_prompt_and_input(tmp_path, settings):
    from quiet_ai.config import LLMSettings, ModelPrice, load_accounts
    from quiet_ai.llm.client import LLM, load_prompt
    from quiet_ai.site import build
    from quiet_ai.site.about import about_context
    from tests.conftest import NOW
    from tests.test_analysis import FakeAnthropic

    st, sources = store_with_labels(), load_sources()
    fake = FakeAnthropic()
    llm = LLM(LLMSettings(prices={"claude-opus-5-5": ModelPrice(input=4, output=20)}), st, "run", client=fake)
    sample_items = [{"id": f"n{i}"} for i in (0, 2, 4, 5)] + [{"id": "gone"}]
    items = evaluate.crosscheck(st, settings, llm, sample_items, "claude-opus-5-5", batch_size=3)
    assert [g["id"] for g in items] == ["n0", "n2", "n4", "n5"]
    assert all(g["track"] == "economic" and g["stance"] == 0 and g["confidence"] == "high" for g in items)
    call = fake.calls[0]
    assert len(fake.calls) == 2 and call["model"] == "claude-opus-5-5" and "thinking" not in call  # Opus 5.5 can't turn thinking off
    assert call["output_config"] == {"effort": "medium"}
    assert call["system"][0]["text"] == load_prompt(settings.analysis.news_prompt)
    assert call["messages"][0]["content"].startswith("[0] (en) headline: AI 0")

    path = tmp_path / "labels-claude-opus-5-5.yaml"
    evaluate.write_crosscheck(items, path, "claude-opus-5-5", "news_label_v3", "2026-11-24T14:00:00+00:00")
    assert evaluate.load_meta(path)["model"] == "claude-opus-5-5" and len(evaluate.load_gold(path)) == 4
    assert evaluate.model_name("claude-opus-5-5") == "Claude Opus 5.5"

    ctx = about_context(st, settings, sources, load_accounts(), NOW, gold=tmp_path / "none.yaml", crosscheck=path)
    html = build.render_about(ctx, tmp_path / "site").read_text()
    assert "Claude Opus 5.5 labeled the same 4 articles" in html and "being labeled by hand" in html
    assert "It agrees with the labels on this site on the angle 25% of the time" in html
