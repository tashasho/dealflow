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

## Sourcing — 5 Data Channels

### 🐙 GitHub Trending (`-s github`)
Scrapes [GitHub Trending](https://github.com/trending) for repos matching enterprise AI keywords, then enriches each with API data.

- **Keywords tracked**: `enterprise`, `saas`, `b2b`, `workflow`, `automation`, `compliance`, `security`, `rag`, `agent`, `llm`, `fine-tun`, `mlops`, `data-pipeline`, `vector`, `embedding`
- **Enterprise signals detected in README**: SAML, SSO, SOC2, RBAC, on-premise, audit log, role-based
- **Metrics collected**: star count, 7-day star velocity, contributor count, open issues
- **Filter**: repos must match ≥1 keyword AND have enterprise signal or >100 stars

### 🚀 Product Hunt (`-s product_hunt`)
Queries the [Product Hunt GraphQL API](https://api.producthunt.com/v2/api/graphql) for recent B2B AI launches.

- **Search terms**: `AI B2B`, `enterprise AI`, `AI workflow`, `AI automation`, `AI security`, `AI compliance`
- **Filter**: minimum 10 upvotes + description must contain AI/ML keywords
- **Data extracted**: product name, tagline, website, maker info, upvote count

### 🟠 Y Combinator (`-s yc`)
Fetches the latest [YC company directory](https://www.ycombinator.com/companies) and filters for AI + B2B startups.

- **Filter criteria**: company must be tagged with both AI-related AND B2B/enterprise verticals
- **Live probe**: checks each company's website for live product signals (pricing pages, demo CTAs, login portals)
- **Data extracted**: company name, one-liner, batch, website, team size

### 🤗 HuggingFace (`-s huggingface`)
Monitors [HuggingFace](https://huggingface.co) for organizations publishing high-traction models and enterprise-focused datasets.

- **Model tracking**: organizations with trending models sorted by download count
- **Enterprise dataset keywords**: `enterprise`, `business`, `finance`, `legal`, `medical`, `compliance`, `security`
- **Filter**: organizations with >10K model downloads or enterprise-tagged datasets
- **Data extracted**: org name, top model names, download counts, dataset descriptions

### 📄 arXiv Research (`-s arxiv`)
Searches the [arXiv API](https://arxiv.org/help/api) for enterprise AI research papers — useful for spotting founders-in-waiting.

- **Research topics monitored**:
  - Enterprise RAG architectures (retrieval augmented generation)
  - Agentic workflow orchestration (multi-agent systems, tool use)
  - Privacy-preserving ML (federated learning, differential privacy)
  - Enterprise AI deployment and production systems
- **Tracked labs**: Stanford HAI, MIT CSAIL, CMU, UC Berkeley, Google Research, DeepMind, Meta FAIR, OpenAI, Anthropic, Microsoft Research
- **Enterprise filter**: papers must contain ≥2 enterprise signals (e.g., "production", "deployment", "compliance", "scalab")
- **Data extracted**: paper title, abstract, author list with affiliations, arXiv categories

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
