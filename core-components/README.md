# Aletheia Core Components Bundle

This folder groups the core code modules into one place for easier delivery and GitHub review.

## Included modules
- `aletheia-backend/` (FastAPI backend and crawler/reasoning services)
- `aletheia-mobile/` (Expo/React Native app)
- `frontend/` (Web frontend)
- `aletheia-ui.pen` (UI design source)
- `README.project.md` (copied from project root README)

## Packaging rules
The bundle excludes local/runtime artifacts:
- Python caches and virtual envs: `__pycache__/`, `*.pyc`, `venv/`
- JS build/runtime caches: `node_modules/`, `.expo/`, `dist/`, `build/`, `.next/`, `.cache/`
- Runtime logs: `logs/`

## Source
Generated from `/home/llwxy/aletheia/design`.
