"""
Evidence Search API.
证据检索 API

Implements unified Search API:
- POST /v1/search: Text search with filters and highlighting
- POST /v1/similar: Vector similarity search
- GET /v1/doc/{doc_id}: Document details with version chain
- GET /v1/hits/{query_id}: Discovery layer SearchHits

Author: Aletheia Team
"""

from dataclasses import asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
import structlog

from services.evidence import (
    SearchQuery,
    SearchResult,
    OpenSearchQueryBuilder,
    EvidenceDoc,
    SearchHit,
    VersionManager,
    EvidenceScorer,
    SourceTierResolver,
    EvidenceSearchClient,
    OpenSearchConfig,
    get_opensearch_client,
    get_metrics_collector,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/v1", tags=["evidence"])


# ============================================================
# Request/Response Models
# ============================================================

class SearchRequest(BaseModel):
    """Search request model"""
    query: str = Field(..., description="Search query text")
    fields: List[str] = Field(
        default=["title", "content_text"],
        description="Fields to search in",
    )

    # Filters
    source_domains: List[str] = Field(default=[], description="Filter by source domains")
    platforms: List[str] = Field(default=[], description="Filter by platforms")
    source_tiers: List[str] = Field(default=[], description="Filter by source tiers (S, A, B, C)")
    authors: List[str] = Field(default=[], description="Filter by authors")
    tags: List[str] = Field(default=[], description="Filter by tags")

    # Time range
    publish_time_start: Optional[str] = Field(None, description="Start of publish time range")
    publish_time_end: Optional[str] = Field(None, description="End of publish time range")
    crawl_time_start: Optional[str] = Field(None, description="Start of crawl time range")
    crawl_time_end: Optional[str] = Field(None, description="End of crawl time range")

    # Scoring
    min_evidence_score: Optional[float] = Field(None, description="Minimum evidence score")
    exclude_deleted: bool = Field(True, description="Exclude deleted documents")
    exclude_low_confidence: bool = Field(False, description="Exclude low confidence extractions")

    # Pagination
    size: int = Field(20, ge=1, le=100, description="Number of results")
    offset: int = Field(0, ge=0, description="Result offset")

    # Sorting
    sort_by: str = Field("evidence_score", description="Sort field")
    sort_order: str = Field("desc", description="Sort order (asc/desc)")

    # Highlighting
    highlight: bool = Field(True, description="Enable highlighting")
    highlight_fragment_size: int = Field(200, description="Highlight fragment size")

    # Vector search (optional)
    vector: Optional[List[float]] = Field(None, description="Query vector for hybrid search")


class SearchResponse(BaseModel):
    """Search response model"""
    total: int
    hits: List[Dict[str, Any]]
    took_ms: int
    query: Dict[str, Any]
    aggregations: Optional[Dict[str, Any]] = None


class SimilarRequest(BaseModel):
    """Similar documents request"""
    doc_id: Optional[str] = Field(None, description="Document ID to find similar documents")
    text: Optional[str] = Field(None, description="Text to find similar documents")
    vector: Optional[List[float]] = Field(None, description="Vector for similarity search")
    k: int = Field(10, ge=1, le=50, description="Number of similar documents")
    exclude_self: bool = Field(True, description="Exclude the query document from results")


class SimilarResponse(BaseModel):
    """Similar documents response"""
    query_doc_id: Optional[str]
    total: int
    hits: List[Dict[str, Any]]
    took_ms: int


class DocumentResponse(BaseModel):
    """Document detail response"""
    doc_id: str
    title: str
    content_text: Optional[str]
    canonical_url: Optional[str]
    original_url: str
    platform: str
    source_domain: str
    source_tier: str
    evidence_score: float
    publish_time: Optional[datetime]
    crawl_time: datetime
    extraction_method: str
    extraction_confidence: float

    # Version info
    version_id: str
    version_count: int
    is_latest: bool
    has_corrections: bool

    # Version chain
    version_chain: List[Dict[str, Any]]

    # Raw snapshot
    raw_snapshot_uri: Optional[str]


class HitsResponse(BaseModel):
    """Search hits response"""
    query_id: str
    query: str
    total: int
    hits: List[Dict[str, Any]]
    captured_at: datetime


class BulkIndexRequest(BaseModel):
    """Bulk index request"""
    documents: List[Dict[str, Any]] = Field(..., description="Documents to index")


class BulkIndexResponse(BaseModel):
    """Bulk index response"""
    indexed: int
    errors: List[Dict[str, Any]]


# ============================================================
# Dependencies
# ============================================================

async def get_client() -> EvidenceSearchClient:
    """Get OpenSearch client dependency"""
    return await get_opensearch_client()


# ============================================================
# API Endpoints
# ============================================================

@router.post("/search", response_model=SearchResponse)
async def search_evidence(request: SearchRequest):
    """
    Search evidence documents with full-text and filters.
    全文检索证据文档（布尔/短语/时间范围/来源过滤/高亮）

    Supports:
    - Full-text search with IK Chinese analyzer
    - Filter by source domain, platform, tier, author, tags
    - Time range filtering
    - Evidence score filtering
    - Highlighting
    - Hybrid text + vector search
    """
    try:
        client = await get_opensearch_client()

        # Build search query
        search_params = SearchQuery(
            query_text=request.query,
            query_fields=request.fields,
            source_domains=request.source_domains,
            platforms=request.platforms,
            source_tiers=request.source_tiers,
            authors=request.authors,
            tags=request.tags,
            publish_time_start=request.publish_time_start,
            publish_time_end=request.publish_time_end,
            crawl_time_start=request.crawl_time_start,
            crawl_time_end=request.crawl_time_end,
            min_evidence_score=request.min_evidence_score,
            exclude_deleted=request.exclude_deleted,
            exclude_low_confidence=request.exclude_low_confidence,
            size=request.size,
            from_=request.offset,
            sort_by=request.sort_by,
            sort_order=request.sort_order,
            highlight=request.highlight,
            highlight_fragment_size=request.highlight_fragment_size,
            vector=request.vector,
        )

        # Execute search
        result = await client.search_evidence(search_params)

        # Record metrics
        metrics = get_metrics_collector()
        metrics.record_index_operation(
            operation="search",
            success=True,
            latency_seconds=result.took_ms / 1000.0,
        )

        return SearchResponse(
            total=result.total,
            hits=result.hits,
            took_ms=result.took_ms,
            query=asdict(search_params),
            aggregations=result.aggregations,
        )

    except Exception as e:
        logger.error("search_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/similar", response_model=SimilarResponse)
async def find_similar(request: SimilarRequest):
    """
    Find similar documents using vector search.
    向量相似检索（给定 doc_id 或文本生成 embedding）

    Supports:
    - Search by document ID (uses stored embedding)
    - Search by text (generates embedding)
    - Search by vector directly
    """
    try:
        if not request.doc_id and not request.text and not request.vector:
            raise HTTPException(
                status_code=400,
                detail="Must provide doc_id, text, or vector",
            )

        client = await get_opensearch_client()

        # Get vector from document or text
        vector = request.vector
        query_doc_id = request.doc_id

        if not vector:
            if request.doc_id:
                # Fetch document and get its embedding
                doc = await client.get_evidence(request.doc_id)
                if not doc:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Document not found: {request.doc_id}",
                    )
                vector = doc.get("embedding")
                if not vector:
                    raise HTTPException(
                        status_code=400,
                        detail="Document has no embedding",
                    )
            elif request.text:
                # Generate embedding from text
                # TODO: Use embedding model (OpenAI, local, etc.)
                raise HTTPException(
                    status_code=501,
                    detail="Text embedding generation not yet implemented",
                )

        if not vector:
            raise HTTPException(
                status_code=400,
                detail="Could not determine query vector",
            )

        # Build exclusion list
        exclude_ids = [request.doc_id] if request.doc_id and request.exclude_self else []

        # Execute similar search
        hits = await client.find_similar(
            vector=vector,
            k=request.k,
            exclude_doc_ids=exclude_ids,
        )

        return SimilarResponse(
            query_doc_id=query_doc_id,
            total=len(hits),
            hits=hits,
            took_ms=0,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("similar_search_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Similar search failed: {str(e)}")


@router.get("/doc/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    include_version_chain: bool = Query(True, description="Include full version chain"),
    include_content: bool = Query(True, description="Include full content"),
):
    """
    Get evidence document details with version chain.
    证据详情（含版本链与快照 hash）

    Returns:
    - Full document details
    - Version chain history
    - Extraction metadata
    - Credibility scores
    """
    try:
        client = await get_opensearch_client()

        # Fetch document from OpenSearch
        doc = await client.get_evidence(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

        # Get version chain (TODO: integrate with VersionManager)
        version_chain = []
        if include_version_chain:
            # Placeholder for version chain
            version_chain = [
                {
                    "version_id": doc.get("version_id", f"{doc_id}:v1"),
                    "captured_at": doc.get("crawl_time", datetime.utcnow().isoformat()),
                    "change_type": "created",
                }
            ]

        return DocumentResponse(
            doc_id=doc_id,
            title=doc.get("title", ""),
            content_text=doc.get("content_text") if include_content else None,
            canonical_url=doc.get("canonical_url"),
            original_url=doc.get("original_url", ""),
            platform=doc.get("platform", ""),
            source_domain=doc.get("source_domain", ""),
            source_tier=doc.get("source_tier", "C"),
            evidence_score=doc.get("evidence_score", 0.0),
            publish_time=doc.get("publish_time"),
            crawl_time=doc.get("crawl_time", datetime.utcnow()),
            extraction_method=doc.get("extraction_method", "fallback"),
            extraction_confidence=doc.get("extraction_confidence", 0.0),
            version_id=doc.get("version_id", f"{doc_id}:v1"),
            version_count=len(version_chain),
            is_latest=True,
            has_corrections=doc.get("has_correction", False),
            version_chain=version_chain,
            raw_snapshot_uri=doc.get("raw_snapshot_uri"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_document_failed", doc_id=doc_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get document: {str(e)}")


@router.get("/hits/{query_id}", response_model=HitsResponse)
async def get_discovery_hits(
    query_id: str,
    platform: Optional[str] = Query(None, description="Filter by platform"),
    min_rank: Optional[int] = Query(None, description="Minimum rank"),
    max_rank: Optional[int] = Query(None, description="Maximum rank"),
    fetch_status: Optional[str] = Query(None, description="Filter by fetch status"),
):
    """
    Get discovery layer SearchHits.
    发现层 SearchHit（可解释"从哪个热榜/搜索发现"）

    Returns the original search result entries that led to
    evidence discovery, useful for explaining "why was this found".
    """
    try:
        client = await get_opensearch_client()

        # Fetch hits from OpenSearch
        hits = await client.get_hits_by_query(query_id)

        # Apply filters
        if platform:
            hits = [h for h in hits if h.get("platform") == platform]
        if min_rank is not None:
            hits = [h for h in hits if h.get("rank", 0) >= min_rank]
        if max_rank is not None:
            hits = [h for h in hits if h.get("rank", 0) <= max_rank]
        if fetch_status:
            hits = [h for h in hits if h.get("fetch_status") == fetch_status]

        return HitsResponse(
            query_id=query_id,
            query=query_id,  # TODO: extract actual query
            total=len(hits),
            hits=hits,
            captured_at=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_hits_failed", query_id=query_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get hits: {str(e)}")


@router.get("/stats")
async def get_evidence_stats():
    """
    Get evidence library statistics.
    获取证据库统计信息
    """
    try:
        client = await get_opensearch_client()
        stats = await client.get_stats()

        # Transform stats for response
        evidence_stats = stats.get("evidence", {})
        search_hits_stats = stats.get("search_hits", {})

        return {
            "total_documents": evidence_stats.get("document_count", 0),
            "total_versions": 0,  # TODO: aggregate from MetaDB
            "total_search_hits": search_hits_stats.get("document_count", 0),
            "by_platform": {},  # TODO: aggregate from OpenSearch
            "by_source_tier": {
                "S": 0,
                "A": 0,
                "B": 0,
                "C": 0,
            },
            "by_extraction_method": {},
            "avg_evidence_score": 0.0,
            "index_size_mb": evidence_stats.get("size_bytes", 0) / (1024 * 1024),
            "last_updated": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("get_stats_failed", error=str(e))
        # Return default stats if OpenSearch is unavailable
        return {
            "total_documents": 0,
            "total_versions": 0,
            "total_search_hits": 0,
            "by_platform": {},
            "by_source_tier": {"S": 0, "A": 0, "B": 0, "C": 0},
            "by_extraction_method": {},
            "avg_evidence_score": 0.0,
            "index_size_mb": 0,
            "last_updated": datetime.utcnow().isoformat(),
            "error": str(e),
        }


@router.post("/bulk", response_model=BulkIndexResponse)
async def bulk_index(request: BulkIndexRequest):
    """
    Bulk index evidence documents.
    批量索引证据文档
    """
    try:
        if not request.documents:
            return BulkIndexResponse(indexed=0, errors=[])

        client = await get_opensearch_client()

        # Execute bulk index
        success_count, error_count = await client.bulk_index_evidence(request.documents)

        # Record metrics
        metrics = get_metrics_collector()
        metrics.record_index_operation(
            operation="bulk",
            success=error_count == 0,
            latency_seconds=0.0,  # TODO: track actual latency
        )

        errors = []
        if error_count > 0:
            errors.append({"error_count": error_count})

        return BulkIndexResponse(
            indexed=success_count,
            errors=errors,
        )

    except Exception as e:
        logger.error("bulk_index_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Bulk index failed: {str(e)}")


@router.post("/index")
async def index_document(document: Dict[str, Any]):
    """
    Index a single evidence document.
    索引单个证据文档
    """
    try:
        client = await get_opensearch_client()

        success = await client.index_evidence(document)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to index document",
            )

        return {
            "status": "success",
            "doc_id": document.get("doc_id"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("index_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Index failed: {str(e)}")


# ============================================================
# Health Check
# ============================================================

@router.get("/health")
async def health_check():
    """Health check for evidence service"""
    try:
        client = await get_opensearch_client()
        stats = await client.get_stats()

        return {
            "status": "healthy",
            "service": "evidence",
            "opensearch": "connected",
            "document_count": stats.get("evidence", {}).get("document_count", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "evidence",
            "opensearch": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.post("/init")
async def init_indexes():
    """
    Initialize OpenSearch indexes.
    初始化 OpenSearch 索引
    """
    try:
        client = await get_opensearch_client()
        await client.ensure_indexes()

        return {
            "status": "success",
            "message": "Indexes created/verified",
            "indexes": [
                client.config.evidence_index,
                client.config.search_hits_index,
            ],
        }
    except Exception as e:
        logger.error("init_indexes_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to init indexes: {str(e)}")