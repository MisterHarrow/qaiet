"""qa: the Qaiet Times command line."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.table import Table

from quiet_ai.config import ROOT, load_accounts, load_dotenv, load_settings, load_sources
from quiet_ai.fetchers.base import Context, run_tasks
from quiet_ai.http import Http
from quiet_ai.llm.client import LLM
from quiet_ai.pipeline import archive
from quiet_ai.pipeline import sentiment as sentiment_mod
from quiet_ai.pipeline import edition as edition_mod
from quiet_ai.pipeline import energy_data, food_data
from quiet_ai.pipeline import momentum
from quiet_ai.pipeline import narratives as narratives_mod
from quiet_ai.pipeline import stories as story_views
from quiet_ai.pipeline.ingest import build_tasks, ingest as run_ingest
from quiet_ai.pipeline.process import all_narratives, build_all_editions, default_embedder, run_analysis, run_cluster
from quiet_ai.render_terminal import render
from quiet_ai.site import build as site_build
from quiet_ai.site.about import about_context
from quiet_ai.store.db import Store

FIXTURES = ROOT / "tests" / "fixtures" / "http"

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Qaiet Times: a quiet daily overview of AI.")
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
        if record and not only:
            console.print(f"[dim]desk data: {_desk_data(store, ctx)}[/]")
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
                  f"; duplicates {r.duplicates}; haiku {r.llm_items} items, {r.translated} translations, in {r.llm_calls} calls "
                  f"(${r.llm_cost_usd:.4f}); undecided {r.pending}")
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
    _desk_data(store, ctx)
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
        tz = settings.site.timezone
        editions = _editions(store, settings, sources, now, res.desk_views)
        for desk, eds in editions.items():
            archive.save_day_edition(store, eds[0], now, tz, desk)
        frozen = archive.freeze(store, ROOT / settings.site.editions_dir, now, tz)
        pruned = archive.prune(store, now, vacuum=bool(frozen))
        if settings.bulletin.daily and llm is not None:
            console.print(f"[dim]bulletin: {_spoken(store, settings, now, llm, run_id)}[/]")
        _render_site(store, settings, sources, now, editions, ROOT / settings.site.out_dir)
        console.print(f"[dim]site: {len(editions)} desks × {len(settings.site.periods)} views, /about, /archive in {settings.site.out_dir}/; "
                      f"froze {', '.join(frozen) or 'nothing'}; pruned {sum(pruned.values())} rows[/]")
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
    console.print(f"[dim]desk data: {_desk_data(store, ctx)}[/]")
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


def _editions(store: Store, settings, sources, now: datetime, desk_views=None) -> dict[str, list[dict]]:
    """desk -> its editions, one per view. Narratives are detected once per desk and shared by its views."""
    return build_all_editions(store, settings, sources, now, desk_views, all_narratives(store, settings, sources, now))


def _render_site(store: Store, settings, sources, now: datetime, editions: dict[str, list[dict]], out: Path) -> Path:
    """Every desk's views, narratives, index and archive (from the frozen files in editions/), plus /about."""
    tz = settings.site.timezone
    audio = ROOT / settings.bulletin.audio_dir
    desks = site_build.desk_list(settings.active_desks, editions)
    pages = []
    for d in desks:
        spoken = audio if d["key"] == "ai" else None  # the bulletin reads AI's edition
        pages += site_build.render_all(editions[d["key"]], out, tz, d, desks, spoken)
        folder = archive.desk_dir(ROOT / settings.site.editions_dir, d["key"])
        site_build.render_archive(archive.load_frozen(folder), out, tz, d, desks, spoken)
        site_build.render_sentiment(sentiment_mod.history(store, desk=d["key"]), out, tz, d, desks)
        site_build.render_narratives(narratives_mod.detect(store, settings, sources, now, d["key"]), out, tz, settings.narratives.min_days, d, desks)
    site_build.render_about(about_context(store, settings, sources, load_accounts(), now, gold=GOLD, crosscheck=crosscheck_path()), out, tz)
    site_build.render_404(out)
    site_build.write_host_config(out)
    return pages[0]


