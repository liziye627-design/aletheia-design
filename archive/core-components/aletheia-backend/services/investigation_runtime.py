"""
Investigation 运行态管理器（run 存储、事件流、持久化）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import uuid4

from core.config import settings
from core.sqlite_database import get_sqlite_db
from services.investigation_helpers import TERMINAL_STATUSES, _utc_now
from utils.logging import logger


class InvestigationRunManager:
    """运行态管理：内存状态 + 事件流 + SQLite 持久化"""

    def __init__(self) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._previews: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, asyncio.Condition] = {}
        self._global_lock = asyncio.Lock()
        self._max_events_per_run = 3000
        self._preview_ttl_minutes = max(
            1, int(getattr(settings, "INVESTIGATION_PREVIEW_TTL_MINUTES", 30))
        )
        self._preview_metrics: Dict[str, int] = {
            "preview_request_count": 0,
            "preview_degraded_count": 0,
            "preview_confirm_count": 0,
            "run_after_preview_count": 0,
            "run_after_preview_success_count": 0,
        }

    async def create_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self._global_lock:
            run_id = f"run_{uuid4().hex[:12]}"
            now = _utc_now()
            run = {
                "run_id": run_id,
                "status": "queued",
                "accepted_at": now,
                "updated_at": now,
                "request": payload,
                "steps": [],
                "events": [],
                "result": None,
                "error": None,
            }
            self._runs[run_id] = run
            self._locks[run_id] = asyncio.Condition()
            self._persist(run_id)
            return run

    def _purge_expired_previews(self) -> None:
        now_ts = datetime.utcnow().timestamp()
        expired = []
        for preview_id, row in (self._previews or {}).items():
            if float(row.get("expires_at_ts") or 0.0) <= now_ts:
                expired.append(preview_id)
        for preview_id in expired:
            self._previews.pop(preview_id, None)

    async def create_preview(
        self,
        *,
        payload: Dict[str, Any],
        preview_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        async with self._global_lock:
            self._purge_expired_previews()
            preview_id = f"preview_{uuid4().hex[:12]}"
            now_dt = datetime.utcnow()
            now = _utc_now()
            expires_dt = now_dt + timedelta(minutes=self._preview_ttl_minutes)
            record = {
                "preview_id": preview_id,
                "status": str(preview_result.get("status") or "ready"),
                "created_at": now,
                "expires_at": expires_dt.isoformat(),
                "expires_at_ts": expires_dt.timestamp(),
                "request": payload,
                "result": preview_result,
            }
            self._previews[preview_id] = record
            self._preview_metrics["preview_request_count"] += 1
            if str(record["status"]).lower() == "degraded":
                self._preview_metrics["preview_degraded_count"] += 1
            return record

    def get_preview(self, preview_id: str) -> Optional[Dict[str, Any]]:
        self._purge_expired_previews()
        row = self._previews.get(preview_id)
        if not row:
            return None
        if float(row.get("expires_at_ts") or 0.0) <= datetime.utcnow().timestamp():
            self._previews.pop(preview_id, None)
            return None
        return row

    def mark_preview_confirmed(self, preview_id: str) -> None:
        row = self.get_preview(preview_id)
        if not row:
            return
        row["confirmed_at"] = _utc_now()
        self._preview_metrics["preview_confirm_count"] += 1

    async def append_event(
        self, run_id: str, event_type: str, payload: Dict[str, Any]
    ) -> None:
        run = self._runs.get(run_id)
        if not run:
            return
        event = {
            "id": f"{run_id}_{len(run['events'])+1}",
            "type": event_type,
            "ts": _utc_now(),
            "payload": payload,
        }
        run["events"].append(event)
        if len(run["events"]) > self._max_events_per_run:
            run["events"] = run["events"][-self._max_events_per_run :]
        if event_type == "step_update":
            self._upsert_step_snapshot(run, payload)
        run["updated_at"] = event["ts"]
        self._persist(run_id)
        await self._notify(run_id)

    async def set_status(self, run_id: str, status: str, error: Optional[str] = None):
        run = self._runs.get(run_id)
        if not run:
            return
        run["status"] = status
        run["updated_at"] = _utc_now()
        run["error"] = error
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        has_preview = bool(request.get("preview_context"))
        already_marked = bool(run.get("_preview_metrics_marked"))
        if has_preview and not already_marked and status in TERMINAL_STATUSES:
            run["_preview_metrics_marked"] = True
            self._preview_metrics["run_after_preview_count"] += 1
            if str(status).lower() not in {"failed", "error"}:
                self._preview_metrics["run_after_preview_success_count"] += 1
        self._persist(run_id)
        await self._notify(run_id)

    async def set_result(self, run_id: str, result: Dict[str, Any], status: str):
        run = self._runs.get(run_id)
        if not run:
            return
        run["result"] = result
        run["steps"] = list(result.get("steps") or run.get("steps") or [])
        run["status"] = status
        run["updated_at"] = _utc_now()
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        has_preview = bool(request.get("preview_context"))
        already_marked = bool(run.get("_preview_metrics_marked"))
        if has_preview and not already_marked:
            run["_preview_metrics_marked"] = True
            self._preview_metrics["run_after_preview_count"] += 1
            if str(status).lower() not in {"failed", "error"}:
                self._preview_metrics["run_after_preview_success_count"] += 1
        self._persist(run_id)
        await self._notify(run_id)

    def get_preview_metrics(self) -> Dict[str, Any]:
        req = int(self._preview_metrics.get("preview_request_count") or 0)
        confirmed = int(self._preview_metrics.get("preview_confirm_count") or 0)
        run_after = int(self._preview_metrics.get("run_after_preview_count") or 0)
        run_after_success = int(
            self._preview_metrics.get("run_after_preview_success_count") or 0
        )
        return {
            **self._preview_metrics,
            "preview_confirm_rate": round(confirmed / max(1, req), 4),
            "preview_to_run_dropoff_rate": round(
                max(0.0, 1.0 - (confirmed / max(1, req))), 4
            ),
            "run_after_preview_success_rate": round(
                run_after_success / max(1, run_after), 4
            ),
            "active_preview_count": len(self._previews),
        }

    def _upsert_step_snapshot(self, run: Dict[str, Any], payload: Dict[str, Any]) -> None:
        step_id = str(payload.get("step_id") or "").strip()
        if not step_id:
            return

        steps = run.setdefault("steps", [])
        for item in steps:
            if item.get("id") == step_id:
                item.update(payload)
                return
        steps.append(dict(payload))

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        run = self._runs.get(run_id)
        if run:
            return run

        # 兜底从 SQLite 读取
        db = get_sqlite_db()
        saved = db.get_investigation_run(run_id)
        if not saved:
            return None
        payload = saved.get("payload_json") or {}
        return {
            "run_id": run_id,
            "status": saved.get("status", "unknown"),
            "accepted_at": saved.get("created_at"),
            "updated_at": saved.get("updated_at"),
            "request": payload.get("request", {}),
            "steps": payload.get("steps", []),
            "events": payload.get("events", []),
            "result": payload.get("result"),
            "error": payload.get("error"),
        }

    async def stream(self, run_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        cursor = 0
        heartbeat_at = 0.0
        while True:
            run = self._runs.get(run_id)
            use_db_polling = False
            if not run:
                saved = get_sqlite_db().get_investigation_run(run_id)
                if not saved:
                    break
                payload = saved.get("payload_json") or {}
                run = {
                    "run_id": run_id,
                    "status": saved.get("status", "unknown"),
                    "events": payload.get("events", []),
                }
                use_db_polling = True

            events = run.get("events", [])
            while cursor < len(events):
                yield events[cursor]
                cursor += 1

            if run.get("status") in TERMINAL_STATUSES and cursor >= len(events):
                break

            # 心跳，避免代理超时
            now = datetime.utcnow().timestamp()
            if now - heartbeat_at > 12:
                heartbeat_at = now
                yield {
                    "id": f"{run_id}_heartbeat_{int(now)}",
                    "type": "heartbeat",
                    "ts": _utc_now(),
                    "payload": {"status": run.get("status")},
                }

            if use_db_polling:
                await asyncio.sleep(1.0)
                continue

            lock = self._locks.get(run_id)
            if lock is None:
                await asyncio.sleep(0.2)
                continue
            try:
                async with lock:
                    await asyncio.wait_for(lock.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    async def _notify(self, run_id: str):
        lock = self._locks.get(run_id)
        if lock is None:
            return
        async with lock:
            lock.notify_all()

    def _persist(self, run_id: str):
        run = self._runs.get(run_id)
        if not run:
            return
        try:
            get_sqlite_db().save_investigation_run(
                run_id=run_id,
                status=run.get("status", "unknown"),
                payload={
                    "request": run.get("request", {}),
                    "steps": run.get("steps", []),
                    "events": run.get("events", []),
                    "result": run.get("result"),
                    "error": run.get("error"),
                },
            )
        except Exception as exc:
            logger.warning(f"persist run failed: {exc}")
