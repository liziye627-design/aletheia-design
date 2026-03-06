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

from services.evidence.opensearch_config import (
    SearchQuery,
    OpenSearchQueryBuilder,
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
    publish_time_start: Optional[str] = Field(None, description="Start of publish time range (ISO format)")
    publish_time_end: Optional[str] = Field(None, description="End of publish time range (ISO format)")
    crawl_time_start: Optional[str] = Field(None, description="Start of crawl time range")
    crawl_time_end: Optional[str] = Field(None, description="End of crawl time range")

    # Scoring
    min_evidence_score: Optional[float] = Field(None, ge=0, le=1, description="Minimum evidence score")
    exclude_deleted: bool = Field(True, description="Exclude deleted documents")
    exclude_low_confidence: bool = Field(False, description="Exclude low extraction confidence")

    # Pagination
    size: int = Field(20, ge=1, le=100, description="Number of results")
    offset: int = Field(0, ge=0, description="Result offset")

    # Sorting
    sort_by: str = Field("evidence_score", description="Sort field")
    sort_order: str = Field("desc", description="Sort order (asc/desc)")

    # Highlighting
    highlight: bool = Field(True, description="Enable highlighting")
    highlight_fragment_size: int = Field(200, description="Highlight fragment size")


class SimilarRequest(BaseModel):
    """Similar documents search request"""
    doc_id: Optional[str] = Field(None, description="Document ID to find similar to")
    text: Optional[str] = Field(None, description="Text to find similar documents")
    vector: Optional[List[float]] = Field(None, description="Embedding vector")
    k: int = Field(10, ge=1, le=50, description="Number of similar documents")
    exclude_self: bool = Field(True, description="Exclude the source document")


class SearchResponse(BaseModel):
    """Search response model"""
    total: int = Field(..., description="Total number of matching documents")
    took_ms: int = Field(..., description="Query execution time in milliseconds")
    hits: List[Dict[str, Any]] = Field(..., description="Search results")
    query: Dict[str, Any] = Field(..., description="Original query parameters")
    aggregations: Optional[Dict[str, Any]] = Field(None, description="Aggregation results")


class DocumentResponse(BaseModel):
    """Document detail response"""
    doc_id: str
    title: str
    content_text: Optional[str] = None
    content_html: Optional[str] = None
    canonical_url: Optional[str] = None
    original_url: str
    publish_time: Optional[str] = None
    author: Optional[str] = None
    source_domain: str
    platform: str
    source_tier: str
    evidence_score: float
    credibility_level: str
    extraction_method: str
    extraction_confidence: float
    crawl_time: str
    version_info: Dict[str, Any]
    related_hits: List[Dict[str, Any]] = []


class VersionChainResponse(BaseModel):
    """Version chain response"""
    doc_id: str
    current_version_id: str
    version_count: int
    versions: List[Dict[str, Any]]


# ============================================================
# API Endpoints
# ============================================================

@router.post("/search", response_model=SearchResponse)
async def search_evidence(request: SearchRequest):
    """
    Search evidence documents.
    搜索证据文档

    Supports:
    - Full-text search with IK Chinese analyzer
    - Boolean filters (source, platform, tier, author, tags)
    - Time range filters
    - Evidence score filtering
    - Highlighting
    - Pagination and sorting
    """
    # Build search query
    search_query = SearchQuery(
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
    )

    builder = OpenSearchQueryBuilder()
    dsl = builder.build_search_query(search_query)

    # In production, execute against OpenSearch
    # For now, return mock response
    mock_response = {
        "total": 0,
        "took_ms": 5,
        "hits": [],
        "query": {
            "dsl": dsl,
            "params": request.model_dump(),
        },
    }

    return SearchResponse(**mock_response)


@router.post("/similar", response_model=SearchResponse)
async def find_similar(request: SimilarRequest):
    """
    Find similar documents using vector search.
    使用向量搜索查找相似文档

    Supports:
    - Search by document ID
    - Search by text (will be embedded)
    - Search by pre-computed vector
    """
    if not request.doc_id and not request.text and not request.vector:
        raise HTTPException(
            status_code=400,
            detail="Must provide doc_id, text, or vector",
        )

    builder = OpenSearchQueryBuilder()

    # In production:
    # 1. If doc_id provided, fetch document and its embedding
    # 2. If text provided, compute embedding
    # 3. Build and execute k-NN query

    exclude_ids = []
    if request.exclude_self and request.doc_id:
        exclude_ids = [request.doc_id]

    dsl = builder.build_similar_query(
        vector=request.vector or [0.0] * 1024,  # Mock vector
        k=request.k,
        exclude_doc_ids=exclude_ids,
    )

    mock_response = {
        "total": 0,
        "took_ms": 10,
        "hits": [],
        "query": {
            "dsl": dsl,
            "params": request.model_dump(),
        },
    }

    return SearchResponse(**mock_response)


@router.get("/doc/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str):
    """
    Get evidence document by ID.
    根据 ID 获取证据文档

    Returns:
    - Full document content
    - Version information
    - Related discovery hits
    """
    # In production, fetch from OpenSearch and database
    mock_doc = {
        "doc_id": doc_id,
        "title": "示例文档标题",
        "content_text": "示例文档内容...",
        "content_html": None,
        "canonical_url": "https://example.com/article/123",
        "original_url": "https://example.com/article/123",
        "publish_time": datetime.utcnow().isoformat(),
        "author": "作者名",
        "source_domain": "example.com",
        "platform": "example",
        "source_tier": "A",
        "evidence_score": 0.85,
        "credibility_level": "HIGH",
        "extraction_method": "template_rules",
        "extraction_confidence": 0.95,
        "crawl_time": datetime.utcnow().isoformat(),
        "version_info": {
            "version_id": f"{doc_id}:v001",
            "version_count": 1,
            "is_latest": True,
            "has_updates": False,
        },
        "related_hits": [],
    }

    return DocumentResponse(**mock_doc)


@router.get("/doc/{doc_id}/versions", response_model=VersionChainResponse)
async def get_version_chain(doc_id: str):
    """
    Get document version history.
    获取文档版本历史

    Returns the complete version chain for a document,
    including change summaries for each version.
    """
    # In production, fetch from version manager
    mock_chain = {
        "doc_id": doc_id,
        "current_version_id": f"{doc_id}:v001",
        "version_count": 1,
        "versions": [
            {
                "version_id": f"{doc_id}:v001",
                "captured_at": datetime.utcnow().isoformat(),
                "change_type": "created",
                "title": "文档标题",
                "content_length": 1500,
            }
        ],
    }

    return VersionChainResponse(**mock_chain)


@router.get("/hits/{query_id}")
async def get_discovery_hits(
    query_id: str,
    size: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get discovery layer search hits.
    获取发现层搜索命中记录

    Returns SearchHit records from the discovery layer,
    showing how evidence was discovered through search/hot lists.
    """
    # In production, fetch from OpenSearch
    mock_hits = {
        "query_id": query_id,
        "total": 0,
        "hits": [],
        "took_ms": 3,
    }

    return mock_hits


@router.get("/stats")
async def get_evidence_stats():
    """
    Get evidence library statistics.
    获取证据库统计信息
    """
    # In production, aggregate from OpenSearch
    stats = {
        "total_documents": 0,
        "total_search_hits": 0,
        "documents_by_tier": {
            "S": 0,
            "A": 0,
            "B": 0,
            "C": 0,
        },
        "documents_by_platform": {},
        "documents_by_day": [],
        "average_evidence_score": 0.0,
        "extraction_methods": {
            "template_rules": 0,
            "jsonld": 0,
            "opengraph": 0,
            "trafilatura": 0,
            "fallback": 0,
        },
    }

    return stats


# ============================================================
# OpenSearch DSL Example Endpoints (for documentation)
# ============================================================

@router.get("/dsl/example")
async def get_dsl_example():
    """
    Get example OpenSearch DSL queries.
    获取 OpenSearch DSL 查询示例
    """
    return {
        "boolean_search": {
            "description": "布尔查询 + 时间范围 + 来源过滤 + 高亮",
            "dsl": {
                "size": 20,
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"content_text": "关键词A 关键词B"}}
                        ],
                        "filter": [
                            {"term": {"source_domain": "news.cn"}},
                            {"range": {"publish_time": {"gte": "now-7d/d", "lte": "now"}}}
                        ],
                        "must_not": [
                            {"term": {"is_deleted": True}}
                        ]
                    }
                },
                "highlight": {
                    "fields": {
                        "content_text": {}
                    }
                },
                "sort": [
                    {"evidence_score": "desc"},
                    {"publish_time": "desc"}
                ]
            }
        },
        "vector_search": {
            "description": "k-NN 向量相似检索",
            "dsl": {
                "size": 10,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": [0.01, 0.02, 0.03],
                            "k": 10
                        }
                    }
                },
                "_source": ["title", "canonical_url", "publish_time", "source_domain", "evidence_score"]
            }
        },
        "aggregation": {
            "description": "按来源分级聚合统计",
            "dsl": {
                "size": 0,
                "aggs": {
                    "by_tier": {
                        "terms": {"field": "source_tier"}
                    },
                    "avg_score": {
                        "avg": {"field": "evidence_score"}
                    }
                }
            }
        }
    }