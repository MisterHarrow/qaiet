"""The spoken bulletin: the day's edition read aloud, once a day.

1. Script: Sonnet writes it for the ear from the day's saved edition (prompt bulletin_v1); the greeting with the
   date and the sign-off are fixed text, so they never vary.
2. Speech, one paragraph at a time, by the engine in bulletin.tts_engine:
   - "ming" (the default): Ming-3.0-tts through mlx-audio, on Apple Silicon only, free, from the local Hugging Face
     cache. The GitHub publish can't run it, so it writes the script and stops; the Mac job (deploy/mac/) voices it.
   - "elevenlabs": eleven_v4 over HTTP, with the neighbouring paragraphs as context; priced per character.
3. Audio: ffmpeg joins the parts with a pause after each paragraph (longer between sections), evens out the
   loudness and encodes one MP3.

Writes <audio_dir>/bulletin-<date>.mp3, .txt (the script, which the page links as the transcript) and .json
(duration, voice, cost). The site shows a player on that day's front page and archive page when the file exists.
Speech is logged in llm_calls (task "tts_bulletin", characters in input_tokens, cost 0 for Ming) and a priced
engine is capped on its own (bulletin.monthly_budget_usd); the LLM cap leaves it out.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date as Date, datetime, timezone
from pathlib import Path

import httpx
from pydantic import BaseModel

from quiet_ai.config import BulletinSettings, Settings
from quiet_ai.llm.client import LLM, load_prompt
from quiet_ai.store.db import Store, iso

TTS_TASK = "tts_bulletin"
SECTION_BREAK = "---"


class BulletinUnavailable(Exception):
    """No edition for the day, no key, the budget is used up, or ffmpeg is missing."""


# -- the script --------------------------------------------------------------------------------------------------


class Section(BaseModel):
    paragraphs: list[str]


class Script(BaseModel):
    sections: list[Section]


_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
        "twelve": "twelfth"}


def number_words(n: int) -> str:
    """0 to 99 in words."""
    if n < 20:
        return _ONES[n] or "zero"
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def ordinal_words(n: int) -> str:
    """1 to 31: "first", "twenty-fifth", "thirtieth"."""
    words = number_words(n)
    head, _, last = words.rpartition("-")
    if last in _ORD:
        last = _ORD[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return f"{head}-{last}" if head else last


def year_words(y: int) -> str:
    """2026 -> "twenty twenty-six"; 2000 -> "two thousand"; 2007 -> "two thousand and seven"."""
    hi, lo = divmod(y, 100)
    if lo == 0:
        return f"{number_words(hi // 10)} thousand" if hi % 10 == 0 else f"{number_words(hi)} hundred"
    if lo < 10 and hi % 10 == 0:
        return f"{number_words(hi // 10)} thousand and {number_words(lo)}"
    if lo < 10:
        return f"{number_words(hi)} oh {number_words(lo)}"
    return f"{number_words(hi)} {number_words(lo)}"


def spoken_date(d: Date) -> str:
    """"Wednesday, the twenty-fifth of November, twenty twenty-six"."""
    return f"{d:%A}, the {ordinal_words(d.day)} of {d:%B}, {year_words(d.year)}"


def intro(d: Date) -> str:
    return f"This is Qaiet Times, the calm daily overview of AI. It is {spoken_date(d)}."


def outro(d: Date) -> str:
    return (f"That was Qaiet Times for {d:%A}, the {ordinal_words(d.day)} of {d:%B}. "
            "The full edition, with every outlet and headline, is on the website. Thank you for listening.")


def material(edition: dict) -> str:
    """The edition as plain text for the script writer: stories with their framings, then Rising and The gap."""
    out = []
    if edition.get("weather"):
        out.append(f"The day in one line: {edition['weather']}")
    for s in edition.get("stories") or []:
        summ = s.get("summary") or {}
        out.append(f"\nStory {s.get('rank', '')}: {summ.get('headline') or s['headline']}")
        out.append(f"Coverage: {s.get('outlets', 0)} outlets in {s.get('countries', 0)} countries; "
                   f"stance of the coverage: {s.get('stance_summary') or 'not labeled'}; angle: {s.get('track') or 'none'}.")
        frames = summ.get("frames") or []
        if frames:
            for f in frames:
                out.append(f"- Framing: {f.get('frame')} ({', '.join(f.get('outlets') or [])})")
        elif summ.get("coverage"):
            out.append(f"How outlets framed it: {summ['coverage']}")
        if summ.get("builders"):
            out.append(f"What builders said: {summ['builders']}")
        elif s.get("builders_line"):
            out.append(f"Builder activity: {s['builders_line']}")
    rising = edition.get("rising") or []
    if rising:
        out.append("\nRising builder projects (fastest first):")
        for r in rising[:6]:
            out.append(f"- {r.get('title')}: {r.get('what') or ''} ({r.get('signal') or ''})")
    gap = edition.get("gap") or {}
    quiet, loud = gap.get("builders_not_press") or [], gap.get("press_not_builders") or []
    if quiet or loud:
        out.append("\nThe gap.")
        for g in quiet:
            out.append(f"- Builders discussed, no press: {g.get('headline')} ({g.get('builders_line') or ''})")
        for g in loud:
            out.append(f"- Press covered ({g.get('outlets')} outlets), builders barely discussed: {g.get('headline')}")
    return "\n".join(out).strip()


def clean(text: str) -> str:
    return " ".join(text.split())


def write_script(llm: LLM, settings: Settings, edition: dict, day: Date) -> list[list[str]]:
    """Sections of paragraphs, greeting first and sign-off last."""
    out = llm.parse("bulletin", settings.llm.story_model, load_prompt(settings.bulletin.prompt), material(edition),
                    Script, max_tokens=6000, fallbacks=True)
    body = [[clean(p) for p in sec.paragraphs if clean(p)] for sec in out.sections]
    return [[intro(day)], *[b for b in body if b], [outro(day)]]


def script_text(sections: list[list[str]]) -> str:
    """Paragraphs separated by a blank line, sections by a line of "---" (the transcript, and what parse_script reads)."""
    return f"\n\n{SECTION_BREAK}\n\n".join("\n\n".join(sec) for sec in sections) + "\n"


def parse_script(text: str) -> list[list[str]]:
    sections: list[list[str]] = [[]]
    for block in text.strip().split("\n\n"):
        block = clean(block)
        if block == SECTION_BREAK:
            sections.append([])
        elif block:
            sections[-1].append(block)
    return [s for s in sections if s]


# -- speech ------------------------------------------------------------------------------------------------------


class Ming:
    """Ming-3.0-tts through mlx-audio (the `voice` extra), on this Mac. Offline: the weights must already be in the
    Hugging Face cache. Its default voice, the blind test's, at temperature 0, so every paragraph sounds the same."""

    name = "ming"
    price = 0.0
    voiced_elsewhere = True  # where it can't run (the GitHub publish), the script is still written for the Mac

    def __init__(self, s: BulletinSettings):
        self.s = s
        self.voice = "Ming default"
        self._model = None

    @property
    def available(self) -> bool:
        try:
            import mlx.core  # noqa: F401
            import mlx_audio.tts.utils  # noqa: F401
        except Exception:
            return False
        return True

    unavailable = "Ming needs Apple Silicon and the `voice` extra: the script is saved for the Mac to voice"

    def speak(self, text: str, previous: str = "", following: str = "") -> bytes:
        import io
        import wave

        import numpy as np

        if self._model is None:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")  # never download weights here
            from mlx_audio.tts.utils import load_model

            self._model = load_model(model_path=self.s.ming_model)
        audio = np.concatenate([np.array(r.audio, dtype=np.float32) for r in self._model.generate(text=text, temperature=0.0)])
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._model.sample_rate)
            w.writeframes(pcm.tobytes())
        return buf.getvalue()

    def close(self) -> None:
        self._model = None


