# Implementation Plan - Enterprise AI Deal Flow System

The goal is to implement the "Enterprise AI Seed Deal Sourcing" system described by the user. While the user's design references **n8n orchestration**, we will implement this logic **directly in Python** within the existing `dealflow` repository to create a self-contained, robust, and cost-effective application.

## User Review Required

> [!IMPORTANT]
> **Architecture Decision**: This plan implements the workflow purely in Python (`src/pipeline.py`), replacing the proposed n8n orchestration. This leverages your existing `scheduler.py` and avoids external no-code platform costs/complexity. The "n8n nodes" from your design will be converted into Python modules.

> [!WARNING]
> **API Keys**: You will need to populate `.env` with keys for: Phantombuster, Apify, Algolia, Crunchbase, Apollo, Jina AI, Google AI Studio, and Slack.

## Proposed Changes

### Phase 1: Sourcing (Multi-Channel)

We will expand `src/sourcing/` to include all requested channels.

#### [NEW] [src/sourcing/linkedin.py](file:///Users/bhumikamarmat/dealflow/src/sourcing/linkedin.py)
- Implement Phantombuster API client to trigger and retrieve results from the 6 configured searches.

#### [NEW] [src/sourcing/twitter.py](file:///Users/bhumikamarmat/dealflow/src/sourcing/twitter.py)
- Implement Apify client for Twitter Scraper (Launch, YC, Stealth, Founder Bio).

#### [NEW] [src/sourcing/product_hunt.py](file:///Users/bhumikamarmat/dealflow/src/sourcing/product_hunt.py)
- Implement Apify client for Product Hunt Scraper (B2B/AI filters).

#### [NEW] [src/sourcing/hacker_news.py](file:///Users/bhumikamarmat/dealflow/src/sourcing/hacker_news.py)
- Implement Algolia API client for "Show HN" and "Who is Hiring".

#### [NEW] [src/sourcing/reddit.py](file:///Users/bhumikamarmat/dealflow/src/sourcing/reddit.py)
- Implement Apify client for Reddit Scraper (r/MachineLearning, r/LocalLLaMA, etc.).

#### [NEW] [src/sourcing/rss.py](file:///Users/bhumikamarmat/dealflow/src/sourcing/rss.py)
- Implement `feedparser` logic for India News (Inc42, YourStory) and Newsletters.

#### [NEW] [src/sourcing/academic.py](file:///Users/bhumikamarmat/dealflow/src/sourcing/academic.py)
- Implement arXiv API client for academic spin-outs.

### Phase 2: Aggregation & Deduplication

#### [MODIFY] [src/pipeline.py](file:///Users/bhumikamarmat/dealflow/src/pipeline.py)
- Update `run_pipeline` to:
    1.  Collect raw leads from all sources (async/parallel).
    2.  Normalize domains and LinkedIn URLs.
    3.  Generate `dedup_hash`.
    4.  Check against `src/storage/db.py` (SQLite/Airtable) to filter duplicates.

### Phase 3: Enrichment

#### [NEW] [src/enrichment/crunchbase.py](file:///Users/bhumikamarmat/dealflow/src/enrichment/crunchbase.py)
- Implement Crunchbase API lookup (Funding <$5M check).

#### [NEW] [src/enrichment/apollo.py](file:///Users/bhumikamarmat/dealflow/src/enrichment/apollo.py)
- Implement Apollo.io / Hunter.io lookup for founder emails.

#### [NEW] [src/enrichment/website.py](file:///Users/bhumikamarmat/dealflow/src/enrichment/website.py)
- Implement Jina AI Reader API to scrape landing page text.

### Phase 4: Scoring

#### [NEW] [src/scoring/gemini.py](file:///Users/bhumikamarmat/dealflow/src/scoring/gemini.py)
- Implement the "VC Analyst" prompt using Google AI Studio (Gemini) API.
- Parse JSON output for Score (0-100), Summary, Strengths, Red Flags.

### Phase 5: Distribution & Operations

#### [NEW] [src/notifications/slack_block_kit.py](file:///Users/bhumikamarmat/dealflow/src/notifications/slack_block_kit.py)
- Create block kit templates for `#deal-flow-hot` and `#deal-flow-research`.

#### [NEW] [src/storage/airtable.py](file:///Users/bhumikamarmat/dealflow/src/storage/airtable.py)
- Implement Airtable API client to sync deals, reading list, and outreach queue.

## Verification Plan

### Automated Tests
- Run `pytest` to verify individual scraper logic (mocked APIs).
- Run `python -m src.cli run --dry-run` to execute the full pipeline without posting to Slack/Airtable.

### Manual Verification
1.  **Sourcing**: Manually trigger `python -m src.cli test-source --channel github` (and others) to verify data collection.
2.  **Scoring**: Run a known startup domain through the scoring module and verify the AI output.
3.  **End-to-End**: Run the pipeline with a limited scope (GitHub only) and verify the Slack message appears in a test channel.
