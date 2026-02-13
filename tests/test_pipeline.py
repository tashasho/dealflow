"""Integration test for the pipeline (with mocked externals)."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import Deal, DealPriority, DealSource, GitHubMetrics
from src.pipeline import _deduplicate, run_pipeline
from src.storage.db import DealDatabase


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_deduplicate_by_name(self):
        deals = [
            Deal(startup_name="Alpha", description="First", source=DealSource.GITHUB),
            Deal(startup_name="alpha", description="Dupe", source=DealSource.YC),
            Deal(startup_name="Beta", description="Second", source=DealSource.GITHUB),
        ]
        result = await _deduplicate(deals)
        assert len(result) == 2
        assert result[0].startup_name == "Alpha"
        assert result[1].startup_name == "Beta"


class TestDealDatabase:
    @pytest.fixture
    def db(self, tmp_path):
        db_path = tmp_path / "test_deals.db"
        database = DealDatabase(db_path)
        yield database
        database.close()

    def test_save_and_retrieve_deal(self, db):
        deal = Deal(
            startup_name="TestCo",
            website="https://testco.ai",
            description="Test startup",
            source=DealSource.GITHUB,
        )
        deal_id = db.save_deal(deal)
        assert deal_id > 0

        # Fetch
        since = datetime(2020, 1, 1)
        rows = db.get_deals_since(since)
        assert len(rows) == 1
        assert rows[0]["name"] == "TestCo"

    def test_duplicate_handling(self, db):
        deal = Deal(
            startup_name="DupeCo",
            description="Test",
            source=DealSource.GITHUB,
        )
        id1 = db.save_deal(deal)
        id2 = db.save_deal(deal)
        # Should return same ID for duplicate
        assert id1 == id2

    def test_scored_deal_storage(self, db):
        from src.models import ScoreBreakdown, ScoredDeal

        deal = Deal(
            startup_name="ScoredCo",
            description="Scored test",
            source=DealSource.MANUAL,
        )
        deal_id = db.save_deal(deal)

        scored = ScoredDeal(
            deal=deal,
            total_score=88,
            breakdown=ScoreBreakdown(
                problem_severity=26,
                differentiation=22,
                team=22,
                market_readiness=18,
            ),
            summary="Great startup",
            strengths=["Strong team", "Good market"],
            red_flags=["Early stage"],
            priority=DealPriority.HIGH,
        )
        db.save_scored_deal(deal_id, scored)

        results = db.get_scored_deals_since(datetime(2020, 1, 1), min_score=80)
        assert len(results) == 1
        assert results[0].total_score == 88
        assert results[0].deal.startup_name == "ScoredCo"
