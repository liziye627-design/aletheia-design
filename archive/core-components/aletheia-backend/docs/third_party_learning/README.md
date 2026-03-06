# Third-Party Learning Notes (No Direct Code Vendoring)

This folder keeps architecture and method learnings from external repositories.
To keep the backend lightweight and license-safe, snapshot source trees were removed.
Only learning notes are retained.

## Repositories reviewed

- https://github.com/stay-leave/weibo-public-opinion-analysis
- https://github.com/lzjqsdd/NewsSpider
- https://github.com/CodeAsPoetry/PublicOpinion
- https://github.com/NanmiCoder/MediaCrawler

## Reusable strengths extracted

- `weibo-public-opinion-analysis`
  - comment/user oriented behavior signals
  - suspicious account scoring dimensions
  - sentiment + topic + trend pipeline separation
- `NewsSpider`
  - "discovery -> crawl -> local index -> search"闭环
  - list-page incremental fetch + structured parsing
- `PublicOpinion`
  - collect -> clean -> analyze -> report 分层流程
  - data cleaning and reproducible analysis pipeline
- `MediaCrawler`
  - multi-platform adapter abstraction
  - account/session pool and sidecar execution mode
  - platform-specific parser normalization

## Mapped implementation in this codebase

- Crawl orchestration and platform adapters:
  - `services/layer1_perception/crawler_manager.py`
  - `services/layer1_perception/crawlers/*`
- Sidecar integration (optional):
  - `services/external/mediacrawler_client.py`
  - `services/external/mediacrawler_process.py`
- Searchable evidence pipeline:
  - `services/investigation_engine.py`
  - `services/rss_sources_config.py`
  - `services/search_sources_config.py`
  - `services/news_indexer/*`
- Comment and risk signals:
  - `services/comments/comment_discovery.py`
  - `services/comments/comment_fetcher.py`
  - `services/comments/spam_scorer.py`
  - `services/opinion_monitoring.py`
