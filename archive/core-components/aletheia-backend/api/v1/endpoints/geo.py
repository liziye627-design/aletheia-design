"""
GEO endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.sqlite_database import get_sqlite_db
from services.geo.geo_ai_citation_scanner import run_geo_scan
from services.geo.geo_mindmap_generator import build_geo_mindmap
from services.geo.geo_opportunity_mining_engine import build_geo_opportunities
from services.geo.geo_content_generation_engine import build_geo_content
from services.geo.geo_metrics import build_geo_metrics

router = APIRouter()


class GeoScanRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    platforms: Optional[List[str]] = None
    limit_per_platform: int = Field(default=20, ge=1, le=100)


class GeoGenerateContentRequest(BaseModel):
    opportunity_id: Optional[str] = None
    direction: Optional[str] = None


@router.post("/scan")
async def geo_scan(req: GeoScanRequest) -> Dict[str, Any]:
    try:
        scan_payload = await run_geo_scan(
            topic=req.topic,
            platforms=req.platforms,
            limit_per_platform=req.limit_per_platform,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"GEO scan failed: {exc}",
        ) from exc
    scan_id = f"geo_scan_{uuid4().hex[:10]}"
    payload = {"scan_id": scan_id, **scan_payload}
    get_sqlite_db().save_geo_scan(scan_id=scan_id, topic=req.topic, payload=payload)
    return payload


@router.get("/scan/{scan_id}")
async def geo_scan_detail(scan_id: str) -> Dict[str, Any]:
    record = get_sqlite_db().get_geo_scan(scan_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    return record.get("payload_json") or {}


@router.post("/scan/{scan_id}/mindmap")
async def geo_scan_mindmap(scan_id: str) -> Dict[str, Any]:
    record = get_sqlite_db().get_geo_scan(scan_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    payload = record.get("payload_json") or {}
    mindmap = build_geo_mindmap(payload)
    payload["mindmap"] = mindmap
    get_sqlite_db().save_geo_scan(scan_id=scan_id, topic=payload.get("topic", ""), payload=payload)
    return mindmap


@router.post("/scan/{scan_id}/opportunities")
async def geo_scan_opportunities(scan_id: str) -> Dict[str, Any]:
    record = get_sqlite_db().get_geo_scan(scan_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    payload = record.get("payload_json") or {}
    mindmap = payload.get("mindmap") or build_geo_mindmap(payload)
    opportunities_payload = build_geo_opportunities(scan_payload=payload, mindmap_payload=mindmap)
    for opp in opportunities_payload.get("opportunities", []):
        opp_id = str(opp.get("opportunity_id") or f"geo_opp_{uuid4().hex[:8]}")
        opp["opportunity_id"] = opp_id
        get_sqlite_db().save_geo_opportunities(opportunity_id=opp_id, scan_id=scan_id, payload=opp)
    return opportunities_payload


@router.post("/scan/{scan_id}/generate-content")
async def geo_scan_generate_content(scan_id: str, req: GeoGenerateContentRequest) -> Dict[str, Any]:
    opportunities = get_sqlite_db().get_geo_opportunities(scan_id)
    opportunity = None
    if req.opportunity_id:
        for row in opportunities:
            payload = row.get("payload_json") or {}
            if payload.get("opportunity_id") == req.opportunity_id:
                opportunity = payload
                break
    if not opportunity and opportunities:
        opportunity = (opportunities[0].get("payload_json") or {})
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")
    if req.direction:
        opportunity = {**opportunity, "direction": req.direction}
    content = build_geo_content(opportunity)
    content_id = f"geo_content_{uuid4().hex[:8]}"
    get_sqlite_db().save_geo_content(content_id=content_id, opportunity_id=opportunity.get("opportunity_id", ""), payload=content)
    return {"content_id": content_id, **content}


@router.post("/scan/{scan_id}/metrics")
async def geo_scan_metrics(scan_id: str) -> Dict[str, Any]:
    record = get_sqlite_db().get_geo_scan(scan_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    payload = record.get("payload_json") or {}
    topic = payload.get("topic") or "GEO主题"
    return build_geo_metrics(topic)
