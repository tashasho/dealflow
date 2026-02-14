# Enterprise AI Deal Flow System - Walkthrough

This document outlines the implemented **Enterprise AI Deal Flow System**, a fully automated pipeline for sourcing, enriching, scoring, and distributing early-stage AI deals.

## System Architecture

The system runs as a Python application (`src/pipeline.py`) that orchestrates the following flow:

1.  **Sourcing**: Aggregates leads from 10+ channels.
    -   **GitHub**: Trending repos (Stars > 50, newly created) via `github_trending` and `github_search`.
    -   **LinkedIn**: Phantombuster integration for targeted search exports.
    -   **Twitter/X**: Apify scraper for launch announcements.
    -   **Product Hunt**: Apify scraper for "Launch Day" products.
    -   **Hacker News**: Algolia API for "Show HN".
    -   **Reddit**: Apify scraper for ML/LocalLLaMA subreddits.
    -   **Academic**: arXiv API for new AI research papers.
    -   **RSS**: Feedparser for India Tech news and newsletters.

2.  **Deduplication**: Filters duplicate startups based on name and source URL.

3.  **Enrichment**:
    -   **Website**: Jina AI Reader to extract landing page text (Pricing, SOC2, Enterprise tier traces).
    -   **Crunchbase**: Checks funding status (filtering for <$5M).
    -   **Apollo/Hunter**: Enriches founder contact info (emails).
    -   **GitHub**: Fetches deep metrics (Star velocity, contributors).

4.  **AI Scoring**:
    -   Uses **Google Gemini** (via `google-genai` SDK) to score deals 0-100.
    -   Rubric: Problem Severity (30), Differentiation (25), Team (25), Market Readiness (20).
    -   Outputs structured JSON with summary, strengths, and red flags.

5.  **Distribution**:
    -   **Slack**: Posts "High Signal" (Score >= 85) and "Worth Watching" deals to configured channels using Block Kit cards.
    -   **Interactive Triage**: "Add to Pipeline", "Research", and "Pass" buttons.

6.  **Storage**:
    -   **SQLite**: Local cache for all deals and scores (`data/deals.db`).
    -   **Airtable**: Syncs high-priority deals for operational management.

## Setup & Configuration

1.  **Environment Variables**:
    Ensure `.env` is populated with the following keys:
    ```bash
    GEMINI_API_KEY=...
    SLACK_WEBHOOK_URL=...
    PHANTOMBUSTER_API_KEY=...
    APIFY_TOKEN=...
    CRUNCHBASE_API_KEY=...
    APOLLO_API_KEY=...
    AIRTABLE_API_KEY=...
    AIRTABLE_BASE_ID=...
    ```

2.  **Dependencies**:
    Running `pip install -r requirements.txt` (ensure `google-genai`, `apify-client`, `feedparser`, `arxiv`, `httpx`, `pydantic`, `rich` are included).

## Usage

### Run the Pipeline (Dry Run)
Test the flow without posting to Slack/Airtable:
```bash
python -m src.cli run --dry-run
```

### Run for Real
Execute the full pipeline (best ran via cron at 7:00 AM PT):
```bash
python -m src.cli run
```

### Test Specific Source
Debug a single channel (e.g., GitHub):
```bash
python -m src.cli test-source --channel github
```

## Maintenance
-   **New Sources**: Add modules in `src/sourcing/` and update `SOURCE_MAP` in `src/pipeline.py`.
-   **Scoring Logic**: Update `SCORECARD_PROMPT` in `src/scoring/scorer.py`.
