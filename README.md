# blogs

Modular paper / research digest pipeline.

## Layout

```
blogs/
├── README.md
├── source.md
├── scripts/                                 ← code
│   ├── fetch.py                             # orchestrator (auto-discovers pipelines)
│   ├── common.py                            # shared: HTTP, seen state, output writer
│   ├── filters.json                         # config (used by hf-papers-weekly only)
│   └── pipelines/
│       ├── __init__.py
│       ├── hf_vendor_daily.py               # pipeline: 7 vendor HF orgs, daily
│       └── hf_papers_weekly.py              # pipeline: HF Daily Papers, weekly
├── .github/workflows/
│   └── daily-papers.yml
├── .state/                                  ← per-pipeline dedup state
│   ├── hf-vendor-daily.json
│   └── hf-papers-weekly.json
├── daily/<pipeline-name>/YYYY-MM-DD.md      ← daily output
└── weekly/<pipeline-name>/YYYY-MM-DD.md     ← weekly output
```

## Adding a new source

1. Drop a new file under `scripts/pipelines/` (e.g. `openai_news_daily.py`)
2. Implement the contract:
   ```python
   NAME = "openai-news-daily"
   SCHEDULE = "daily"        # "daily" | "weekly"

   def run(today: str, seen: dict) -> tuple[str, int]:
       # ... fetch, render markdown ...
       return md, new_count
   ```
3. Done. Orchestrator auto-discovers it; output lands in `daily/openai-news-daily/`.
   No changes needed to `fetch.py`, workflow, or any other pipeline.

## Existing pipelines

### `hf-vendor-daily` (daily)
Scans 7 vendor HF orgs for new papers today:

| Vendor | HF org slug |
|---|---|
| DeepSeek | `deepseek-ai` |
| Qwen (Alibaba) | `Qwen` |
| Kimi (Moonshot) | `moonshotai` |
| Zhipu / GLM | `zai-org` |
| Zhipu / THUDM | `THUDM` |
| MiniMax | `MiniMaxAI` |
| ByteDance Seed | `ByteDance-Seed` |

No filtering — vendors are always included.

### `hf-papers-weekly` (weekly)
Scans past 7 days of HuggingFace Daily Papers, applies `scripts/filters.json`,
keeps papers with upvotes ≥ 50 (or VIP-org bypass via `always_include_orgs`).

## `filters.json` (used only by `hf-papers-weekly`)

| Field | Purpose |
|---|---|
| `min_upvotes` | upvote threshold (AND) |
| `top_n` | keep top N after sorting (currently advisory, weekly applies its own threshold) |
| `organizations` | author-org allowlist (OR, substring) |
| `submitters` | HF submitter username (OR) |
| `authors` | author name (OR, substring) |
| `keywords` | keyword match against ai_keywords/title/summary (OR) |
| `always_include_orgs` | VIP vendors that **bypass** the upvote floor |

## Dedup

Per-pipeline state in `.state/<pipeline-name>.json`. 🆕 = first-seen on this date.

## Local run

```bash
python3 scripts/fetch.py                       # all daily pipelines
python3 scripts/fetch.py daily                 # all daily pipelines
python3 scripts/fetch.py weekly                # all weekly pipelines
python3 scripts/fetch.py both                  # everything
python3 scripts/fetch.py hf-vendor-daily       # one specific pipeline
```

## Triggers

- **Auto daily**: every day @ 01:07 UTC (≈09:07 Beijing)
- **Auto weekly**: every Friday @ 01:23 UTC (≈09:23 Beijing)
- **Manual**: repo Actions → "Papers Digest" → enter `daily` / `weekly` / `both` / pipeline name

## TODO

- ⏳ OpenAI research + news (no official RSS — needs HTML scraper)
- ⏳ Anthropic research (same)
- ⏳ LLM scoring layer (Claude Haiku for "0–10 relevance + one-liner")
