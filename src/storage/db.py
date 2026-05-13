"""SQLite-backed deal storage."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.models import Deal, DealPriority, ScoredDeal, ScoreBreakdown, WeeklyDigest


class DealDatabase:
    """Lightweight SQLite store for deals and scores."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        """Add new columns to existing DBs without dropping data."""
        cols = {row["name"] for row in self._conn.execute("PRAGMA table_info(scored_deals)").fetchall()}
        if "posted_at" not in cols:
            self._conn.execute("ALTER TABLE scored_deals ADD COLUMN posted_at TEXT")
            self._conn.commit()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS deals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                website     TEXT,
                description TEXT,
                source      TEXT NOT NULL,
                source_url  TEXT,
                raw_json    TEXT NOT NULL,
                discovered  TEXT NOT NULL,
                UNIQUE(name, source)
            );

            CREATE TABLE IF NOT EXISTS scored_deals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id         INTEGER NOT NULL REFERENCES deals(id),
                total_score     INTEGER NOT NULL,
                breakdown_json  TEXT NOT NULL,
                summary         TEXT,
                strengths_json  TEXT,
                red_flags_json  TEXT,
                priority        TEXT NOT NULL,
                scored_at       TEXT NOT NULL,
                posted_at       TEXT
            );

            CREATE TABLE IF NOT EXISTS digest_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start  TEXT NOT NULL,
                week_end    TEXT NOT NULL,
                body_json   TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
        """)
        self._conn.commit()
        self._migrate()

    # ------------------------------------------------------------------
    # Deals
    # ------------------------------------------------------------------

    def has_been_seen(self, deal: Deal) -> bool:
        """True if a deal with the same (name, source) was already saved.

        Pipeline uses this to skip re-scoring + re-posting items from past runs.
        """
        row = self._conn.execute(
            "SELECT 1 FROM deals WHERE name = ? AND source = ? LIMIT 1",
            (deal.startup_name, deal.source.value),
        ).fetchone()
        return row is not None

    def save_deal(self, deal: Deal) -> int:
        """Insert a deal, returning its row id. Skips duplicates."""
        try:
            cur = self._conn.execute(
                """INSERT INTO deals (name, website, description, source, source_url, raw_json, discovered)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    deal.startup_name,
                    deal.website,
                    deal.description,
                    deal.source.value,
                    deal.source_url,
                    deal.model_dump_json(),
                    deal.discovered_at.isoformat(),
                ),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]
        except sqlite3.IntegrityError:
            # Duplicate — fetch existing id
            row = self._conn.execute(
                "SELECT id FROM deals WHERE name = ? AND source = ?",
                (deal.startup_name, deal.source.value),
            ).fetchone()
            return row["id"]

    def save_scored_deal(self, deal_id: int, scored: ScoredDeal) -> int:
        cur = self._conn.execute(
            """INSERT INTO scored_deals
               (deal_id, total_score, breakdown_json, summary, strengths_json, red_flags_json, priority, scored_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                deal_id,
                scored.total_score,
                scored.breakdown.model_dump_json(),
                scored.summary,
                json.dumps(scored.strengths),
                json.dumps(scored.red_flags),
                scored.priority.value,
                scored.scored_at.isoformat(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_deals_since(self, since: datetime) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM deals WHERE discovered >= ? ORDER BY discovered DESC",
            (since.isoformat(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_scored_deals_since(
        self, since: datetime, min_score: int = 0
    ) -> list[ScoredDeal]:
        rows = self._conn.execute(
            """SELECT sd.*, d.raw_json AS deal_json
               FROM scored_deals sd
               JOIN deals d ON d.id = sd.deal_id
               WHERE sd.scored_at >= ? AND sd.total_score >= ?
               ORDER BY sd.total_score DESC""",
            (since.isoformat(), min_score),
        ).fetchall()
        results = []
        for r in rows:
            deal = Deal.model_validate_json(r["deal_json"])
            breakdown = ScoreBreakdown.model_validate_json(r["breakdown_json"])
            scored = ScoredDeal(
                deal=deal,
                total_score=r["total_score"],
                breakdown=breakdown,
                summary=r["summary"] or "",
                strengths=json.loads(r["strengths_json"] or "[]"),
                red_flags=json.loads(r["red_flags_json"] or "[]"),
                priority=DealPriority(r["priority"]),
                scored_at=datetime.fromisoformat(r["scored_at"]),
            )
            results.append(scored)
        return results

    def get_high_priority(self, min_score: int = 75) -> list[ScoredDeal]:
        week_ago = datetime.utcnow() - timedelta(days=7)
        return self.get_scored_deals_since(week_ago, min_score)

    # ------------------------------------------------------------------
    # Slack-post tracking (cross-run dedup at the *posting* layer)
    # ------------------------------------------------------------------

    def mark_posted(self, scored_deal_id: int) -> None:
        """Stamp a scored_deals row as posted to Slack."""
        self._conn.execute(
            "UPDATE scored_deals SET posted_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), scored_deal_id),
        )
        self._conn.commit()

    def has_been_posted(self, deal: Deal) -> bool:
        """True if any scored row for this deal has been posted to Slack."""
        row = self._conn.execute(
            """SELECT 1 FROM scored_deals sd
               JOIN deals d ON d.id = sd.deal_id
               WHERE d.name = ? AND d.source = ? AND sd.posted_at IS NOT NULL
               LIMIT 1""",
            (deal.startup_name, deal.source.value),
        ).fetchone()
        return row is not None

    def get_top_unposted(self, limit: int = 5, min_score: int = 0) -> list[tuple[int, ScoredDeal]]:
        """Return top scored deals never posted to Slack, newest first.

        Used as a fallback when today's source pull yields nothing new — keeps
        the channel useful while guaranteeing no duplicates with past posts.
        """
        rows = self._conn.execute(
            """SELECT sd.id AS sd_id, sd.*, d.raw_json AS deal_json
               FROM scored_deals sd
               JOIN deals d ON d.id = sd.deal_id
               WHERE sd.posted_at IS NULL AND sd.total_score >= ?
               ORDER BY sd.total_score DESC, sd.scored_at DESC
               LIMIT ?""",
            (min_score, limit),
        ).fetchall()

        results: list[tuple[int, ScoredDeal]] = []
        for r in rows:
            deal = Deal.model_validate_json(r["deal_json"])
            breakdown = ScoreBreakdown.model_validate_json(r["breakdown_json"])
            scored = ScoredDeal(
                deal=deal,
                total_score=r["total_score"],
                breakdown=breakdown,
                summary=r["summary"] or "",
                strengths=json.loads(r["strengths_json"] or "[]"),
                red_flags=json.loads(r["red_flags_json"] or "[]"),
                priority=DealPriority(r["priority"]),
                scored_at=datetime.fromisoformat(r["scored_at"]),
            )
            results.append((r["sd_id"], scored))
        return results

    # ------------------------------------------------------------------
    # Digest
    # ------------------------------------------------------------------

    def save_digest(self, digest: WeeklyDigest) -> None:
        self._conn.execute(
            """INSERT INTO digest_history (week_start, week_end, body_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                digest.week_start.isoformat(),
                digest.week_end.isoformat(),
                digest.model_dump_json(),
                datetime.utcnow().isoformat(),
            ),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