class ElevenLabs:
    """Text to speech over plain HTTP. The key comes from ELEVENLABS_API_KEY and never leaves the request header."""

    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
    name = "elevenlabs"
    voiced_elsewhere = False
    unavailable = "no ELEVENLABS_API_KEY"

    def __init__(self, s: BulletinSettings, key: str | None = None, transport: httpx.BaseTransport | None = None):
        self.s = s
        self.key = key if key is not None else os.environ.get("ELEVENLABS_API_KEY", "")
        self.http = httpx.Client(timeout=180, transport=transport)
        self.context = True  # previous_text / next_text; dropped if the model refuses them
        self.voice = s.voice_name
        self.price = s.price_per_million_chars

    @property
    def available(self) -> bool:
        return bool(self.key)

    def speak(self, text: str, previous: str = "", following: str = "") -> bytes:
        if not self.key:
            raise BulletinUnavailable("no ELEVENLABS_API_KEY")
        body = {"text": text, "model_id": self.s.tts_model, "seed": self.s.seed}
        url = self.URL.format(voice=self.s.voice_id)
        headers = {"xi-api-key": self.key}
        r = self.http.post(url, headers=headers, json={**body, "previous_text": previous, "next_text": following} if self.context else body)
        if r.status_code in (400, 422) and self.context:
            self.context = False  # a refused request isn't billed
            r = self.http.post(url, headers=headers, json=body)
        if r.status_code != 200:
            # Status and ElevenLabs' error code only (such as invalid_api_key or detected_unusual_activity):
            # the message text can echo the request.
            raise BulletinUnavailable(f"ElevenLabs answered HTTP {r.status_code}{error_code(r)}")
        return r.content

    def close(self) -> None:
        self.http.close()