def _build_site(dry_run: bool, out: Path | None) -> Path:
    settings, sources = load_settings(), load_sources()
    store, now = _open(dry_run)
    page = _render_site(store, settings, sources, now, _editions(store, settings, sources, now), out or ROOT / settings.site.out_dir)
    store.close()
    return page


Out = Annotated[Path | None, typer.Option("--out", help="Output directory (default: site.out_dir).")]


@app.command()
def build(dry_run: DryRun = False, out: Out = None) -> None:
    """Render the static site from the database (no LLM calls)."""
    console.print(f"wrote {_build_site(dry_run, out)}")


def _desk_data(store: Store, ctx: Context) -> str:
    """The figures beside the desks' news (energy prices, food prices). Never raises."""
    return (f"energy: {energy_data.update(store, ctx.http, ctx.settings, ctx.now)}; "
            f"food: {food_data.update(store, ctx.http, ctx.settings, ctx.now)}")


@app.command()
def data() -> None:
    """Fetch the figures beside the desks' news (energy and food prices) into the database: a few requests, no
    model calls (qa run does this too). The deploy runs it before qa build so a rebuilt page is current. Never fails."""
    settings = load_settings()
    store = Store(ROOT / settings.db_path)
    ctx = _context("live")
    try:
        console.print(f"desk data: {_desk_data(store, ctx)}")
    finally:
        ctx.http.close()
        store.close()


@app.command(hidden=True)
def energy() -> None:
    """Older name for qa data."""
    data()


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
def pull() -> None:
    """Replace the local database with the latest one saved by the scheduled workflow."""
    import gzip
    import shutil

    import httpx

    settings = load_settings()
    if not settings.db_release_url:
        raise typer.BadParameter("db_release_url is not set in config/settings.yaml")
    target = ROOT / settings.db_path
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".download.gz")
    with httpx.stream("GET", settings.db_release_url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)
    if target.exists():
        shutil.copy(target, target.with_suffix(".db.bak"))
    with gzip.open(tmp, "rb") as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    tmp.unlink()
    store = Store(target)  # runs any pending migrations
    n = store.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    store.close()
    console.print(f"pulled {target} ({target.stat().st_size / 1e6:.1f} MB, {n} items); previous copy kept as {target.with_suffix('.db.bak').name}")


def _spoken(store: Store, settings, now: datetime, llm: LLM, run_id: str, day: str = "", script: str | None = None,
            force: bool = False) -> str:
    """Make the day's spoken bulletin unless it exists. Never raises: a failed bulletin must not stop a publish."""
    from quiet_ai.pipeline import bulletin as bulletin_mod

    day = day or archive.local_date(now, settings.site.timezone)
    audio_dir = ROOT / settings.bulletin.audio_dir
    files = bulletin_mod.paths(audio_dir, day)
    if files["mp3"].exists() and not force:
        return f"{day} already voiced"
    if script is None and files["txt"].exists() and not force:
        script = files["txt"].read_text(encoding="utf-8")  # an earlier try wrote it: voice it, don't pay for a new one
    tts = bulletin_mod.engine(settings.bulletin)
    try:
        res = bulletin_mod.make(store, settings, day, audio_dir, llm, tts, now, run_id, script)
    except Exception as e:  # no key, budget, ffmpeg, HTTP: say so and carry on
        msg = str(e) if isinstance(e, bulletin_mod.BulletinUnavailable) else type(e).__name__
        return f"[yellow]not made: {msg}[/]"
    finally:
        tts.close()
    return (f"{res.mp3.relative_to(ROOT)}, {res.duration_s / 60:.1f} min, {res.paragraphs} paragraphs, {res.chars:,} characters; "
            f"script ${res.script_cost_usd:.3f}, speech ${res.tts_cost_usd:.2f}")


