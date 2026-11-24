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