def engine(s: BulletinSettings) -> Ming | ElevenLabs:
    return ElevenLabs(s) if s.tts_engine == "elevenlabs" else Ming(s)


def error_code(r: httpx.Response) -> str:
    try:
        detail = r.json().get("detail")
    except Exception:
        return ""
    code = (detail.get("status") or detail.get("code")) if isinstance(detail, dict) else None
    return f" ({code})" if isinstance(code, str) and re.fullmatch(r"[a-z_]{3,60}", code) else ""


def tts_month_spend(store: Store, now: datetime) -> float:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    row = store.conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE task = ? AND created_at >= ?",
                             (TTS_TASK, iso(start))).fetchone()
    return float(row[0])


def log_tts(store: Store, run_id: str | None, tts, chars: int, now: datetime, error: str | None = None) -> float:
    cost = 0.0 if error else chars * tts.price / 1_000_000
    with store.conn:
        store.conn.execute(
            "INSERT INTO llm_calls(run_id, task, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
            "cost_usd, error, created_at) VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?)",
            (run_id, TTS_TASK, tts_model(tts), chars, cost, error, iso(now)))
    return cost


# -- audio -------------------------------------------------------------------------------------------------------


def join(parts: list[tuple[Path, float]], out: Path, bitrate: str = "96k") -> float:
    """Each part followed by its pause, loudness evened out to -16 LUFS, one mono MP3. Returns the duration in seconds."""
    if not shutil.which("ffmpeg"):
        raise BulletinUnavailable("ffmpeg is not installed")
    inputs, chains = [], []
    for i, (path, pause) in enumerate(parts):
        inputs += ["-i", str(path)]
        chains.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=mono,apad=pad_dur={pause}[p{i}]")
    graph = ";".join(chains) + ";" + "".join(f"[p{i}]" for i in range(len(parts))) + \
        f"concat=n={len(parts)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
                    "-ar", "44100", "-ac", "1", "-b:a", bitrate, str(out)], check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                           check=True, capture_output=True, text=True)
    return float(probe.stdout.strip())


# -- the whole thing ---------------------------------------------------------------------------------------------


def paths(audio_dir: Path, day: str) -> dict[str, Path]:
    stem = audio_dir / f"bulletin-{day}"
    return {"mp3": stem.with_suffix(".mp3"), "txt": stem.with_suffix(".txt"), "json": stem.with_suffix(".json")}


def day_edition(store: Store, day: str) -> dict | None:
    row = store.conn.execute("SELECT data FROM editions WHERE desk = 'ai' AND date = ?", (day,)).fetchone()  # the bulletin reads AI's edition
    return json.loads(row["data"]) if row else None


