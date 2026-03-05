#!/usr/bin/env python3
"""
Investigation quality gate runner.

Goal:
- Do not treat "pipeline runs end-to-end" as success.
- Evaluate each stage output against explicit expectations.
- Fail fast with actionable diagnostics when any stage is below target.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import httpx


def _now_ts() -> float:
    return time.time()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for row in value:
        item = str(row or "").strip()
        if item and item not in out:
            out.append(item)
    return out


@dataclass
class StageResult:
    name: str
    passed: bool
    score: float
    expected: Dict[str, Any]
    observed: Dict[str, Any]
    issues: List[str]
    elapsed_sec: float


class QualityGateRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.base_url = args.base_url.rstrip("/")
        self.api_root = f"{self.base_url}/api/v1/investigations"
        self._timeout = httpx.Timeout(
            timeout=args.http_timeout_sec,
            connect=min(8.0, args.http_timeout_sec),
        )

    async def _get_json(self, cli: httpx.AsyncClient, url: str) -> Tuple[int, Dict[str, Any]]:
        resp = await cli.get(url)
        payload = {}
        try:
            payload = resp.json()
        except Exception:
            payload = {"_raw": resp.text[:2000]}
        return resp.status_code, payload

    async def _post_json(
        self, cli: httpx.AsyncClient, url: str, payload: Dict[str, Any]
    ) -> Tuple[int, Dict[str, Any]]:
        resp = await cli.post(url, json=payload)
        body = {}
        try:
            body = resp.json()
        except Exception:
            body = {"_raw": resp.text[:2000]}
        return resp.status_code, body

    def _score_preview(self, payload: Dict[str, Any]) -> StageResult:
        started = _now_ts()
        issues: List[str] = []
        expected = {
            "status": "ready",
            "intent_summary_min_chars": self.args.preview_summary_min_chars,
            "claims_draft_min": self.args.preview_claims_min,
            "selected_platforms_min": self.args.preview_platforms_min,
            "risk_notes_min": self.args.preview_risk_notes_min,
        }

        preview_id = str(payload.get("preview_id") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        summary = str(payload.get("intent_summary") or "").strip()
        claims = payload.get("claims_draft") if isinstance(payload.get("claims_draft"), list) else []
        source_plan = payload.get("source_plan") if isinstance(payload.get("source_plan"), dict) else {}
        selected = _to_str_list(source_plan.get("selected_platforms"))
        risk_notes = _to_str_list(payload.get("risk_notes"))

        checks = {
            "preview_id_present": bool(preview_id),
            "status_ready": status == "ready",
            "summary_len_ok": len(summary) >= self.args.preview_summary_min_chars,
            "claims_min_ok": len(claims) >= self.args.preview_claims_min,
            "platforms_min_ok": len(selected) >= self.args.preview_platforms_min,
            "risk_notes_min_ok": len(risk_notes) >= self.args.preview_risk_notes_min,
        }

        if not checks["preview_id_present"]:
            issues.append("preview_id missing")
        if not checks["status_ready"]:
            issues.append(f"preview status is '{status}', expected 'ready'")
        if not checks["summary_len_ok"]:
            issues.append(
                f"intent_summary too short: {len(summary)} < {self.args.preview_summary_min_chars}"
            )
        if not checks["claims_min_ok"]:
            issues.append(f"claims_draft too few: {len(claims)} < {self.args.preview_claims_min}")
        if not checks["platforms_min_ok"]:
            issues.append(
                f"selected_platforms too few: {len(selected)} < {self.args.preview_platforms_min}"
            )
        if not checks["risk_notes_min_ok"]:
            issues.append(f"risk_notes too few: {len(risk_notes)} < {self.args.preview_risk_notes_min}")

        score = round(100.0 * (sum(1 for x in checks.values() if x) / max(1, len(checks))), 2)
        passed = bool(
            checks["preview_id_present"]
            and checks["status_ready"]
            and checks["summary_len_ok"]
            and checks["claims_min_ok"]
            and checks["platforms_min_ok"]
            and checks["risk_notes_min_ok"]
        )
        observed = {
            "preview_id": preview_id,
            "status": status,
            "intent_summary_chars": len(summary),
            "claims_draft_count": len(claims),
            "selected_platforms_count": len(selected),
            "risk_notes_count": len(risk_notes),
            "checks": checks,
        }
        return StageResult(
            name="preview_quality",
            passed=passed,
            score=score,
            expected=expected,
            observed=observed,
            issues=issues,
            elapsed_sec=round(_now_ts() - started, 3),
        )

    def _score_run_accept(self, status_code: int, payload: Dict[str, Any]) -> StageResult:
        started = _now_ts()
        issues: List[str] = []
        run_id = str(payload.get("run_id") or "").strip()
        accepted_at = str(payload.get("accepted_at") or "").strip()
        initial_status = str(payload.get("initial_status") or "").strip().lower()
        checks = {
            "status_202": status_code == 202,
            "run_id_present": bool(run_id),
            "accepted_at_present": bool(accepted_at),
            "initial_status_valid": initial_status in {"queued", "running"},
        }
        if not checks["status_202"]:
            issues.append(f"run HTTP status {status_code}, expected 202")
        if not checks["run_id_present"]:
            issues.append("run_id missing in run accepted payload")
        if not checks["accepted_at_present"]:
            issues.append("accepted_at missing in run accepted payload")
        if not checks["initial_status_valid"]:
            issues.append(f"initial_status '{initial_status}' unexpected")
        score = round(100.0 * (sum(1 for x in checks.values() if x) / len(checks)), 2)
        observed = {
            "http_status": status_code,
            "run_id": run_id,
            "accepted_at": accepted_at,
            "initial_status": initial_status,
            "checks": checks,
        }
        return StageResult(
            name="run_acceptance",
            passed=all(checks.values()),
            score=score,
            expected={"http_status": 202, "initial_status": ["queued", "running"]},
            observed=observed,
            issues=issues,
            elapsed_sec=round(_now_ts() - started, 3),
        )

    async def _collect_stream_events(
        self, cli: httpx.AsyncClient, run_id: str
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
        url = f"{self.api_root}/{run_id}/stream"
        terminal_event_types = {"run_completed", "run_failed"}
        events: List[Dict[str, Any]] = []
        terminal_type: Optional[str] = None
        terminal_status: Optional[str] = None
        started = _now_ts()

        async with cli.stream("GET", url, timeout=self.args.stream_timeout_sec + 10) as resp:
            resp.raise_for_status()
            current_event = {"id": "", "event": "", "data": ""}
            async for line in resp.aiter_lines():
                if _now_ts() - started > self.args.stream_timeout_sec:
                    break
                if line is None:
                    continue
                row = str(line).rstrip("\n")
                if not row:
                    # Flush one SSE frame
                    event_type = str(current_event.get("event") or "").strip()
                    data_text = str(current_event.get("data") or "").strip()
                    payload = {}
                    if data_text:
                        try:
                            payload = json.loads(data_text)
                        except Exception:
                            payload = {"_raw": data_text}
                    if event_type:
                        events.append(
                            {
                                "id": str(current_event.get("id") or ""),
                                "event": event_type,
                                "data": payload,
                            }
                        )
                        if event_type in terminal_event_types:
                            terminal_type = event_type
                            terminal_status = str(payload.get("status") or "").strip().lower()
                            break
                    current_event = {"id": "", "event": "", "data": ""}
                    continue

                if row.startswith("id:"):
                    current_event["id"] = row[3:].strip()
                elif row.startswith("event:"):
                    current_event["event"] = row[6:].strip()
                elif row.startswith("data:"):
                    value = row[5:].strip()
                    if current_event["data"]:
                        current_event["data"] += value
                    else:
                        current_event["data"] = value

        return events, terminal_type, terminal_status

    def _score_stream(self, events: List[Dict[str, Any]], terminal_type: Optional[str]) -> StageResult:
        started = _now_ts()
        issues: List[str] = []
        event_types = [str(e.get("event") or "") for e in events]
        step_updates = [e for e in events if str(e.get("event")) == "step_update"]
        checks = {
            "events_min_ok": len(events) >= self.args.stream_events_min,
            "step_update_seen": len(step_updates) >= self.args.stream_step_updates_min,
            "terminal_seen": bool(terminal_type),
        }
        if not checks["events_min_ok"]:
            issues.append(f"stream events too few: {len(events)} < {self.args.stream_events_min}")
        if not checks["step_update_seen"]:
            issues.append(
                f"step_update events too few: {len(step_updates)} < {self.args.stream_step_updates_min}"
            )
        if not checks["terminal_seen"]:
            issues.append("no terminal event (run_completed/run_failed) seen in stream window")
        score = round(100.0 * (sum(1 for x in checks.values() if x) / len(checks)), 2)
        return StageResult(
            name="stream_quality",
            passed=all(checks.values()),
            score=score,
            expected={
                "stream_events_min": self.args.stream_events_min,
                "step_updates_min": self.args.stream_step_updates_min,
                "terminal_event_required": True,
            },
            observed={
                "events_total": len(events),
                "step_updates": len(step_updates),
                "event_types": event_types,
                "terminal_event": terminal_type,
                "checks": checks,
            },
            issues=issues,
            elapsed_sec=round(_now_ts() - started, 3),
        )

    async def _wait_result(
        self, cli: httpx.AsyncClient, run_id: str
    ) -> Tuple[int, Dict[str, Any], bool]:
        terminal = {"completed", "insufficient_evidence", "failed", "error", "cancelled"}
        started = _now_ts()
        latest_status = 0
        latest_payload: Dict[str, Any] = {}
        while _now_ts() - started <= self.args.result_wait_timeout_sec:
            status_code, payload = await self._get_json(cli, f"{self.api_root}/{run_id}")
            latest_status = status_code
            latest_payload = payload
            run_status = str(payload.get("status") or "").strip().lower()
            # Final result response includes run_id+status and usually more sections.
            if run_status in terminal and ("acquisition_report" in payload or "steps" in payload):
                return latest_status, latest_payload, True
            await asyncio.sleep(self.args.result_poll_sec)
        return latest_status, latest_payload, False

    def _extract_platforms_with_data(self, payload: Dict[str, Any]) -> int:
        acq = payload.get("acquisition_report") if isinstance(payload.get("acquisition_report"), dict) else {}
        if isinstance(acq.get("platforms_with_data"), int):
            return int(acq["platforms_with_data"])
        search = payload.get("search") if isinstance(payload.get("search"), dict) else {}
        data = search.get("data") if isinstance(search.get("data"), dict) else {}
        if isinstance(data, dict) and data:
            count = 0
            for _, rows in data.items():
                if isinstance(rows, list) and len(rows) > 0:
                    count += 1
            return count
        return 0

    def _score_result(self, payload: Dict[str, Any], ready: bool) -> StageResult:
        started = _now_ts()
        issues: List[str] = []
        status = str(payload.get("status") or "").strip().lower()
        valid_evidence = _safe_int(payload.get("valid_evidence_count"), -1)
        if valid_evidence < 0:
            acq = payload.get("acquisition_report") if isinstance(payload.get("acquisition_report"), dict) else {}
            valid_evidence = _safe_int(acq.get("external_evidence_count"), 0)
        platforms_with_data = self._extract_platforms_with_data(payload)
        duration_sec = _safe_float(payload.get("duration_sec"), -1.0)
        claim_analysis = payload.get("claim_analysis") if isinstance(payload.get("claim_analysis"), dict) else {}
        claim_count = len(claim_analysis.get("claims") or []) if isinstance(claim_analysis.get("claims"), list) else 0
        steps = payload.get("step_summaries") if isinstance(payload.get("step_summaries"), list) else []

        checks = {
            "result_ready": bool(ready),
            "status_not_failed": status not in {"failed", "error", "cancelled", "unknown"},
            "valid_evidence_min_ok": valid_evidence >= self.args.result_valid_evidence_min,
            "platforms_with_data_min_ok": platforms_with_data >= self.args.result_platforms_with_data_min,
            "claim_analysis_present": claim_count >= self.args.result_claims_min,
            "step_summaries_present": len(steps) >= self.args.result_step_summaries_min,
            "duration_budget_ok": (duration_sec < 0) or (duration_sec <= self.args.result_duration_budget_sec),
        }
        if not checks["result_ready"]:
            issues.append("result not ready within wait timeout")
        if not checks["status_not_failed"]:
            issues.append(f"terminal status is {status}")
        if not checks["valid_evidence_min_ok"]:
            issues.append(
                f"valid_evidence_count too low: {valid_evidence} < {self.args.result_valid_evidence_min}"
            )
        if not checks["platforms_with_data_min_ok"]:
            issues.append(
                "platforms_with_data too low: "
                f"{platforms_with_data} < {self.args.result_platforms_with_data_min}"
            )
        if not checks["claim_analysis_present"]:
            issues.append(f"claim_analysis claims too few: {claim_count} < {self.args.result_claims_min}")
        if not checks["step_summaries_present"]:
            issues.append(
                f"step_summaries too few: {len(steps)} < {self.args.result_step_summaries_min}"
            )
        if not checks["duration_budget_ok"]:
            issues.append(
                f"duration budget exceeded: {duration_sec:.2f}s > {self.args.result_duration_budget_sec:.2f}s"
            )

        score = round(100.0 * (sum(1 for x in checks.values() if x) / len(checks)), 2)
        return StageResult(
            name="result_quality",
            passed=all(checks.values()),
            score=score,
            expected={
                "valid_evidence_min": self.args.result_valid_evidence_min,
                "platforms_with_data_min": self.args.result_platforms_with_data_min,
                "claims_min": self.args.result_claims_min,
                "step_summaries_min": self.args.result_step_summaries_min,
                "duration_budget_sec": self.args.result_duration_budget_sec,
            },
            observed={
                "status": status,
                "valid_evidence_count": valid_evidence,
                "platforms_with_data": platforms_with_data,
                "claims_count": claim_count,
                "step_summaries_count": len(steps),
                "duration_sec": duration_sec,
                "checks": checks,
            },
            issues=issues,
            elapsed_sec=round(_now_ts() - started, 3),
        )

    def _build_run_payload(self, preview: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        claims = preview.get("claims_draft") if isinstance(preview.get("claims_draft"), list) else []
        confirmed_claims = [str(x.get("text") or "").strip() for x in claims if str(x.get("text") or "").strip()]
        source_plan = preview.get("source_plan") if isinstance(preview.get("source_plan"), dict) else {}
        selected_platforms = _to_str_list(source_plan.get("selected_platforms"))
        target_valid = self.args.result_valid_evidence_min
        max_runtime_sec = self.args.run_max_runtime_sec
        source_strategy = "auto"
        if attempt >= 2:
            # Retry strategy: broaden source pool and give more runtime budget.
            source_strategy = "full"
            target_valid = max(10, int(self.args.result_valid_evidence_min * 0.8))
            max_runtime_sec = min(600, self.args.run_max_runtime_sec + 60 * (attempt - 1))
        return {
            "claim": self.args.claim,
            "keyword": self.args.keyword or self.args.claim[:80],
            "mode": self.args.mode,
            "source_strategy": source_strategy,
            "confirmed_preview_id": str(preview.get("preview_id") or ""),
            "confirmed_claims": confirmed_claims[:6] if confirmed_claims else [self.args.claim],
            "confirmed_platforms": selected_platforms[:10],
            "target_valid_evidence_min": target_valid,
            "min_platforms_with_data": self.args.result_platforms_with_data_min,
            "max_runtime_sec": max_runtime_sec,
            "phase1_target_valid_evidence": min(target_valid, max(20, int(target_valid * 0.6))),
            "phase1_deadline_sec": min(120, max(30, int(max_runtime_sec * 0.5))),
        }

    async def run_once(self, attempt: int) -> Dict[str, Any]:
        stages: List[StageResult] = []
        t0 = _now_ts()
        async with httpx.AsyncClient(timeout=self._timeout) as cli:
            # Stage 0: health
            s0_started = _now_ts()
            health_code, health_payload = await self._get_json(cli, f"{self.api_root}/health")
            health_ok = bool(health_code == 200 and health_payload.get("ok") is True)
            stages.append(
                StageResult(
                    name="health_check",
                    passed=health_ok,
                    score=100.0 if health_ok else 0.0,
                    expected={"http_status": 200, "ok": True},
                    observed={"http_status": health_code, "payload": health_payload},
                    issues=[] if health_ok else [f"health check failed: status={health_code}"],
                    elapsed_sec=round(_now_ts() - s0_started, 3),
                )
            )
            if not health_ok:
                return {
                    "attempt": attempt,
                    "passed": False,
                    "stages": [asdict(x) for x in stages],
                    "elapsed_sec": round(_now_ts() - t0, 3),
                }

            # Stage 1: preview
            preview_payload = {
                "claim": self.args.claim,
                "keyword": self.args.keyword or self.args.claim[:80],
                "mode": self.args.mode,
                "source_strategy": "auto",
            }
            p_code, p_body = await self._post_json(cli, f"{self.api_root}/preview", preview_payload)
            preview_stage = self._score_preview(p_body if p_code == 200 else {"status": "degraded"})
            if p_code != 200:
                preview_stage.passed = False
                preview_stage.issues.insert(0, f"preview HTTP status {p_code}, expected 200")
                preview_stage.observed["http_status"] = p_code
            stages.append(preview_stage)
            if not preview_stage.passed:
                return {
                    "attempt": attempt,
                    "passed": False,
                    "stages": [asdict(x) for x in stages],
                    "elapsed_sec": round(_now_ts() - t0, 3),
                }

            # Stage 2: run
            run_payload = self._build_run_payload(p_body, attempt)
            r_code, r_body = await self._post_json(cli, f"{self.api_root}/run", run_payload)
            run_stage = self._score_run_accept(r_code, r_body)
            stages.append(run_stage)
            if not run_stage.passed:
                return {
                    "attempt": attempt,
                    "passed": False,
                    "stages": [asdict(x) for x in stages],
                    "elapsed_sec": round(_now_ts() - t0, 3),
                }
            run_id = str(r_body.get("run_id") or "")

            # Stage 3: stream
            stream_events, terminal_type, terminal_status = await self._collect_stream_events(cli, run_id)
            stream_stage = self._score_stream(stream_events, terminal_type)
            stream_stage.observed["terminal_status"] = terminal_status
            stages.append(stream_stage)

            # Stage 4: result
            result_code, result_payload, result_ready = await self._wait_result(cli, run_id)
            result_stage = self._score_result(result_payload, result_ready)
            result_stage.observed["http_status"] = result_code
            result_stage.observed["run_id"] = run_id
            stages.append(result_stage)

        passed = all(s.passed for s in stages)
        overall_score = round(sum(s.score for s in stages) / max(1, len(stages)), 2)
        return {
            "attempt": attempt,
            "passed": passed,
            "overall_score": overall_score,
            "stages": [asdict(x) for x in stages],
            "elapsed_sec": round(_now_ts() - t0, 3),
        }

    async def run(self) -> int:
        attempts: List[Dict[str, Any]] = []
        for attempt in range(1, self.args.max_attempts + 1):
            report = await self.run_once(attempt)
            attempts.append(report)
            if report.get("passed"):
                output = {
                    "ok": True,
                    "message": "All stage gates passed.",
                    "attempts": attempts,
                }
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return 0
        output = {
            "ok": False,
            "message": "Stage gate failed. See stage issues and expected vs observed per stage.",
            "attempts": attempts,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Investigation stage quality gate runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--claim", required=True, help="Claim text to validate end-to-end")
    parser.add_argument("--keyword", default="", help="Optional keyword")
    parser.add_argument("--mode", default="dual", choices=["dual", "enhanced", "search"])
    parser.add_argument("--max-attempts", type=int, default=2, help="Retry attempts with adaptive params")
    parser.add_argument("--http-timeout-sec", type=float, default=18.0)
    parser.add_argument("--stream-timeout-sec", type=float, default=210.0)
    parser.add_argument("--result-wait-timeout-sec", type=float, default=240.0)
    parser.add_argument("--result-poll-sec", type=float, default=2.0)
    parser.add_argument("--run-max-runtime-sec", type=int, default=180)

    # Stage expectations
    parser.add_argument("--preview-summary-min-chars", type=int, default=120)
    parser.add_argument("--preview-claims-min", type=int, default=1)
    parser.add_argument("--preview-platforms-min", type=int, default=3)
    parser.add_argument("--preview-risk-notes-min", type=int, default=0)
    parser.add_argument("--stream-events-min", type=int, default=3)
    parser.add_argument("--stream-step-updates-min", type=int, default=1)
    parser.add_argument("--result-valid-evidence-min", type=int, default=20)
    parser.add_argument("--result-platforms-with-data-min", type=int, default=3)
    parser.add_argument("--result-claims-min", type=int, default=1)
    parser.add_argument("--result-step-summaries-min", type=int, default=2)
    parser.add_argument("--result-duration-budget-sec", type=float, default=240.0)
    return parser


async def _main_async() -> int:
    args = build_parser().parse_args()
    runner = QualityGateRunner(args)
    return await runner.run()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main_async()))
