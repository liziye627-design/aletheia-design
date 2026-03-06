# RSS Source Operation

## 1) Audit searchability

```bash
./venv/bin/python scripts/audit_rss_searchability.py \
  --query "苏炳添 退役" \
  --query "OpenAI" \
  --query "全国两会"
```

Outputs:
- `docs/rss_searchability_report.json`
- `docs/rss_searchability_report.md`

## 2) Build production shortlist

```bash
./venv/bin/python scripts/build_searchable_sources.py \
  --audit docs/rss_searchability_report.json \
  --out config/sources.searchable.yaml
```

## 3) Enable shortlist in runtime

Use either:

- Replace primary source path in `.env`:
  - `RSS_SOURCES_CONFIG_PATH=config/sources.searchable.yaml`

or

- Keep primary and append shortlist:
  - `RSS_SOURCES_CONFIG_EXTRA_PATHS=config/sources.searchable.yaml`

For strict quality, prefer replacing primary path.

## 4) Give RSS sources keyword-search capability (local index)

RSS feeds often have no native search endpoint. We now support local keyword search
against historical ingested `rss_articles` records.

1. Keep ingestion running (so the local index has data):

```bash
./venv/bin/python scripts/run_rss_pipeline.py
```

2. Query local RSS search API:

```bash
curl "http://127.0.0.1:8000/api/v1/rss/articles/search?keyword=%E8%8B%8F%E7%82%B3%E6%B7%BB%20%E9%80%80%E5%BD%B9&limit=20&days=30"
```

3. Relevant settings in `.env`:

- `RSS_POOL_ENABLE_LOCAL_INDEX_SEARCH=true`
- `RSS_POOL_LOCAL_INDEX_LOOKBACK_DAYS=30`
- `RSS_POOL_LOCAL_INDEX_MAX_CANDIDATES=120`

## 5) Build trusted crawler platform whitelist from health report

```bash
PYTHONPATH=. ./venv/bin/python scripts/build_trusted_platforms_from_health.py \
  --in docs/source-health-report-strict.json \
  --out config/trusted_platforms.auto.json \
  --min-success 0.34 \
  --require-items
```

Then copy the printed `env` value into `.env`:

- `INVESTIGATION_TRUSTED_PLATFORMS=...`
