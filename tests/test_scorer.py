"""Tests for the AI scoring engine."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import Deal, DealPriority, DealSource, Founder, GitHubMetrics, WebsiteSignals
from src.scoring.scorer import _parse_score_response, score_deal


class TestParseScoreResponse:
    def test_clean_json(self):
        raw = json.dumps({
            "problem_severity": 25,
            "differentiation": 20,
            "team": 18,
            "market_readiness": 15,
            "total_score": 78,
            "summary": "AI compliance tool",
            "strengths": ["Strong team", "Clear focus"],
            "red_flags": ["No pricing"],
        })
        result = _parse_score_response(raw)
        assert result is not None
        assert result["total_score"] == 78
        assert len(result["strengths"]) == 2

    def test_markdown_fenced_json(self):
        raw = """```json
{
    "problem_severity": 28,
    "differentiation": 22,
    "team": 20,
    "market_readiness": 17,
    "total_score": 87,
    "summary": "Enterprise agent orchestration",
    "strengths": ["Ex-Google founders", "SOC2 certified"],
    "red_flags": ["Crowded market"]
}
```"""
        result = _parse_score_response(raw)
        assert result is not None
        assert result["total_score"] == 87

    def test_invalid_response(self):
        result = _parse_score_response("This is not JSON at all")
        assert result is None

    def test_embedded_json(self):
        raw = "Here is my analysis: {\"total_score\": 65, \"problem_severity\": 15, \"differentiation\": 15, \"team\": 15, \"market_readiness\": 10, \"summary\": \"test\", \"strengths\": [], \"red_flags\": []} That's my assessment."
        result = _parse_score_response(raw)
        assert result is not None
        assert result["total_score"] == 65


class TestScoreDeal:
    @pytest.fixture
    def sample_deal(self):
        return Deal(
            startup_name="TestAgent",
            website="https://testagent.ai",
            description="Agentic workflow orchestration for enterprise compliance",
            founders=[
                Founder(
                    name="Alice Smith",
                    background="Ex-Google, PhD in ML",
                    notable_companies=["Google", "DeepMind"],
                    has_phd=True,
                ),
            ],
            github=GitHubMetrics(
                repo_url="https://github.com/test/agent",
                stars=800,
                star_velocity_7d=300,
                enterprise_signals=["SOC2", "SAML"],
            ),
            website_signals=WebsiteSignals(
                has_pricing=True,
                has_book_demo=True,
                has_soc2_badge=True,
                has_enterprise_tier=True,
                page_text="Enterprise compliance automation...",
            ),
            source=DealSource.GITHUB,
        )

    @pytest.mark.asyncio
    async def test_score_deal_success(self, sample_deal):
        """Test scoring with a mocked Gemini response."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "problem_severity": 28,
            "differentiation": 22,
            "team": 23,
            "market_readiness": 17,
            "total_score": 90,
            "summary": "Enterprise compliance automation with agentic AI",
            "strengths": ["PhD founders from Google/DeepMind", "SOC2 certified, live product"],
            "red_flags": ["Competitive market with established players"],
        })

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.scoring.scorer.genai.Client", return_value=mock_client):
            result = await score_deal(sample_deal)

        assert result.total_score == 90
        assert result.priority == DealPriority.HIGH
        assert len(result.strengths) == 2
        assert len(result.red_flags) == 1
        assert result.breakdown.problem_severity == 28

    @pytest.mark.asyncio
    async def test_score_deal_parse_failure(self, sample_deal):
        """Test graceful fallback when LLM returns garbage."""
        mock_response = MagicMock()
        mock_response.text = "I cannot provide a score for this startup."

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.scoring.scorer.genai.Client", return_value=mock_client):
            result = await score_deal(sample_deal)

        assert result.total_score == 0
        assert result.priority == DealPriority.LOW
        assert "manual review" in result.red_flags[0].lower()

    @pytest.mark.asyncio
    async def test_score_clamping(self, sample_deal):
        """Test that out-of-range scores get clamped."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "problem_severity": 50,  # over max of 30
            "differentiation": -5,   # below min of 0
            "team": 25,
            "market_readiness": 20,
            "total_score": 120,       # over max of 100
            "summary": "Test",
            "strengths": ["A"],
            "red_flags": ["B"],
        })

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.scoring.scorer.genai.Client", return_value=mock_client):
            result = await score_deal(sample_deal)

        assert result.breakdown.problem_severity == 30  # clamped
        assert result.breakdown.differentiation == 0     # clamped
        assert result.total_score == 100                  # clamped
