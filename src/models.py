"""Pydantic data models for the deal flow pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DealSource(str, Enum):
    GITHUB = "github"
    PRODUCT_HUNT = "product_hunt"
    YC = "yc"
    HUGGINGFACE = "huggingface"
    ARXIV = "arxiv"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    HACKER_NEWS = "hacker_news"
    REDDIT = "reddit"
    RSS = "rss"
    MANUAL = "manual"


class DealPriority(str, Enum):
    HIGH = "high"          # score >= 85
    WORTH_WATCHING = "worth_watching"  # 75 <= score < 85
    LOW = "low"            # score < 75


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class Founder(BaseModel):
    name: str
    linkedin_url: Optional[str] = None
    background: Optional[str] = None
    notable_companies: list[str] = Field(default_factory=list)
    has_phd: bool = False
    has_exits: bool = False
    oss_contributions: Optional[str] = None


class GitHubMetrics(BaseModel):
    repo_url: str
    stars: int = 0
    star_velocity_7d: int = 0  # stars gained in last 7 days
    contributors: int = 0
    open_issues: int = 0
    enterprise_signals: list[str] = Field(default_factory=list)
    # e.g. ["SAML", "SOC2", "on-prem", "RBAC"]
    readme_snippet: Optional[str] = None


class WebsiteSignals(BaseModel):
    has_pricing: bool = False
    has_book_demo: bool = False
    has_soc2_badge: bool = False
    has_enterprise_tier: bool = False
    page_text: str = ""  # extracted text for LLM scoring


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------

class Deal(BaseModel):
    """A raw deal before scoring."""
    startup_name: str
    website: Optional[str] = None
    description: str = ""
    founders: list[Founder] = Field(default_factory=list)
    github: Optional[GitHubMetrics] = None
    website_signals: Optional[WebsiteSignals] = None
    source: DealSource = DealSource.MANUAL
    source_url: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Enrichment Fields
    funding_raised: Optional[float] = None  # in USD
    funding_stage: Optional[str] = None
    employee_count: Optional[str] = None
    hq_location: Optional[str] = None
    
    # Triage Fields
    triage_status: str = "New" # "New", "Interesting", "Pass", "Reach Out"
    triaged_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    slack_ts: Optional[str] = None # Slack message timestamp for threading


class ScoreBreakdown(BaseModel):
    """Maps to the 4-dimension scorecard."""
    problem_severity: int = Field(ge=0, le=30, default=0)
    differentiation: int = Field(ge=0, le=25, default=0)
    team: int = Field(ge=0, le=25, default=0)
    market_readiness: int = Field(ge=0, le=20, default=0)

    @property
    def total(self) -> int:
        return (
            self.problem_severity
            + self.differentiation
            + self.team
            + self.market_readiness
        )


class ScoredDeal(BaseModel):
    """A deal after AI scoring."""
    deal: Deal
    total_score: int = Field(ge=0, le=100)
    breakdown: ScoreBreakdown
    summary: str = ""           # one-line summary
    strengths: list[str] = Field(default_factory=list)   # top 2
    red_flags: list[str] = Field(default_factory=list)    # top 1+
    priority: DealPriority = DealPriority.LOW
    scored_at: datetime = Field(default_factory=datetime.utcnow)

    def classify(self) -> DealPriority:
        if self.total_score >= 85:
            return DealPriority.HIGH
        elif self.total_score >= 75:
            return DealPriority.WORTH_WATCHING
        return DealPriority.LOW


class WeeklyDigest(BaseModel):
    """Monday morning summary for the partnership."""
    week_start: datetime
    week_end: datetime
    total_reviewed: int = 0
    high_priority: int = 0      # >= 85
    worth_watching: int = 0     # 75-84
    auto_filtered: int = 0      # < 75
    top_deals: list[ScoredDeal] = Field(default_factory=list)
