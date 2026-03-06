# OSS Integration Selection (Public Opinion / RSS)

## Candidate Repos Reviewed

1. `stay-leave/weibo-public-opinion-analysis`
2. `lzjqsdd/NewsSpider`
3. `CodeAsPoetry/PublicOpinion`

## Screening Result

- All three repos currently lack explicit `LICENSE` files.
- Action: do **not** vendor or copy their code into production paths directly.
- Safe usage: architecture/reference learning only.

## What We Reuse as Ideas (Re-implemented in our codebase)

- `weibo-public-opinion-analysis`:
  - comment/user-centric public opinion signals
  - suspicious-account detection dimensions
- `NewsSpider`:
  - source crawler + local searchable index pattern
- `PublicOpinion`:
  - pipeline segmentation (collect/clean/analyze/report)

## What We Actually Integrated

1. Strict search mode for investigation (`hot_fallback` disabled in strict path).
2. Entity gate to block unscoped evidence pollution.
3. RSS emulated search (`rss_pool.search`) + query-aware source selection.
4. RSS audit tool:
   - `scripts/audit_rss_searchability.py`
   - outputs:
     - `docs/rss_searchability_report.json`
     - `docs/rss_searchability_report.md`

## Next Engineering Steps

1. Build a persistent RSS local index (SQLite FTS5/BM25) for stable query search.
2. Route source groups by topic intent (sports, policy, finance, etc.).
3. Keep trend feeds (RSSHub) as `lead` signals, not primary evidence.
