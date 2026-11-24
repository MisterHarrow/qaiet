"""Print an edition in the terminal: ranked stories with labels and evidence, then Rising."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape

STANCE_MARK = {"-2": "−−", "-1": "−", "0": "0", "1": "+", "2": "++", "unclear": "?", "unlabeled": "·"}
STANCE_STYLE = {"-2": "bold", "-1": "default", "0": "dim", "1": "default", "2": "bold", "unclear": "dim italic", "unlabeled": "dim"}


def stance_bar(stance: dict[str, int]) -> str:
    parts = [f"{STANCE_MARK[k]} {v}" for k, v in stance.items() if v]
    return "  ".join(parts)


def render(console: Console, edition: dict, examples_per_stance: int = 2) -> None:
    console.print(f"[bold]quiet-ai[/]  {edition['generated_at'][:16].replace('T', ' ')} UTC")
    weather = edition.get("weather")
    console.print(f"[italic]{escape(weather)}[/]" if weather else "[dim](no weather report yet)[/]")
    if edition["llm"]["budget_reached"]:
        console.print(f"[yellow]Monthly LLM budget (${edition['llm']['budget_usd']:.0f}) reached: labels and summaries are paused.[/]")
    console.print()
    for s in edition["stories"]:
        track = (s["track"] or "unlabeled").capitalize()
        console.print(f"[bold]{s['rank']}.[/] [cyan]{track}[/] · [bold]{escape(s['headline'])}[/]  [dim]momentum {s['momentum']:.2f}[/]")
        console.print(f"   {s['outlets']} outlets · {s['countries']} countries · stance  {stance_bar(s['stance'])}")
        if s["summary"] and s["summary"].get("coverage"):
            console.print(f"   [dim]Coverage:[/] {escape(s['summary']['coverage'])}")
        for group in s["coverage"]:
            mark = STANCE_MARK[group["stance"]]
            for c in group["items"][:examples_per_stance]:
                ev = f' “{escape(c["evidence"][0])}”' if c["evidence"] else ""
                frame = f" [dim]{c['frame']}[/]" if c["frame"] and group["stance"] not in ("unclear", "unlabeled") else ""
                title = c["title_en"] or c["title"]
                if c["llm_opt_out"]:
                    frame = " [dim](not labeled: publisher opted out of AI input)[/]"
                console.print(f"   [{STANCE_STYLE[group['stance']]}]{mark:>2}[/] {escape(c['outlet'])} ({c['country'] or '?'}){frame}: "
                              f"{escape(title[:90])}[dim]{ev}[/]")
        builders = (s["summary"] or {}).get("builders") or s["builders_line"]
        if builders:
            console.print(f"   [dim]Builders:[/] {escape(builders)}")
        console.print()
    if edition["rising"]:
        console.print("[bold]Rising[/]")
        for r in edition["rising"]:
            what = f" — {escape(r['what'])}" if r.get("what") else ""
            why = f"\n      [dim]{escape(r['why'])}[/]" if r.get("why") else ""
            console.print(f"   [cyan]{r['kind']}[/] {escape(r['title'])}{what}  [dim]{escape(r['signal'])}[/]{why}")
