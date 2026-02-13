"""Cron-based scheduler for automated pipeline runs."""

from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime

from rich.console import Console

from src.config import Config
from src.notifications.digest import send_digest
from src.pipeline import run_pipeline
from src.storage.db import DealDatabase

console = Console()


class DealFlowScheduler:
    """
    Lightweight cron-style scheduler for the deal flow pipeline.

    Runs two recurring jobs:
    1. Pipeline scan — every N hours (default: 6)
    2. Weekly digest — every Monday at a configurable hour

    Uses asyncio.sleep for timing — no external cron dependency.
    For production use, consider wrapping with systemd or launchd.
    """

    def __init__(
        self,
        scan_interval_hours: int = 6,
        digest_day: int = 0,  # 0 = Monday
        digest_hour: int = 9,  # 9 AM
        dry_run: bool = False,
        sources: list[str] | None = None,
    ) -> None:
        self.scan_interval = scan_interval_hours * 3600
        self.digest_day = digest_day
        self.digest_hour = digest_hour
        self.dry_run = dry_run
        self.sources = sources
        self._running = False

    async def _run_scan(self) -> None:
        """Execute a single pipeline scan."""
        console.print(
            f"\n[bold blue]⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M')}] "
            f"Scheduled scan starting…[/]"
        )
        try:
            await run_pipeline(
                sources=self.sources,
                dry_run=self.dry_run,
                limit=20,
            )
        except Exception as e:
            console.print(f"[red]❌ Scan failed: {e}[/]")

    async def _run_digest(self) -> None:
        """Generate and send the weekly digest."""
        console.print(
            f"\n[bold blue]📊 [{datetime.now().strftime('%Y-%m-%d %H:%M')}] "
            f"Weekly digest generating…[/]"
        )
        Config.ensure_dirs()
        db = DealDatabase(Config.DB_PATH)
        try:
            await send_digest(db, dry_run=self.dry_run)
            console.print("[bold green]✅ Digest sent![/]")
        except Exception as e:
            console.print(f"[red]❌ Digest failed: {e}[/]")
        finally:
            db.close()

    async def _scan_loop(self) -> None:
        """Run pipeline scans at fixed intervals."""
        while self._running:
            await self._run_scan()
            console.print(
                f"[dim]💤 Next scan in {self.scan_interval // 3600}h "
                f"({datetime.now().strftime('%H:%M')})[/]"
            )
            await asyncio.sleep(self.scan_interval)

    async def _digest_loop(self) -> None:
        """Check for weekly digest trigger every hour."""
        while self._running:
            now = datetime.now()
            # Check if it's the right day and hour
            if now.weekday() == self.digest_day and now.hour == self.digest_hour:
                await self._run_digest()
                # Sleep until next day to avoid re-triggering
                await asyncio.sleep(24 * 3600)
            else:
                # Check again in 30 minutes
                await asyncio.sleep(30 * 60)

    def _handle_shutdown(self, signum, frame) -> None:
        """Handle graceful shutdown on SIGINT/SIGTERM."""
        console.print("\n[bold yellow]🛑 Shutting down scheduler…[/]")
        self._running = False

    async def start(self) -> None:
        """Start the scheduler with both scan and digest loops."""
        self._running = True

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        console.print("\n[bold green]🚀 DealFlow Scheduler Started[/]")
        console.print(f"  📡 Pipeline scan: every {self.scan_interval // 3600} hours")
        console.print(f"  📊 Weekly digest: {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][self.digest_day]} at {self.digest_hour:02d}:00")
        if self.dry_run:
            console.print("  🏃 Mode: dry-run (no Slack posts)")
        if self.sources:
            console.print(f"  🔍 Sources: {', '.join(self.sources)}")
        console.print("  Press Ctrl+C to stop\n")

        # Run both loops concurrently
        tasks = [
            asyncio.create_task(self._scan_loop()),
            asyncio.create_task(self._digest_loop()),
        ]

        try:
            # Wait until shutdown signal
            while self._running:
                await asyncio.sleep(1)
        finally:
            # Cancel tasks
            for task in tasks:
                task.cancel()
            # Wait for cancellation
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        console.print("[bold green]✅ Scheduler stopped cleanly.[/]\n")


def generate_crontab_entry(
    python_path: str = "python3",
    project_dir: str = "/Users/bhumikamarmat/dealflow",
    scan_schedule: str = "0 */6 * * *",
    digest_schedule: str = "0 9 * * 1",
) -> str:
    """
    Generate crontab entries for system-level scheduling.

    Returns a string suitable for adding to crontab via `crontab -e`.
    """
    lines = [
        f"# DealFlow — Enterprise AI Deal Sourcing",
        f"# Pipeline scan (every {scan_schedule})",
        f"{scan_schedule} cd {project_dir} && {python_path} -m src.cli run >> {project_dir}/data/cron.log 2>&1",
        f"",
        f"# Weekly digest ({digest_schedule})",
        f"{digest_schedule} cd {project_dir} && {python_path} -m src.cli digest >> {project_dir}/data/cron.log 2>&1",
    ]
    return "\n".join(lines)


def generate_launchd_plist(
    scan_interval_hours: int = 6,
    project_dir: str = "/Users/bhumikamarmat/dealflow",
) -> str:
    """
    Generate a macOS launchd plist for scheduling.

    Save to ~/Library/LaunchAgents/com.dealflow.scanner.plist
    Then: launchctl load ~/Library/LaunchAgents/com.dealflow.scanner.plist
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.dealflow.scanner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>src.cli</string>
        <string>run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_dir}</string>
    <key>StartInterval</key>
    <integer>{scan_interval_hours * 3600}</integer>
    <key>StandardOutPath</key>
    <string>{project_dir}/data/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>{project_dir}/data/launchd_error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>"""
