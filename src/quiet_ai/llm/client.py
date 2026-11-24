"""Thin wrapper around the Anthropic SDK: structured output, prompt caching, a per-item
result cache, cost logging and the monthly budget cap."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from quiet_ai.config import LLMSettings
from quiet_ai.store.db import Store, iso

PROMPTS = Path(__file__).parent / "prompts"
T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    """No API key, budget cap reached, or the model declined."""


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class LLM:
    def __init__(self, settings: LLMSettings, store: Store, run_id: str | None = None, client=None):
        self.s = settings
        self.store = store
        self.run_id = run_id
        self._client = client
        self.calls = 0
        self.cost_usd = 0.0

    @property
    def available(self) -> bool:
        return self._client is not None or has_credentials()

    @property
    def client(self):
        if self._client is None:
            if not has_credentials():
                raise LLMUnavailable("no ANTHROPIC_API_KEY")
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    # -- budget ---------------------------------------------------------------------------

    def month_spend(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        row = self.store.conn.execute("SELECT COALESCE(SUM(cost_usd), 0) AS c FROM llm_calls WHERE created_at >= ?", (iso(start),)).fetchone()
        return float(row["c"])

    def budget_left(self) -> float:
        return self.s.monthly_budget_usd - self.month_spend()

    def cost(self, model: str, usage) -> float:
        p = self.s.prices.get(model)
        if not p:
            return 0.0
        g = lambda name: getattr(usage, name, 0) or 0  # noqa: E731
        return (
            g("input_tokens") * p.input
            + g("output_tokens") * p.output
            + g("cache_read_input_tokens") * p.cache_read
            + g("cache_creation_input_tokens") * p.cache_write
        ) / 1_000_000

    # -- calls ----------------------------------------------------------------------------

    def parse(self, task: str, model: str, system: str, user: str, output: type[T], max_tokens: int = 4000, effort: str = "low") -> T:
        if self.budget_left() <= 0:
            raise LLMUnavailable(f"monthly LLM budget of ${self.s.monthly_budget_usd:.0f} reached")
        now = datetime.now(timezone.utc)
        try:
            resp = self.client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                # The system prompt is identical across calls: cache it.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_format=output,
                output_config={"effort": effort},
                thinking={"type": "disabled"},
            )
        except Exception as e:
            self._log(task, model, None, now, error=f"{type(e).__name__}: {e}"[:300])
            raise
        cost = self._log(task, model, resp.usage, now)
        self.calls += 1
        self.cost_usd += cost
        if resp.stop_reason == "refusal":
            raise LLMUnavailable("model declined the request")
        if resp.parsed_output is None:
            raise LLMUnavailable(f"no structured output (stop_reason={resp.stop_reason})")
        return resp.parsed_output

    def _log(self, task: str, model: str, usage, now: datetime, error: str | None = None) -> float:
        cost = self.cost(model, usage) if usage else 0.0
        g = lambda name: (getattr(usage, name, 0) or 0) if usage else 0  # noqa: E731
        with self.store.conn:
            self.store.conn.execute(
                "INSERT INTO llm_calls(run_id, task, model, input_tokens, output_tokens, cache_read_tokens, "
                "cache_write_tokens, cost_usd, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.run_id, task, model, g("input_tokens"), g("output_tokens"), g("cache_read_input_tokens"),
                 g("cache_creation_input_tokens"), cost, error, iso(now)),
            )
        return cost

    # -- per-item result cache -------------------------------------------------------------

    def cached(self, task: str, version: str, hashes: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(hashes), 500):
            chunk = hashes[i : i + 500]
            rows = self.store.conn.execute(
                f"SELECT content_hash, result FROM llm_cache WHERE task = ? AND prompt_version = ? "
                f"AND content_hash IN ({','.join('?' * len(chunk))})",
                [task, version, *chunk],
            )
            out.update({r["content_hash"]: json.loads(r["result"]) for r in rows})
        return out

    def remember(self, task: str, version: str, model: str, results: dict[str, dict]) -> None:
        now = iso(datetime.now(timezone.utc))
        with self.store.conn:
            self.store.conn.executemany(
                "INSERT OR REPLACE INTO llm_cache(task, prompt_version, content_hash, model, result, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                [(task, version, h, model, json.dumps(r, sort_keys=True), now) for h, r in results.items()],
            )
