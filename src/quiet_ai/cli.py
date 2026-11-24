"""qa: the quiet-ai command line."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from quiet_ai.config import ROOT, load_accounts, load_dotenv, load_settings, load_sources
from quiet_ai.fetchers.base import Context, run_tasks
from quiet_ai.http import Http
from quiet_ai.llm.client import LLM
from quiet_ai.pipeline import edition as edition_mod
from quiet_ai.pipeline import momentum
from quiet_ai.pipeline import stories as story_views
from quiet_ai.pipeline.ingest import build_tasks, ingest as run_ingest
from quiet_ai.pipeline.process import default_embedder, period_views, run_analysis, run_cluster
from quiet_ai.render_terminal import render
from quiet_ai.site import build as site_build
from quiet_ai.store.db import Store

FIXTURES = ROOT / "tests" / "fixtures" / "http"

app = typer.Typer(no_args_is_help=True, add_completion=False, help="quiet-ai: a quiet daily overview of AI.")
sources_app = typer.Typer(no_args_is_help=True, help="Inspect configured sources.")
app.add_typer(sources_app, name="sources")
console = Console()

DryRun = Annotated[bool, typer.Option("--dry-run", help="Replay recorded fixtures: no network, nothing written.")]
Only = Annotated[list[str] | None, typer.Option("--source", "-s", help="Only these sources or fetchers (repeatable).")]

_STATUS_STYLE = {"ok": "green", "not_modified": "cyan", "error": "red", "robots_blocked": "yellow", "no_fixture": "dim"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _replay_now() -> datetime:
    meta = FIXTURES / "meta.json"
    if meta.exists():
        return datetime.fromisoformat(json.loads(meta.read_text())["recorded_at"])
    return _now()


def _context(mode: str, fetch_state: dict | None = None) -> Context:
    settings = load_settings()
    http = Http(settings.http, mode=mode, fixtures_dir=FIXTURES if mode != "live" else None, fetch_state=fetch_state)
    now = _replay_now() if mode == "replay" else _now()
    return Context(settings=settings, sources=load_sources(), accounts=load_accounts(), http=http, now=now)


@app.command()
def ingest(
    only: Only = None,
    dry_run: DryRun = False,
    record: Annotated[bool, typer.Option("--record", help="Fetch live and save trimmed fixtures (dev only).")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show every source, not only problems.")] = False,
) -> None:
    """Fetch every source and store new items in SQLite."""
    if dry_run and record:
        raise typer.BadParameter("--dry-run and --record are exclusive")
    mode = "replay" if dry_run else "record" if record else "live"
    settings = load_settings()
    store = Store(":memory:" if mode != "live" else ROOT / settings.db_path)
    ctx = _context(mode, fetch_state=store.load_fetch_state() if mode == "live" else None)
    ctx.known_urls = store.urls_for_sources([f.id for f in ctx.sources.feeds if f.sitemap])
    try:
        reports = run_ingest(ctx, store, only=only, dry_run=dry_run)
    finally:
        ctx.http.close()
    if record:
        (FIXTURES / "meta.json").write_text(json.dumps({"recorded_at": ctx.now.isoformat()}) + "\n")

    table = Table(title=f"ingest ({mode}) {ctx.now:%Y-%m-%d %H:%M} UTC", show_lines=False)
    for col in ("source", "fetcher", "status", "items", "new", "note"):
        table.add_column(col, justify="right" if col in ("items", "new") else "left")
    shown = 0
    for rep in sorted(reports, key=lambda r: (r.result.fetcher, r.result.source)):
        res = rep.result
        if res.status == "no_fixture" and not verbose:
            continue
        if not verbose and res.status in ("ok", "not_modified") and res.fetcher == "bluesky":
            continue  # 50 accounts; summarized below
        style = _STATUS_STYLE.get(res.status, "")
        table.add_row(res.source, res.fetcher, f"[{style}]{res.status}[/]", str(len(res.items)), str(rep.new), (res.error or "")[:60])
        shown += 1
    console.print(table)

    by_status = Counter(r.result.status for r in reports)
    by_kind: Counter[str] = Counter()
    for r in reports:
        for it in r.result.items:
            by_kind[it.kind] += 1
    bsky = [r for r in reports if r.result.fetcher == "bluesky"]
    if bsky and not verbose:
        console.print(
            f"bluesky: {len(bsky)} accounts, {sum(len(r.result.items) for r in bsky)} posts, "
            f"{sum(r.new for r in bsky)} new, {sum(r.result.status not in ('ok', 'not_modified') for r in bsky)} failed"
        )
    console.print("sources: " + ", ".join(f"{k} {v}" for k, v in by_status.most_common()))
    console.print("items by kind: " + ", ".join(f"{k} {v}" for k, v in by_kind.most_common()))
    console.print(f"new items stored: {sum(r.new for r in reports)}" + ("  (in memory only)" if mode != "live" else ""))
    store.close()


@app.command()
def cluster(
    dry_run: DryRun = False,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Keyword relevance only; skip Haiku.")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Stories to print.")] = 15,
    singles: Annotated[bool, typer.Option("--singles", help="Also print one-item stories.")] = False,
) -> None:
    """Relevance filter, embeddings and story clustering; prints the current stories."""
    load_dotenv()
    settings, sources = load_settings(), load_sources()
    if dry_run:
        store = Store(":memory:")
        ctx = _context("replay")
        run_ingest(ctx, store, dry_run=True)
        ctx.http.close()
        now = ctx.now
    else:
        store = Store(ROOT / settings.db_path)
        now = _now()
    run_id = store.start_run("cluster", dry_run, now)
    llm = None if (dry_run or no_llm) else LLM(settings.llm, store, run_id)
    embedder = default_embedder(settings, offline=dry_run)
    result = run_cluster(store, settings, sources, now, llm, embedder)
    store.finish_run(run_id, _now())

    views = story_views.active(store, sources, now, settings.cluster.window_hours)
    shown = [v for v in views if singles or v.items > 1]
    table = Table(title=f"stories, last {settings.cluster.window_hours}h ({now:%Y-%m-%d %H:%M} UTC)")
    for col in ("#", "story", "items", "outlets", "sources"):
        table.add_column(col, justify="right" if col in ("#", "items", "outlets") else "left", overflow="fold")
    for n, v in enumerate(shown[:limit], 1):
        srcs = ", ".join(v.sources[:5]) + (f" +{len(v.sources) - 5}" if len(v.sources) > 5 else "")
        kinds = " ".join(f"{k}:{c}" for k, c in v.kinds.most_common())
        table.add_row(str(n), v.title[:90], str(v.items), str(len(v.outlets)), f"{srcs}\n[dim]{kinds}[/]")
    console.print(table)

    r, cl = result.relevance, result.cluster
    console.print("relevance: " + ", ".join(f"{k} {v}" for k, v in sorted(r.by.items())) +
                  f"; duplicates {r.duplicates}; haiku {r.llm_items} items in {r.llm_calls} calls (${r.llm_cost_usd:.4f}); undecided {r.pending}")
    if r.note:
        console.print(f"[yellow]note: {r.note}[/]")
    console.print(f"embedded {result.embedded} with {result.embedder}; placed {cl.placed} items: "
                  f"{cl.by_link} by link, {cl.by_similarity} by similarity, {cl.new_stories} new stories, {cl.merged} merged")
    console.print(f"active stories: {len(views)} ({sum(v.items > 1 for v in views)} with 2+ items)")
    store.close()


def _open(dry_run: bool) -> tuple[Store, datetime]:
    """The live DB, or (dry run) an in-memory DB filled from fixtures and clustered."""
    settings, sources = load_settings(), load_sources()
    if not dry_run:
        return Store(ROOT / settings.db_path), _now()
    store = Store(":memory:")
    ctx = _context("replay")
    run_ingest(ctx, store, dry_run=True)
    ctx.http.close()
    run_cluster(store, settings, sources, ctx.now, None, default_embedder(settings, offline=True))
    return store, ctx.now


def _analyze_and_print(store: Store, now: datetime, dry_run: bool, no_llm: bool, run_id: str, build_site: bool = False) -> None:
    settings, sources = load_settings(), load_sources()
    llm = None if (dry_run or no_llm) else LLM(settings.llm, store, run_id)
    res = run_analysis(store, settings, sources, now, llm)
    ed = edition_mod.build(store, settings, sources, res.scores, res.rising, now, settings.analysis.top_stories)
    render(console, ed)
    if build_site:
        pages = site_build.render_all(_editions(store, settings, sources, now, res.views), ROOT / settings.site.out_dir, settings.site.timezone)
        console.print(f"[dim]site: {len(pages)} views in {pages[0].parent}[/]")
    n, b, s = res.news, res.builders, res.summaries
    cost = llm.cost_usd if llm else 0.0
    console.print(f"\n[dim]labels: {n.labeled} news ({n.from_cache} cached, {n.low_confidence} low confidence, "
                  f"{n.evidence_dropped} evidence phrases rejected), {b.labeled} builder; summaries: {s.summarized} new, "
                  f"{s.unchanged} unchanged; weather {'updated' if res.weather.weather else 'unchanged'}; "
                  f"LLM {llm.calls if llm else 0} calls, ${cost:.4f} this run[/]")
    for note in res.notes:
        console.print(f"[yellow]note: {note}[/]")


@app.command()
def classify(
    dry_run: DryRun = False,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Skip Haiku/Sonnet; momentum and view only.")] = False,
) -> None:
    """Label items, score momentum, summarize the top stories; print the ranked stories."""
    load_dotenv()
    store, now = _open(dry_run)
    run_id = store.start_run("classify", dry_run, now)
    _analyze_and_print(store, now, dry_run, no_llm, run_id)
    store.finish_run(run_id, _now())
    store.close()


@app.command()
def stories(
    dry_run: DryRun = False,
    period: Annotated[str, typer.Option("--period", "-p", help="day, week, month or year (site.periods keys).")] = "",
) -> None:
    """Print the current ranked stories from the database (no LLM calls)."""
    settings, sources = load_settings(), load_sources()
    chosen = next((p for p in settings.site.periods if p.key == period), settings.site.periods[0]) if period else settings.site.periods[0]
    store, now = _open(dry_run)
    scores = momentum.score_stories(store, settings, sources, now, chosen)
    ed = edition_mod.build(store, settings, sources, scores, momentum.rising(store, settings, now, chosen.hours), now,
                           settings.analysis.top_stories, chosen)
    console.print(f"[dim]period: last {chosen.label}[/]")
    render(console, ed)
    store.close()


@app.command()
def run(
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Skip every LLM step.")] = False,
) -> None:
    """Everything: ingest, relevance, embeddings, stories, labels, summaries; print the edition."""
    load_dotenv()
    settings, sources = load_settings(), load_sources()
    store = Store(ROOT / settings.db_path)
    ctx = _context("live", fetch_state=store.load_fetch_state())
    ctx.known_urls = store.urls_for_sources([f.id for f in ctx.sources.feeds if f.sitemap])
    reports = run_ingest(ctx, store)
    ctx.http.close()
    bad = [r.result.source for r in reports if r.result.status not in ("ok", "not_modified")]
    console.print(f"[dim]ingest: {sum(r.new for r in reports)} new items; {len(bad)} sources failed {', '.join(bad[:8])}[/]")
    now = _now()
    run_id = store.start_run("run", False, now)
    llm = None if no_llm else LLM(settings.llm, store, run_id)
    cl = run_cluster(store, settings, sources, now, llm, default_embedder(settings))
    console.print(f"[dim]stories: {cl.cluster.placed} items placed, {cl.cluster.new_stories} new stories; "
                  f"{cl.relevance.pending} items undecided[/]")
    _analyze_and_print(store, now, False, no_llm, run_id, build_site=True)
    store.finish_run(run_id, _now())
    store.close()


def _editions(store: Store, settings, sources, now: datetime, views=None) -> list[dict]:
    views = views or period_views(store, settings, sources, now)
    return [edition_mod.build(store, settings, sources, v.scores, v.rising, now, settings.analysis.top_stories, v.period) for v in views.values()]


def _build_site(dry_run: bool, out: Path | None) -> Path:
    settings, sources = load_settings(), load_sources()
    store, now = _open(dry_run)
    pages = site_build.render_all(_editions(store, settings, sources, now), out or ROOT / settings.site.out_dir, settings.site.timezone)
    store.close()
    return pages[0]


Out = Annotated[Path | None, typer.Option("--out", help="Output directory (default: site.out_dir).")]


@app.command()
def build(dry_run: DryRun = False, out: Out = None) -> None:
    """Render the static site from the database (no LLM calls)."""
    console.print(f"wrote {_build_site(dry_run, out)}")


@app.command()
def serve(
    port: Annotated[int, typer.Option("--port", "-p")] = 8765,
    rebuild: Annotated[bool, typer.Option("--build/--no-build", help="Build before serving.")] = True,
    dry_run: DryRun = False,
    out: Out = None,
) -> None:
    """Preview the site locally at http://localhost:PORT."""
    import functools
    import http.server

    settings = load_settings()
    root = out or ROOT / settings.site.out_dir
    if rebuild:
        _build_site(dry_run, out)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        console.print(f"serving {root} at http://localhost:{port}  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


@app.command()
def costs() -> None:
    """LLM spend this month, by task and model, against the cap."""
    settings = load_settings()
    store = Store(ROOT / settings.db_path)
    now = _now()
    start = now.replace(day=1, hour=0, minute=0, second=0)
    rows = store.conn.execute(
        "SELECT task, model, COUNT(*) calls, SUM(input_tokens) i, SUM(output_tokens) o, SUM(cache_read_tokens) cr, "
        "SUM(cost_usd) c, SUM(error IS NOT NULL) errs FROM llm_calls WHERE created_at >= ? GROUP BY task, model ORDER BY c DESC",
        (start.isoformat(timespec="seconds"),),
    ).fetchall()
    table = Table(title=f"LLM costs since {start:%Y-%m-%d}")
    for col in ("task", "model", "calls", "errors", "input", "output", "cache read", "USD"):
        table.add_column(col, justify="left" if col in ("task", "model") else "right")
    total = 0.0
    for r in rows:
        total += r["c"] or 0
        table.add_row(r["task"], r["model"], str(r["calls"]), str(r["errs"]), f"{r['i'] or 0:,}", f"{r['o'] or 0:,}", f"{r['cr'] or 0:,}", f"{r['c'] or 0:.4f}")
    console.print(table)
    cap = settings.llm.monthly_budget_usd
    first = store.conn.execute("SELECT MIN(created_at) FROM llm_calls WHERE created_at >= ?", (start.isoformat(timespec="seconds"),)).fetchone()[0]
    days = max(1.0, (now - datetime.fromisoformat(first)).total_seconds() / 86400) if first else 1.0
    console.print(f"month to date ${total:.4f} of ${cap:.2f} cap; on pace for ${total / days * 30:.2f} this month")
    store.close()


@sources_app.command("check")
def sources_check(
    only: Only = None,
    dry_run: DryRun = False,
    strict: Annotated[bool, typer.Option("--strict", help="Exit 1 if any source fails.")] = False,
) -> None:
    """Fetch every source once and report health. Writes nothing."""
    ctx = _context("replay" if dry_run else "live")
    tasks = build_tasks(ctx, only)
    results = run_tasks(tasks, ctx.settings.http.workers)
    feeds = {f.id: f for f in ctx.sources.feeds}

    table = Table(title=f"source health {ctx.now:%Y-%m-%d %H:%M} UTC")
    for col in ("source", "fetcher", "status", "items", "newest", "note"):
        table.add_column(col, justify="right" if col in ("items", "newest") else "left")
    problems = 0
    for res in sorted(results, key=lambda r: (r.fetcher, r.source)):
        dates = [it.published_at for it in res.items if it.published_at]
        newest = f"{(ctx.now - max(dates)).total_seconds() / 3600:.0f}h" if dates else "-"
        note = res.error or ""
        src = feeds.get(res.source)
        if src and not dry_run:
            signals = {s for url in src.feeds for s in ctx.http.robots(url).content_signals}
            if any("ai-input=no" in s.replace(" ", "") for s in signals) and src.llm:
                note = "robots.txt says ai-input=no but llm is true"
                problems += 1
        if res.status not in ("ok", "not_modified", "no_fixture"):
            problems += 1
        if res.status == "no_fixture":
            continue
        style = _STATUS_STYLE.get(res.status, "")
        table.add_row(res.source, res.fetcher, f"[{style}]{res.status}[/]", str(len(res.items)), newest, note[:70])
    ctx.http.close()
    console.print(table)
    counts = Counter(r.status for r in results)
    console.print("summary: " + ", ".join(f"{k} {v}" for k, v in counts.most_common()) + f"; problems {problems}")
    if strict and problems:
        raise typer.Exit(1)


@sources_app.command("list")
def sources_list() -> None:
    """Print configured sources by kind."""
    srcs = load_sources()
    by_kind = Counter(f.kind for f in srcs.feeds)
    console.print("feeds: " + ", ".join(f"{k} {v}" for k, v in by_kind.items()) + f"; gdelt outlets {len(srcs.gdelt_outlets)}")
    accounts = load_accounts()
    console.print(f"bluesky accounts: {sum(a.bluesky_active for a in accounts)} active of {len(accounts)}")


if __name__ == "__main__":
    app()