@app.command()
def bulletin(
    day: Annotated[str, typer.Option("--date", help="Local date of a saved edition (default: today).")] = "",
    reuse_script: Annotated[bool, typer.Option("--reuse-script", help="Voice that day's existing script again: no Sonnet call.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Make it again even if that day's audio exists.")] = False,
) -> None:
    """Make the spoken bulletin by hand (qa run makes it every day): Sonnet script, ElevenLabs voice, about $0.60."""
    from quiet_ai.pipeline import bulletin as bulletin_mod

    load_dotenv()
    settings = load_settings()
    now = _now()
    day = day or archive.local_date(now, settings.site.timezone)
    txt = bulletin_mod.paths(ROOT / settings.bulletin.audio_dir, day)["txt"]
    script = None
    if reuse_script:
        if not txt.exists():
            raise typer.BadParameter(f"no script at {txt.relative_to(ROOT)} to reuse")
        script = txt.read_text(encoding="utf-8")
    store = Store(ROOT / settings.db_path)
    run_id = store.start_run("bulletin", False, now)
    note = _spoken(store, settings, now, LLM(settings.llm, store, run_id), run_id, day, script, force)
    store.finish_run(run_id, _now())
    store.close()
    console.print(note)
    if "not made" in note:
        raise typer.Exit(1)


@app.command()
def freeze() -> None:
    """Write finished days' editions to editions/<date>.json (the workflow commits them)."""
    settings = load_settings()
    store = Store(ROOT / settings.db_path)
    written = archive.freeze(store, ROOT / settings.site.editions_dir, _now(), settings.site.timezone)
    console.print(f"froze {', '.join(written) or 'nothing new'}")
    store.close()


@app.command()
def prune(vacuum: Annotated[bool, typer.Option("--vacuum", help="Also compact the file.")] = False) -> None:
    """Delete data the site no longer needs (see pipeline/archive.py for the rules)."""
    settings = load_settings()
    store = Store(ROOT / settings.db_path)
    console.print(archive.prune(store, _now(), vacuum=vacuum))
    store.close()


eval_app = typer.Typer(no_args_is_help=True, help="Check the labels: hand-labeled sample, agreement, bias audit.")
app.add_typer(eval_app, name="eval")
GOLD = ROOT / "tests" / "gold" / "labels.yaml"
CROSSCHECK_MODEL = "claude-opus-5-5"


def crosscheck_path(model: str = CROSSCHECK_MODEL) -> Path:
    return GOLD.parent / f"labels-{model}.yaml"


@eval_app.command("sample")
def eval_sample(
    n: Annotated[int, typer.Option("--n", help="Articles to sample.")] = 50,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing gold file.")] = False,
) -> None:
    """Write a blind, stratified sample to tests/gold/labels.yaml for hand labeling."""
    from quiet_ai import evaluate

    if GOLD.exists() and evaluate.load_gold(GOLD) and not force:
        raise typer.BadParameter(f"{GOLD} already has hand labels; use --force to replace it")
    settings, sources = load_settings(), load_sources()
    store = Store(ROOT / settings.db_path)
    items = evaluate.sample(store, sources, n)
    evaluate.write_gold(items, GOLD)
    console.print(f"wrote {len(items)} articles to {GOLD.relative_to(ROOT)}; fill in track, frame and stance, then run: qa eval score")
    store.close()