@dataclass
class Result:
    day: str
    mp3: Path
    paragraphs: int
    chars: int
    duration_s: float
    script_cost_usd: float
    tts_cost_usd: float


def tts_model(tts) -> str:
    return tts.s.ming_model.split("/")[-1] if tts.name == "ming" else tts.s.tts_model


def make(store: Store, settings: Settings, day: str, audio_dir: Path, llm: LLM | None, tts: Ming | ElevenLabs,
         now: datetime | None = None, run_id: str | None = None, script: str | None = None) -> Result:
    """Write, voice and encode the bulletin for `day` (a local date with a saved edition).
    `script` reuses a script (the text of an earlier .txt) instead of asking the model for a new one.
    An engine that can't run here but is voiced elsewhere (Ming on the GitHub publish) still gets the script written."""
    now = now or datetime.now(timezone.utc)
    s = settings.bulletin
    if not tts.available and not tts.voiced_elsewhere:
        raise BulletinUnavailable(tts.unavailable)
    out = paths(audio_dir, day)

    script_cost = 0.0
    if script is None:
        edition = day_edition(store, day)
        if edition is None:
            raise BulletinUnavailable(f"no edition saved for {day}: publish first")
        if llm is None or not llm.available:
            raise BulletinUnavailable("no ANTHROPIC_API_KEY to write the script")
        before = llm.cost_usd
        sections = write_script(llm, settings, edition, Date.fromisoformat(day))
        script_cost = llm.cost_usd - before
    else:
        sections = parse_script(script)
    flat = [(p, i == len(sec) - 1) for sec in sections for i, p in enumerate(sec)]
    chars = sum(len(p) for p, _ in flat)
    estimate = chars * tts.price / 1_000_000
    spent = tts_month_spend(store, now)
    if estimate and spent + estimate > s.monthly_budget_usd:
        raise BulletinUnavailable(f"the bulletin's monthly budget of ${s.monthly_budget_usd:.0f} would be passed "
                                  f"(${spent:.2f} spent, this one about ${estimate:.2f})")
    audio_dir.mkdir(parents=True, exist_ok=True)
    out["txt"].write_text(script_text(sections), encoding="utf-8")
    if not tts.available:
        raise BulletinUnavailable(tts.unavailable)

    tts_cost = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, (text, ends_section) in enumerate(flat):
            prev = flat[i - 1][0] if i else ""
            nxt = flat[i + 1][0] if i + 1 < len(flat) else ""
            try:
                audio = tts.speak(text, prev, nxt)
            except BulletinUnavailable as e:
                log_tts(store, run_id, tts, len(text), now, error=str(e))
                raise
            tts_cost += log_tts(store, run_id, tts, len(text), now)
            part = Path(tmp) / f"{i:03d}.audio"  # MP3 (ElevenLabs) or WAV (Ming); ffmpeg reads either
            part.write_bytes(audio)
            last = i == len(flat) - 1
            parts.append((part, 0.0 if last else s.section_pause_s if ends_section else s.pause_s))
        duration = join(parts, out["mp3"], s.bitrate)

    meta = {"date": day, "duration_s": round(duration, 1), "paragraphs": len(flat), "characters": chars,
            "tts_model": tts_model(tts), "voice": tts.voice, "script_prompt": s.prompt if script is None else "reused",
            "script_cost_usd": round(script_cost, 4), "tts_cost_usd": round(tts_cost, 4), "created_at": iso(now)}
    out["json"].write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return Result(day, out["mp3"], len(flat), chars, duration, script_cost, tts_cost)


def for_page(audio_dir: Path | None, day: str) -> dict | None:
    """What a page needs for its player, if that day's bulletin exists: file names and length in minutes."""
    if audio_dir is None:
        return None
    p = paths(audio_dir, day)
    if not p["mp3"].exists():
        return None
    meta = json.loads(p["json"].read_text(encoding="utf-8")) if p["json"].exists() else {}
    secs = float(meta.get("duration_s") or 0)
    return {"date": day, "mp3": p["mp3"], "txt": p["txt"] if p["txt"].exists() else None,
            "minutes": max(1, round(secs / 60)) if secs else None, "voice": meta.get("voice")}
