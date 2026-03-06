"""
OpenSearch Client for Evidence Library.
OpenSearch 客户端

Provides a high-level interface for:
- Indexing evidence documents
- Searching with filters and highlighting
- Vector similarity search
- Bulk operations

Author: Aletheia Team
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import structlog

try:
    from opensearchpy import AsyncOpenSearch, OpenSearch, helpers
    from opensearchpy.exceptions import NotFoundError, RequestError
    HAS_OPENSEARCH = True
except ImportError:
    HAS_OPENSEARCH = False

from services.evidence.opensearch_config import (
    EVIDENCE_INDEX_MAPPING,
    SEARCH_HIT_INDEX_MAPPING,
    SearchQuery,
    OpenSearchQueryBuilder,
)

logger = structlog.get_logger()


@dataclass
class OpenSearchConfig:
    """OpenSearch connection configuration"""
    hosts: List[str] = field(default_factory=lambda: ["localhost:9200"])
    username: str = "admin"
    password: str = "admin"
    use_ssl: bool = False
    verify_certs: bool = False
    timeout: int = 30
    max_retries: int = 3
    retry_on_timeout: bool = True

    # Index names
    evidence_index: str = "evidence"
    search_hits_index: str = "search_hits"


class EvidenceSearchClient:
    """
    High-level OpenSearch client for Evidence Library.
    证据库 OpenSearch 高级客户端
    """

    def __init__(self, config: Optional[OpenSearchConfig] = None):
        self.config = config or OpenSearchConfig()
        self._client: Optional[AsyncOpenSearch] = None
        self._sync_client: Optional[OpenSearch] = None
        self.query_builder = OpenSearchQueryBuilder()

    async def connect(self) -> None:
        """Initialize async OpenSearch client"""
        if not HAS_OPENSEARCH:
            raise ImportError("opensearch-py is required. Install with: pip install opensearch-py")

        self._client = AsyncOpenSearch(
            hosts=self.config.hosts,
            http_auth=(self.config.username, self.config.password),
            use_ssl=self.config.use_ssl,
            verify_certs=self.config.verify_certs,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
            retry_on_timeout=self.config.retry_on_timeout,
        )

        # Test connection
        try:
            info = await self._client.info()
            logger.info(
                "opensearch_connected",
                cluster=info.get("cluster_name"),
                version=info.get("version", {}).get("number"),
            )
        except Exception as e:
            logger.error("opensearch_connection_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Close OpenSearch client"""
        if self._client:
            await self._client.close()
            self._client = None

    async def ensure_indexes(self) -> None:
        """Create indexes if they don't exist"""
        if not self._client:
            await self.connect()

        # Create evidence index
        if not await self._client.indices.exists(index=self.config.evidence_index):
            await self._client.indices.create(
                index=self.config.evidence_index,
                body=EVIDENCE_INDEX_MAPPING,
            )
            logger.info("index_created", index=self.config.evidence_index)

        # Create search_hits index
        if not await self._client.indices.exists(index=self.config.search_hits_index):
            await self._client.indices.create(
                index=self.config.search_hits_index,
                body=SEARCH_HIT_INDEX_MAPPING,
            )
            logger.info("index_created", index=self.config.search_hits_index)

    # ============================================================
    # Evidence Document Operations
    # ============================================================

    async def index_evidence(self, doc: Dict[str, Any]) -> bool:
        """
        Index a single evidence document.
        索引单个证据文档
        """
        if not self._client:
            await self.connect()

        try:
            doc_id = doc.get("doc_id")
            response = await self._client.index(
                index=self.config.evidence_index,
                id=doc_id,
                body=doc,
                refresh=False,
            )
            return response.get("result") in ["created", "updated"]
        except Exception as e:
            logger.error("index_evidence_failed", doc_id=doc.get("doc_id"), error=str(e))
            return False

    async def bulk_index_evidence(self, docs: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Bulk index evidence documents.
        批量索引证据文档

        Returns:
            Tuple of (success_count, error_count)
        """
        if not self._client:
            await self.connect()

        if not docs:
            return 0, 0

        actions = []
        for doc in docs:
            actions.append({
                "_index": self.config.evidence_index,
                "_id": doc.get("doc_id"),
                "_source": doc,
            })

        try:
            success, errors = await helpers.async_bulk(
                self._client,
                actions,
                refresh=False,
            )
            error_count = len(errors) if errors else 0
            logger.info("bulk_index_complete", success=success, errors=error_count)
            return success, error_count
        except Exception as e:
            logger.error("bulk_index_failed", error=str(e))
            return 0, len(docs)

    async def get_evidence(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get an evidence document by ID"""
        if not self._client:
            await self.connect()

        try:
            response = await self._client.get(
                index=self.config.evidence_index,
                id=doc_id,
            )
            return response.get("_source")
        except NotFoundError:
            return None
        except Exception as e:
            logger.error("get_evidence_failed", doc_id=doc_id, error=str(e))
            return None

    async def search_evidence(
        self,
        query: SearchQuery,
    ) -> Dict[str, Any]:
        """
        Search evidence documents.
        搜索证据文档
        """
        if not self._client:
            await self.connect()

        dsl = self.query_builder.build_search_query(query)

        try:
            start_time = time.time()
            response = await self._client.search(
                index=self.config.evidence_index,
                body=dsl,
            )
            took_ms = int((time.time() - start_time) * 1000)

            hits = []
            for hit in response.get("hits", {}).get("hits", []):
                source = hit.get("_source", {})
                source["_id"] = hit.get("_id")
                source["_score"] = hit.get("_score")
                if "highlight" in hit:
                    source["_highlight"] = hit["highlight"]
                hits.append(source)

            return {
                "total": response.get("hits", {}).get("total", {}).get("value", 0),
                "hits": hits,
                "took_ms": took_ms,
                "aggregations": response.get("aggregations"),
            }
        except Exception as e:
            logger.error("search_failed", error=str(e))
            return {"total": 0, "hits": [], "took_ms": 0, "error": str(e)}

    async def find_similar(
        self,
        vector: List[float],
        k: int = 10,
        exclude_doc_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find similar documents using vector search.
        使用向量搜索查找相似文档
        """
        if not self._client:
            await self.connect()

        dsl = self.query_builder.build_similar_query(
            vector=vector,
            k=k,
            exclude_doc_ids=exclude_doc_ids or [],
        )

        try:
            response = await self._client.search(
                index=self.config.evidence_index,
                body=dsl,
            )

            hits = []
            for hit in response.get("hits", {}).get("hits", []):
                source = hit.get("_source", {})
                source["_id"] = hit.get("_id")
                source["_score"] = hit.get("_score")
                hits.append(source)

            return hits
        except Exception as e:
            logger.error("similar_search_failed", error=str(e))
            return []

    # ============================================================
    # Search Hit Operations
    # ============================================================

    async def index_search_hit(self, hit: Dict[str, Any]) -> bool:
        """Index a search hit"""
        if not self._client:
            await self.connect()

        try:
            hit_id = hit.get("hit_id")
            response = await self._client.index(
                index=self.config.search_hits_index,
                id=hit_id,
                body=hit,
                refresh=False,
            )
            return response.get("result") in ["created", "updated"]
        except Exception as e:
            logger.error("index_hit_failed", hit_id=hit.get("hit_id"), error=str(e))
            return False

    async def get_hits_by_query(self, query: str, size: int = 100) -> List[Dict[str, Any]]:
        """Get all search hits for a query"""
        if not self._client:
            await self.connect()

        dsl = {
            "size": size,
            "query": {
                "term": {"query.keyword": query}
            },
            "sort": [{"captured_at": {"order": "desc"}}],
        }

        try:
            response = await self._client.search(
                index=self.config.search_hits_index,
                body=dsl,
            )
            return [hit.get("_source") for hit in response.get("hits", {}).get("hits", [])]
        except Exception as e:
            logger.error("get_hits_failed", query=query, error=str(e))
            return []

    # ============================================================
    # Statistics
    # ============================================================

    async def get_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        if not self._client:
            await self.connect()

        stats = {
            "evidence": {},
            "search_hits": {},
        }

        for index_name, key in [
            (self.config.evidence_index, "evidence"),
            (self.config.search_hits_index, "search_hits"),
        ]:
            try:
                # Get document count
                count_response = await self._client.count(index=index_name)
                stats[key]["document_count"] = count_response.get("count", 0)

                # Get index stats
                index_stats = await self._client.indices.stats(index=index_name)
                index_data = index_stats.get("indices", {}).get(index_name, {})
                stats[key]["size_bytes"] = index_data.get("primaries", {}).get("store", {}).get("size_in_bytes", 0)

            except Exception as e:
                logger.warning("stats_error", index=index_name, error=str(e))

        return stats


# Singleton instance
_client_instance: Optional[EvidenceSearchClient] = None


async def get_opensearch_client() -> EvidenceSearchClient:
    """Get or create OpenSearch client singleton"""
    global _client_instance
    if _client_instance is None:
        _client_instance = EvidenceSearchClient()
        await _client_instance.connect()
    return _client_instance