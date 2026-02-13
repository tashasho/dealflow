"""Tests for Pydantic data models."""

from src.models import (
    Deal,
    DealPriority,
    DealSource,
    Founder,
    GitHubMetrics,
    ScoreBreakdown,
    ScoredDeal,
    WebsiteSignals,
    WeeklyDigest,
)


class TestScoreBreakdown:
    def test_total_calculation(self):
        b = ScoreBreakdown(
            problem_severity=25,
            differentiation=20,
            team=18,
            market_readiness=15,
        )
        assert b.total == 78

    def test_min_values(self):
        b = ScoreBreakdown()
        assert b.total == 0

    def test_max_values(self):
        b = ScoreBreakdown(
            problem_severity=30,
            differentiation=25,
            team=25,
            market_readiness=20,
        )
        assert b.total == 100


class TestScoredDeal:
    def _make_deal(self) -> Deal:
        return Deal(
            startup_name="TestCo",
            description="Test startup",
            source=DealSource.MANUAL,
        )

    def test_classify_high(self):
        sd = ScoredDeal(
            deal=self._make_deal(),
            total_score=90,
            breakdown=ScoreBreakdown(
                problem_severity=28, differentiation=22, team=22, market_readiness=18
            ),
        )
        assert sd.classify() == DealPriority.HIGH

    def test_classify_worth_watching(self):
        sd = ScoredDeal(
            deal=self._make_deal(),
            total_score=80,
            breakdown=ScoreBreakdown(
                problem_severity=22, differentiation=18, team=22, market_readiness=18
            ),
        )
        assert sd.classify() == DealPriority.WORTH_WATCHING

    def test_classify_low(self):
        sd = ScoredDeal(
            deal=self._make_deal(),
            total_score=50,
            breakdown=ScoreBreakdown(
                problem_severity=15, differentiation=10, team=15, market_readiness=10
            ),
        )
        assert sd.classify() == DealPriority.LOW

    def test_strengths_and_flags(self):
        sd = ScoredDeal(
            deal=self._make_deal(),
            total_score=85,
            breakdown=ScoreBreakdown(
                problem_severity=25, differentiation=20, team=20, market_readiness=20
            ),
            summary="AI-powered compliance tool",
            strengths=["Strong founding team", "Clear enterprise focus"],
            red_flags=["No public pricing"],
        )
        assert len(sd.strengths) == 2
        assert len(sd.red_flags) == 1
        assert sd.summary == "AI-powered compliance tool"


class TestDealModel:
    def test_default_values(self):
        deal = Deal(startup_name="Foo", description="Bar")
        assert deal.source == DealSource.MANUAL
        assert deal.founders == []
        assert deal.github is None
        assert deal.website_signals is None

    def test_with_github_metrics(self):
        deal = Deal(
            startup_name="AgentCo",
            description="Agentic workflows",
            github=GitHubMetrics(
                repo_url="https://github.com/test/repo",
                stars=1200,
                star_velocity_7d=500,
                enterprise_signals=["SOC2", "SAML"],
            ),
            source=DealSource.GITHUB,
        )
        assert deal.github.stars == 1200
        assert "SOC2" in deal.github.enterprise_signals

    def test_serialization_roundtrip(self):
        deal = Deal(
            startup_name="SerialCo",
            description="Test",
            founders=[
                Founder(name="Alice", has_phd=True, notable_companies=["OpenAI"]),
            ],
        )
        json_str = deal.model_dump_json()
        restored = Deal.model_validate_json(json_str)
        assert restored.startup_name == "SerialCo"
        assert restored.founders[0].has_phd is True
        assert restored.founders[0].notable_companies == ["OpenAI"]


class TestFounder:
    def test_defaults(self):
        f = Founder(name="Bob")
        assert f.has_phd is False
        assert f.has_exits is False
        assert f.notable_companies == []
        assert f.linkedin_url is None


class TestWebsiteSignals:
    def test_defaults(self):
        ws = WebsiteSignals()
        assert ws.has_pricing is False
        assert ws.has_book_demo is False
        assert ws.page_text == ""
