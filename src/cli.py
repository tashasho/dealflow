"""CLI entry point for the deal flow pipeline."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import click
from rich.console import Console

from src.config import Config
from src.models import Deal, DealSource
from src.notifications.digest import send_digest
from src.pipeline import run_pipeline
from src.scoring.scorer import score_deal
from src.enrichment.website import extract_website_signals
from src.storage.db import DealDatabase

console = Console()

VALID_SOURCES = ["github", "product_hunt", "yc", "huggingface", "arxiv"]


@click.group()
def cli():
    """🎯 DealFlow — Enterprise AI Deal Sourcing Pipeline"""
    pass


@cli.command()
@click.option(
    "--source", "-s",
    multiple=True,
    type=click.Choice(VALID_SOURCES, case_sensitive=False),
    help="Specific source(s) to scrape. Omit to run all.",
)
@click.option(
    "--dry-run", is_flag=True,
    help="Score and display results without posting to Slack.",
)
@click.option(
    "--limit", "-l",
    default=20,
    help="Max deals to fetch per source (default: 20).",
)
def run(source: tuple[str, ...], dry_run: bool, limit: int):
    """Execute the full deal flow pipeline: source → enrich → score → notify."""
    # Validate config
    missing = Config.validate()
    if missing and not dry_run:
        console.print(f"[red]❌ Missing config: {', '.join(missing)}[/]")
        console.print("Set them in .env or use --dry-run to test without Slack.")
        raise SystemExit(1)

    if not Config.GEMINI_API_KEY:
        console.print("[red]❌ GEMINI_API_KEY is required for scoring.[/]")
        raise SystemExit(1)

    sources = list(source) if source else None
    asyncio.run(run_pipeline(sources=sources, dry_run=dry_run, limit=limit))


@cli.command()
@click.argument("url")
@click.option("--name", "-n", default=None, help="Startup name (auto-detected if omitted).")
def score(url: str, name: str | None):
    """Score a single startup by its website URL."""
    if not Config.GEMINI_API_KEY:
        console.print("[red]❌ GEMINI_API_KEY is required.[/]")
        raise SystemExit(1)

    async def _score():
        console.print(f"\n[bold blue]🔍 Analyzing {url}…[/]")

        # Extract website signals
        signals = await extract_website_signals(url)

        startup_name = name or url.split("//")[-1].split("/")[0].replace("www.", "")

        deal = Deal(
            startup_name=startup_name,
            website=url,
            description=signals.page_text[:500] if signals.page_text else "",
            website_signals=signals,
            source=DealSource.MANUAL,
        )

        console.print(f"[bold blue]🤖 Scoring with Gemini…[/]")
        result = await score_deal(deal)

        console.print(f"\n{'═' * 60}")
        console.print(f"[bold cyan]  {result.deal.startup_name}[/]")
        console.print(f"{'═' * 60}")
        console.print(f"  [bold]Score: {result.total_score}/100[/]")
        console.print(f"  Priority: {result.priority.value.upper()}")
        console.print(f"\n  📝 {result.summary}")

        b = result.breakdown
        console.print(f"\n  [bold]Breakdown:[/]")
        console.print(f"    Problem Severity:  {b.problem_severity}/30")
        console.print(f"    Differentiation:   {b.differentiation}/25")
        console.print(f"    Team:              {b.team}/25")
        console.print(f"    Market Readiness:  {b.market_readiness}/20")

        if result.strengths:
            console.print(f"\n  [green]✅ Strengths:[/]")
            for s in result.strengths:
                console.print(f"    • {s}")

        if result.red_flags:
            console.print(f"\n  [red]⚠️ Red Flags:[/]")
            for rf in result.red_flags:
                console.print(f"    • {rf}")

        console.print(f"{'═' * 60}\n")

    asyncio.run(_score())


@cli.command()
@click.option("--dry-run", is_flag=True, help="Print digest without posting to Slack.")
def digest(dry_run: bool):
    """Generate and send the weekly deal flow digest."""
    Config.ensure_dirs()
    db = DealDatabase(Config.DB_PATH)

    async def _digest():
        console.print("\n[bold blue]📊 Generating weekly digest…[/]")
        text = await send_digest(db, dry_run=dry_run)
        if dry_run:
            console.print(f"\n{'─' * 60}")
            console.print(text)
            console.print(f"{'─' * 60}\n")
        else:
            console.print("[bold green]✅ Digest posted to Slack![/]\n")

    try:
        asyncio.run(_digest())
    finally:
        db.close()


@cli.command(name="list")
@click.option(
    "--min-score", "-m",
    default=75,
    help="Minimum score to display (default: 75).",
)
@click.option(
    "--days", "-d",
    default=7,
    help="Look back N days (default: 7).",
)
def list_deals(min_score: int, days: int):
    """List stored high-priority deals."""
    Config.ensure_dirs()
    db = DealDatabase(Config.DB_PATH)

    try:
        since = datetime.utcnow() - timedelta(days=days)
        deals = db.get_scored_deals_since(since, min_score=min_score)

        if not deals:
            console.print(f"\n[yellow]No deals with score ≥{min_score} in the last {days} days.[/]\n")
            return

        from src.pipeline import _print_results_table
        _print_results_table(deals)
        console.print(f"\n  {len(deals)} deals with score ≥{min_score} in last {days} days\n")

    finally:
        db.close()


@cli.command()
@click.option(
    "--interval", "-i",
    default=6,
    help="Hours between pipeline scans (default: 6).",
)
@click.option(
    "--source", "-s",
    multiple=True,
    type=click.Choice(VALID_SOURCES, case_sensitive=False),
    help="Specific source(s) to scan. Omit to use all.",
)
@click.option(
    "--dry-run", is_flag=True,
    help="Run scans without posting to Slack.",
)
def schedule(interval: int, source: tuple[str, ...], dry_run: bool):
    """Start the automated scheduler (runs until Ctrl+C)."""
    if not Config.GEMINI_API_KEY:
        console.print("[red]❌ GEMINI_API_KEY is required for scoring.[/]")
        raise SystemExit(1)

    from src.scheduler import DealFlowScheduler

    scheduler = DealFlowScheduler(
        scan_interval_hours=interval,
        dry_run=dry_run,
        sources=list(source) if source else None,
    )
    asyncio.run(scheduler.start())


@cli.command()
@click.option(
    "--scan-schedule",
    default="0 */6 * * *",
    help="Cron expression for pipeline scans (default: every 6h).",
)
@click.option(
    "--digest-schedule",
    default="0 9 * * 1",
    help="Cron expression for weekly digest (default: Mon 9AM).",
)
@click.option(
    "--launchd", is_flag=True,
    help="Generate macOS launchd plist instead of crontab.",
)
def crontab(scan_schedule: str, digest_schedule: str, launchd: bool):
    """Generate crontab or launchd entries for system scheduling."""
    from src.scheduler import generate_crontab_entry, generate_launchd_plist

    if launchd:
        plist = generate_launchd_plist()
        plist_path = "~/Library/LaunchAgents/com.dealflow.scanner.plist"
        console.print(f"\n[bold]macOS LaunchAgent plist:[/]")
        console.print(f"[dim]Save to {plist_path}, then run:[/]")
        console.print(f"[dim]  launchctl load {plist_path}[/]\n")
        console.print(plist)
    else:
        entry = generate_crontab_entry(
            scan_schedule=scan_schedule,
            digest_schedule=digest_schedule,
        )
        console.print(f"\n[bold]Add to crontab (crontab -e):[/]\n")
        console.print(entry)

    console.print()


if __name__ == "__main__":
    cli()
