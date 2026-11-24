"""OpenRouter model list (keyless): a new entry means a model just became usable via API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quiet_ai.fetchers.base import Context, Task
from quiet_ai.store.models import Item
from quiet_ai.text import clean_text

NAME = "openrouter"
API = "https://openrouter.ai/api/v1/models"


def tasks(ctx: Context) -> list[Task]:
    return [Task("openrouter", NAME, lambda: fetch(ctx))]


def fetch(ctx: Context) -> list[Item]:
    r = ctx.http.get(API, key="openrouter:models")
    cutoff = ctx.now - timedelta(days=ctx.settings.openrouter.max_age_days)
    items = []
    for m in r.json().get("data", []):
        mid = m.get("id", "")
        if not mid or ":" in mid:  # skip ":free", ":batch" and other variants
            continue
        created = datetime.fromtimestamp(m["created"], tz=timezone.utc) if m.get("created") else None
        if not created or created < cutoff:
            continue
        pricing = m.get("pricing") or {}
        items.append(
            Item(
                id=f"openrouter:{mid}",
                source="openrouter",
                kind="model",
                url=f"https://openrouter.ai/{mid}",
                title=m.get("name") or mid,
                lang="en",
                published_at=created,
                author=mid.split("/")[0],
                summary=clean_text(m.get("description"), ctx.settings.ingest.summary_max_chars),
                extra={
                    "model_id": mid,
                    "context_length": m.get("context_length"),
                    "price_prompt": pricing.get("prompt"),
                    "price_completion": pricing.get("completion"),
                    "hugging_face_id": m.get("hugging_face_id") or None,
                },
                fetched_at=ctx.now,
            )
        )
    return items
