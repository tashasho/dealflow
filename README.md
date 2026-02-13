# 🎯 DealFlow — Enterprise AI Deal Sourcing Pipeline

Automated pipeline that sources, scores, and surfaces seed-stage enterprise AI startups.

## Quick Start

```bash
# 1. Install
cd dealflow
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env with your GEMINI_API_KEY and SLACK_WEBHOOK_URL

# 3. Run
dealflow run --dry-run          # Test without Slack
dealflow score --url https://example-startup.ai   # Score one startup
dealflow digest --dry-run       # Weekly summary preview
dealflow list --min-score 75    # View stored deals
```

## Architecture

```
Source → Enrich → Score → Filter → Notify → Store
  │        │        │        │        │        │
  ▼        ▼        ▼        ▼        ▼        ▼
GitHub   Website  Gemini   ≥75pts   Slack    SQLite
PH       GitHub   0-100    Auto     Card
YC       Apollo/          Pass
HF       Clay
arXiv
```

## Scoring Rubric (0-100)

| Dimension | Max | What It Measures |
|-----------|-----|-----------------|
| Problem Severity | 30 | Mission-critical vs nice-to-have |
| Differentiation | 25 | Proprietary tech vs GPT wrapper |
| Team | 25 | PhDs, exits, OSS cred |
| Market Readiness | 20 | Live product vs concept stage |

## CLI Commands

| Command | Description |
|---------|-------------|
| `dealflow run` | Full pipeline (all sources) |
| `dealflow run -s github` | Single source |
| `dealflow run -s arxiv` | arXiv papers only |
| `dealflow run --dry-run` | Score without Slack |
| `dealflow score --url URL` | Score one startup |
| `dealflow digest` | Weekly summary to Slack |
| `dealflow list -m 80` | View deals ≥80 |
| `dealflow schedule` | Start auto-scheduler (Ctrl+C to stop) |
| `dealflow schedule -i 12` | Scan every 12 hours |
| `dealflow crontab` | Generate crontab entries |
| `dealflow crontab --launchd` | Generate macOS launchd plist |

## Configuration (.env)

```
GEMINI_API_KEY=...          # Required
SLACK_WEBHOOK_URL=...       # Required (or use --dry-run)
GITHUB_TOKEN=...            # Optional (higher rate limits)
SCORE_THRESHOLD=75          # Auto-pass cutoff
APOLLO_API_KEY=...          # Optional (founder enrichment)
CLAY_API_KEY=...            # Optional (fallback enrichment)
```

## Scheduling

```bash
# Option 1: Built-in scheduler (foreground process)
dealflow schedule --interval 6 --dry-run

# Option 2: System crontab
dealflow crontab              # prints crontab entries
crontab -e                     # paste the output

# Option 3: macOS launchd
dealflow crontab --launchd     # prints plist XML
```

## Tests

```bash
pytest tests/ -v
```
