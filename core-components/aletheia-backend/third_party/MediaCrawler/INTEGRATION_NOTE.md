# MediaCrawler Embedded Core

This directory vendors the core runtime files from `MediaCrawler` so the backend
can auto-start the sidecar without requiring a sibling `../MediaCrawler` folder.

Included:
- API server/runtime (`api/`, `main.py`, crawler modules and configs)
- Platform crawlers and shared utility modules required by `uv run main.py`

Excluded on purpose:
- local runtime state (`browser_data/`, `logs/`, `data/`)
- local virtual environments and caches (`.venv/`, `__pycache__/`)
- tests/docs and unrelated development artifacts

License and usage constraints of upstream MediaCrawler still apply
(non-commercial learning use).
