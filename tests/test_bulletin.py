"""The spoken bulletin: script, speech requests, costs and the player. No network, no model calls."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from quiet_ai.config import BulletinSettings, LLMSettings, ModelPrice, Settings
from quiet_ai.llm.client import LLM
from quiet_ai.pipeline import archive, bulletin
from quiet_ai.site import build
from quiet_ai.store.db import Store
from tests.conftest import NOW
from tests.test_site import edition as site_edition

TONE = Path(__file__).parent / "fixtures" / "audio" / "tone.mp3"  # 0.4 s, made locally with ffmpeg
DAY = archive.local_date(NOW, "Europe/Stockholm")
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def day_edition() -> dict:
    return {
        "generated_at": NOW.isoformat(),
        "weather": "Market-heavy day; builders shipped agent tools.",
        "stories": [
            {"rank": 1, "headline": "Nvidia reinstates its chief executive", "outlets": 41, "countries": 10, "track": "political",
             "stance_summary": "mostly neutral", "builders_line": "HN 690 points",
             "summary": {"headline": "Nvidia's board reinstated Jensen Huang.", "frames": [
                 {"frame": "Treat the return as a governance failure", "outlets": ["Financial Times", "Der Spiegel"]}],
                 "builders": "Hacker News discussed it at length."}},
            {"rank": 2, "headline": "Tidal bans AI music", "outlets": 5, "countries": 2, "track": "economic",
             "stance_summary": "leans critical", "summary": {"headline": "Tidal bans fully AI-generated music.",
                                                             "coverage": "Most report it plainly.", "builders": None}},
        ],
        "rising": [{"title": "stablyai/orca", "what": "An app for running coding agents.", "signal": "+1,827 stars/day",
                    "url": "https://github.com/stablyai/orca"}],
        "gap": {"builders_not_press": [{"headline": "Agents work for their makers", "builders_line": "HN 961 points",
                                        "link": "https://news.ycombinator.com/item?id=1"}],
                "press_not_builders": [{"headline": "Riemann proof", "outlets": 6}]},
    }


class FakeAnthropic:
    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(parse=self._parse)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kw):
        self.calls.append(kw)
        data = {"sections": [{"paragraphs": ["The day's biggest story.  Nvidia's board reinstated Jensen Huang.", "Forty-one outlets covered it."]},
                             {"paragraphs": ["Tidal has banned music made entirely by AI.", "  "]},
                             {"paragraphs": []}]}
        usage = SimpleNamespace(input_tokens=2000, output_tokens=1500, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=kw["output_format"].model_validate(data), usage=usage, stop_reason="end_turn", model=kw["model"])


class FakeElevenLabs:
    """Records each request; answers with a short tone. With `refuse_context`, a 400 to any request that sends context."""

    def __init__(self, refuse_context: bool = False, fail_at: int | None = None):
        self.requests: list[httpx.Request] = []
        self.refuse_context = refuse_context
        self.fail_at = fail_at

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = json.loads(request.content)
        if self.refuse_context and "previous_text" in body:
            return httpx.Response(400, json={"detail": {"status": "invalid_parameter"}})
        if self.fail_at is not None and len(self.requests) > self.fail_at:
            return httpx.Response(401, json={"detail": {"status": "invalid_api_key", "message": "key sk_123 is wrong"}})
        return httpx.Response(200, content=TONE.read_bytes(), headers={"content-type": "audio/mpeg"})

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


def setup(tmp_path, fake: FakeElevenLabs, edition: dict | None = None, key: str = "test-key"):
    store = Store(":memory:")
    if edition is not False:
        archive.save_day_edition(store, edition or day_edition(), NOW, "Europe/Stockholm")
    settings = Settings(llm=LLMSettings(prices={"claude-sonnet-5-5": ModelPrice(input=2, output=10)}))
    llm = LLM(settings.llm, store, "run", client=FakeAnthropic())
    tts = bulletin.ElevenLabs(settings.bulletin, key=key, transport=httpx.MockTransport(fake))
    return store, settings, llm, tts


def fake_join(parts, out, bitrate="96k"):
    out.write_bytes(b"".join(p.read_bytes() for p, _ in parts))
    fake_join.pauses = [pause for _, pause in parts]
    return 0.4 * len(parts) + sum(fake_join.pauses)


def test_spoken_dates():
    assert bulletin.intro(date(2026, 11, 25)) == (
        "This is Qaiet Times, the calm daily overview of AI. It is Wednesday, the twenty-fifth of November, twenty twenty-six.")
    assert [bulletin.ordinal_words(n) for n in (1, 2, 3, 11, 12, 20, 22, 30, 31)] == [
        "first", "second", "third", "eleventh", "twelfth", "twentieth", "twenty-second", "thirtieth", "thirty-first"]
    assert [bulletin.year_words(y) for y in (2000, 2007, 2010, 2026)] == [
        "two thousand", "two thousand and seven", "twenty ten", "twenty twenty-six"]
    assert bulletin.outro(date(2026, 12, 1)).startswith("That was Qaiet Times for Tuesday, the first of December.")


def test_material_has_stories_framings_rising_and_gap_but_no_links():
    text = bulletin.material(day_edition())
    for part in ("Nvidia's board reinstated Jensen Huang.", "41 outlets in 10 countries", "mostly neutral",
                 "Treat the return as a governance failure (Financial Times, Der Spiegel)", "Hacker News discussed it",
                 "How outlets framed it: Most report it plainly.", "stablyai/orca: An app for running coding agents.",
                 "Builders discussed, no press: Agents work for their makers", "Press covered (6 outlets)"):
        assert part in text, part
    assert "://" not in text


def test_script_text_round_trips():
    sections = [["Hello.", "Two  words."], ["Next section."]]
    text = bulletin.script_text(sections)
    assert text == "Hello.\n\nTwo  words.\n\n---\n\nNext section.\n"
    assert bulletin.parse_script(text) == [["Hello.", "Two words."], ["Next section."]]


def test_make_writes_voices_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(bulletin, "join", fake_join)
    fake = FakeElevenLabs()
    store, settings, llm, tts = setup(tmp_path, fake)
    res = bulletin.make(store, settings, DAY, tmp_path, llm, tts, NOW, "run")

    # The script: greeting, the model's sections (blank paragraphs and empty sections dropped), sign-off.
    script = (tmp_path / f"bulletin-{DAY}.txt").read_text()
    sections = bulletin.parse_script(script)
    assert sections[0][0].startswith("This is Qaiet Times") and sections[-1][0].startswith("That was Qaiet Times")
    assert sections[1:-1] == [["The day's biggest story. Nvidia's board reinstated Jensen Huang.", "Forty-one outlets covered it."],
                              ["Tidal has banned music made entirely by AI."]]
    assert llm.client.calls[0]["model"] == "claude-sonnet-5-5"
    assert "Story 1:" in llm.client.calls[0]["messages"][0]["content"]

    # Speech: one request per paragraph, same voice, model and seed, neighbours as context, key only in the header.
    bodies = fake.bodies()
    assert len(bodies) == res.paragraphs == 5
    assert all(r.url.path == "/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb" and r.headers["xi-api-key"] == "test-key" for r in fake.requests)
    assert {(b["model_id"], b["seed"]) for b in bodies} == {("eleven_v4", 1201)}
    assert bodies[0]["previous_text"] == "" and bodies[0]["next_text"] == bodies[1]["text"]
    assert bodies[-1]["previous_text"] == bodies[-2]["text"] and bodies[-1]["next_text"] == ""
    # Pauses: longer after the last paragraph of a section, none after the sign-off.
    assert fake_join.pauses == [1.5, 0.7, 1.5, 1.5, 0.0]

    # Costs: the speech is logged per paragraph at the list price, outside the LLM cap.
    chars = sum(len(b["text"]) for b in bodies)
    assert res.chars == chars and res.tts_cost_usd == pytest.approx(chars * 80 / 1e6)
    assert bulletin.tts_month_spend(store, NOW) == pytest.approx(res.tts_cost_usd)
    assert llm.month_spend(NOW) == pytest.approx(res.script_cost_usd) and res.script_cost_usd > 0
    meta = json.loads((tmp_path / f"bulletin-{DAY}.json").read_text())
    assert meta["voice"] == "George" and meta["paragraphs"] == 5 and meta["tts_model"] == "eleven_v4"


def test_reused_script_makes_no_model_call(tmp_path, monkeypatch):
    monkeypatch.setattr(bulletin, "join", fake_join)
    fake = FakeElevenLabs()
    store, settings, llm, tts = setup(tmp_path, fake)
    res = bulletin.make(store, settings, DAY, tmp_path, llm, tts, NOW, script="One.\n\n---\n\nTwo.\n")
    assert llm.client.calls == [] and res.script_cost_usd == 0 and [b["text"] for b in fake.bodies()] == ["One.", "Two."]


def test_context_refused_once_then_left_out(tmp_path, monkeypatch):
    monkeypatch.setattr(bulletin, "join", fake_join)
    fake = FakeElevenLabs(refuse_context=True)
    store, settings, llm, tts = setup(tmp_path, fake)
    bulletin.make(store, settings, DAY, tmp_path, llm, tts, NOW)
    bodies = fake.bodies()
    assert "previous_text" in bodies[0] and all("previous_text" not in b for b in bodies[1:])
    assert len(bodies) == 6  # one refused, then five plain


def test_errors_never_echo_the_response(tmp_path, monkeypatch):
    monkeypatch.setattr(bulletin, "join", fake_join)
    store, settings, llm, tts = setup(tmp_path, FakeElevenLabs(fail_at=1))
    with pytest.raises(bulletin.BulletinUnavailable) as err:
        bulletin.make(store, settings, DAY, tmp_path, llm, tts, NOW)
    assert str(err.value) == "ElevenLabs answered HTTP 401 (invalid_api_key)"  # the code, never the message
    assert not (tmp_path / f"bulletin-{DAY}.mp3").exists()
    errors = store.conn.execute("SELECT error, cost_usd FROM llm_calls WHERE task = 'tts_bulletin' AND error IS NOT NULL").fetchall()
    assert [(r["error"], r["cost_usd"]) for r in errors] == [("ElevenLabs answered HTTP 401 (invalid_api_key)", 0.0)]


def test_refuses_without_edition_key_or_budget(tmp_path):
    fake = FakeElevenLabs()
    store, settings, llm, tts = setup(tmp_path, fake, edition=False)
    with pytest.raises(bulletin.BulletinUnavailable, match="no edition saved"):
        bulletin.make(store, settings, DAY, tmp_path, llm, tts, NOW)

    store, settings, llm, tts = setup(tmp_path, fake, key="")
    with pytest.raises(bulletin.BulletinUnavailable, match="ELEVENLABS_API_KEY"):
        bulletin.make(store, settings, DAY, tmp_path, llm, tts, NOW)

    store, settings, llm, tts = setup(tmp_path, fake)
    settings.bulletin = BulletinSettings(monthly_budget_usd=0.01)
    bulletin.log_tts(store, "earlier", settings.bulletin, 100, NOW)  # $0.008 spent
    with pytest.raises(bulletin.BulletinUnavailable, match="monthly budget"):
        bulletin.make(store, settings, DAY, tmp_path, llm, tts, NOW)
    assert fake.requests == []


@needs_ffmpeg
def test_join_pads_and_encodes(tmp_path):
    out = tmp_path / "b.mp3"
    seconds = bulletin.join([(TONE, 0.5), (TONE, 0.0)], out)
    assert out.read_bytes()[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3") and 1.0 < seconds < 1.6


def test_player_on_the_page_only_when_the_audio_exists(tmp_path):
    audio = tmp_path / "audio-in"
    audio.mkdir()
    def day_view():
        return {**site_edition(), "period": {"key": "day", "label": "24 hours", "hours": 24}}

    day = archive.local_date(datetime.fromisoformat(day_view()["generated_at"]), "Europe/Stockholm")
    build.render_all([day_view()], tmp_path / "site", audio_dir=audio)
    assert 'class="listen"' not in (tmp_path / "site" / "index.html").read_text()

    shutil.copy(TONE, audio / f"bulletin-{day}.mp3")
    (audio / f"bulletin-{day}.txt").write_text("Hello.\n")
    (audio / f"bulletin-{day}.json").write_text(json.dumps({"duration_s": 554.1, "voice": "George"}))
    build.render_all([day_view(), {**site_edition(), "period": {"key": "week", "label": "7 days", "hours": 168}}],
                     tmp_path / "site", audio_dir=audio)
    html = (tmp_path / "site" / "index.html").read_text()
    assert f'<audio controls preload="none" src="audio/bulletin-{day}.mp3"></audio>' in html
    assert f'href="audio/bulletin-{day}.txt">transcript</a>' in html and "9 min, read by a synthetic voice" in html
    assert '<div class="speed" role="group" aria-label="Playback speed" hidden>' in html
    assert (tmp_path / "site" / "audio" / f"bulletin-{day}.mp3").exists()
    assert 'class="listen"' not in (tmp_path / "site" / "week" / "index.html").read_text()  # the 24-hour view only

    # An archive page links two folders up.
    frozen = {**day_view(), "frozen": {"date": day, "at": "x"}}
    build.render_archive([frozen], tmp_path / "site", audio_dir=audio)
    assert f'src="../../audio/bulletin-{day}.mp3"' in (tmp_path / "site" / "archive" / day / "index.html").read_text()


def test_publish_helper_never_raises_and_voices_once(tmp_path, monkeypatch):
    from quiet_ai import cli

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    store, settings, llm, _ = setup(tmp_path, FakeElevenLabs())
    settings.bulletin.audio_dir = str(tmp_path)  # absolute: ROOT / it is tmp_path
    assert cli._spoken(store, settings, NOW, llm, "run") == "[yellow]not made: no ELEVENLABS_API_KEY[/]"
    assert llm.client.calls == []  # stopped before the script was written

    (tmp_path / f"bulletin-{DAY}.mp3").write_bytes(b"x")
    assert cli._spoken(store, settings, NOW, llm, "run") == f"{DAY} already voiced"


def test_a_later_try_reuses_the_days_script(tmp_path, monkeypatch):
    from quiet_ai import cli

    monkeypatch.setattr(bulletin, "join", fake_join)
    fake = FakeElevenLabs()
    store, settings, llm, tts = setup(tmp_path, fake)
    settings.bulletin.audio_dir = str(tmp_path)
    (tmp_path / f"bulletin-{DAY}.txt").write_text("One.\n\n---\n\nTwo.\n")
    monkeypatch.setattr(bulletin, "ElevenLabs", lambda s: tts)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    note = cli._spoken(store, settings, NOW, llm, "run")
    assert "2 paragraphs" in note and llm.client.calls == [] and [b["text"] for b in fake.bodies()] == ["One.", "Two."]