@eval_app.command("crosscheck")
def eval_crosscheck(
    model: Annotated[str, typer.Option("--model", help="The larger model that labels the sample.")] = CROSSCHECK_MODEL,
) -> None:
    """Label the hand-label sample with a larger model (same prompt and input as the site), then score the site against it."""
    from quiet_ai import evaluate

    load_dotenv()
    settings, sources = load_settings(), load_sources()
    if model not in settings.llm.prices:
        raise typer.BadParameter(f"no price for {model} in config/settings.yaml (llm.prices); add it so the cost is logged")
    raw = yaml.safe_load(GOLD.read_text(encoding="utf-8")) if GOLD.exists() else None
    sample_items = (raw or {}).get("items") or []
    if not sample_items:
        raise typer.BadParameter(f"no sample in {GOLD.relative_to(ROOT)}; run qa eval sample first")
    store = Store(ROOT / settings.db_path)
    now = _now()
    llm = LLM(settings.llm, store, store.start_run("eval-crosscheck", False, now))
    items = evaluate.crosscheck(store, settings, llm, sample_items, model)
    path = crosscheck_path(model)
    evaluate.write_crosscheck(items, path, model, settings.analysis.news_prompt, now.isoformat(timespec="seconds"))
    console.print(f"{model} labeled {len(items)} of {len(sample_items)} articles in {llm.calls} calls, ${llm.cost_usd:.3f}; wrote {path.relative_to(ROOT)}")
    _print_score(evaluate.score(store, evaluate.load_gold(path), sources), f"site labels vs {model}")
    store.close()


def _print_score(res: dict, title: str) -> None:
    table = Table(title=f"{title} (n={res['n']})")
    for col in ("field", "agree", "n"):
        table.add_column(col, justify="left" if col == "field" else "right")
    for field in ("track", "frame", "stance_exact", "stance_within_1"):
        table.add_row(field.replace("_", " "), f"{res[field]['agree']}%" if res[field]["agree"] is not None else "-", str(res[field]["n"]))
    console.print(table)
    console.print(f"stance mean absolute error: {res['stance_mae']}; within 1 by model confidence: "
                  + ", ".join(f"{k} {v['agree']}% (n={v['n']})" for k, v in res["stance_within_1_by_confidence"].items()))
    if res.get("stance_bias") is not None:
        console.print(f"stance bias (site minus reference, + = site reads more positive): {res['stance_bias']:+.2f}; by group: "
                      + ", ".join(f"{k} {v['bias']:+.2f} (n={v['n']})" for k, v in res["stance_bias_by_group"].items()))
    if res["missing"]:
        console.print(f"[yellow]{res['missing']} labeled items have no site label in this database (pruned or not pulled)[/]")


@eval_app.command("score")
def eval_score() -> None:
    """Agreement between the model's labels and the hand labels, per field."""
    from quiet_ai import evaluate

    settings, sources = load_settings(), load_sources()
    store = Store(ROOT / settings.db_path)
    res = evaluate.score(store, evaluate.load_gold(GOLD), sources)
    cross = evaluate.score(store, evaluate.load_gold(crosscheck_path()), sources)
    store.close()
    if cross["n"]:
        _print_score(cross, f"site labels vs {CROSSCHECK_MODEL}")
    if not res["n"]:
        console.print(f"no hand labels yet in {GOLD.relative_to(ROOT)} (run qa eval sample, then fill it in)")
        return
    _print_score(res, "site labels vs hand labels")


@eval_app.command("audit")
def eval_audit(
    by: Annotated[str, typer.Option("--by", help="group, type or country")] = "group",
    min_n: Annotated[int, typer.Option("--min-n")] = 10,
) -> None:
    """Stance distribution by outlet group, type or country, to spot skew in the classifier."""
    from quiet_ai import evaluate

    settings, sources = load_settings(), load_sources()
    store = Store(ROOT / settings.db_path)
    rows = evaluate.audit(store, sources, by=by, min_n=min_n)
    store.close()
    table = Table(title=f"stance by outlet {by} (confident labels; -2 critical .. +2 enthusiastic)")
    for col in (by, "labels", "mean", "critical", "positive", "unclear"):
        table.add_column(col, justify="left" if col == by else "right")
    for r in rows:
        table.add_row(str(r["key"]), str(r["n"]), f"{r['mean']:+.2f}" if r["mean"] is not None else "-",
                      f"{r['critical']}%" if r["critical"] is not None else "-", f"{r['positive']}%" if r["positive"] is not None else "-", f"{r['unclear']}%")
    console.print(table)


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
