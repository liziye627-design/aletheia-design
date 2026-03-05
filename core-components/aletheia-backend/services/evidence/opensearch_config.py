"""
OpenSearch Index Mapping and Configuration.
OpenSearch 索引映射配置

Implements full-text + vector hybrid search with:
- IK Chinese analyzer
- ngram tokenizer for partial matching
- k-NN vector search

Author: Aletheia Team
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import json


# OpenSearch Index Mapping for Evidence Documents
EVIDENCE_INDEX_MAPPING = {
    "settings": {
        "index": {
            "number_of_shards": 3,
            "number_of_replicas": 1,
            "knn": True,
            "knn.algo_param.ef_search": 512,
        },
        "analysis": {
            "analyzer": {
                "ik_smart_analyzer": {
                    "type": "custom",
                    "tokenizer": "ik_smart",
                    "filter": ["lowercase", "stop_filter"],
                },
                "ik_max_word_analyzer": {
                    "type": "custom",
                    "tokenizer": "ik_max_word",
                    "filter": ["lowercase", "stop_filter"],
                },
                "ngram_analyzer": {
                    "type": "custom",
                    "tokenizer": "ngram_tokenizer",
                    "filter": ["lowercase"],
                },
            },
            "tokenizer": {
                "ngram_tokenizer": {
                    "type": "ngram",
                    "min_gram": 2,
                    "max_gram": 3,
                    "token_chars": ["letter", "digit", "punctuation"],
                },
            },
            "filter": {
                "stop_filter": {
                    "type": "stop",
                    "stopwords": "_chinese_",
                },
            },
        },
    },
    "mappings": {
        "properties": {
            # Document identifiers
            "doc_id": {
                "type": "keyword",
                "doc_values": True,
            },
            "version_id": {
                "type": "keyword",
            },
            "original_url": {
                "type": "keyword",
                "index": False,  # Not searchable, just stored
            },
            "canonical_url": {
                "type": "keyword",
            },

            # Title field - multi-field for different search needs
            "title": {
                "type": "text",
                "analyzer": "ik_max_word_analyzer",
                "search_analyzer": "ik_smart_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 256,
                    },
                    "ngram": {
                        "type": "text",
                        "analyzer": "ngram_analyzer",
                    },
                },
                "term_vector": "with_positions_offsets",
            },

            # Content field - main full-text search
            "content_text": {
                "type": "text",
                "analyzer": "ik_max_word_analyzer",
                "search_analyzer": "ik_smart_analyzer",
                "fields": {
                    "ngram": {
                        "type": "text",
                        "analyzer": "ngram_analyzer",
                    },
                },
                "term_vector": "with_positions_offsets",
            },

            # Content HTML - stored but not analyzed
            "content_html": {
                "type": "text",
                "index": False,
                "store": True,
            },

            # Media type
            "media_type": {
                "type": "keyword",
            },

            # Media assets
            "images": {
                "type": "keyword",
                "index": False,
            },
            "videos": {
                "type": "keyword",
                "index": False,
            },

            # Metadata
            "publish_time": {
                "type": "date",
                "format": "strict_date_optional_time||epoch_millis",
            },
            "crawl_time": {
                "type": "date",
                "format": "strict_date_optional_time||epoch_millis",
            },
            "author": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "ik_smart_analyzer",
                    },
                },
            },
            "source_org": {
                "type": "keyword",
            },
            "language": {
                "type": "keyword",
            },
            "tags": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "ik_smart_analyzer",
                    },
                },
            },
            "topics": {
                "type": "keyword",
            },

            # Platform info
            "platform": {
                "type": "keyword",
            },
            "source_domain": {
                "type": "keyword",
            },
            "platform_doc_id": {
                "type": "keyword",
            },

            # Extraction info
            "extraction_method": {
                "type": "keyword",
            },
            "extraction_confidence": {
                "type": "float",
            },

            # Credibility scoring
            "source_tier": {
                "type": "keyword",
            },
            "evidence_score": {
                "type": "float",
                "doc_values": True,
            },
            "credibility_level": {
                "type": "keyword",
            },

            # Version management
            "is_latest": {
                "type": "boolean",
            },
            "version_count": {
                "type": "integer",
            },
            "is_deleted": {
                "type": "boolean",
            },
            "is_updated": {
                "type": "boolean",
            },
            "has_correction": {
                "type": "boolean",
            },

            # Content hashes
            "url_hash": {
                "type": "keyword",
            },
            "content_hash": {
                "type": "keyword",
            },
            "simhash": {
                "type": "keyword",
            },

            # Vector embedding for semantic search
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,  # Adjust based on embedding model
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {
                        "ef_construction": 256,
                        "m": 16,
                    },
                },
            },

            # Raw snapshot reference
            "raw_snapshot_uri": {
                "type": "keyword",
                "index": False,
            },

            # HTTP metadata
            "http_status": {
                "type": "integer",
            },
            "fetch_latency_ms": {
                "type": "integer",
            },

            # Related hits
            "hit_ids": {
                "type": "keyword",
            },
        },
    },
}

# Search Hit Index Mapping
SEARCH_HIT_INDEX_MAPPING = {
    "settings": {
        "index": {
            "number_of_shards": 2,
            "number_of_replicas": 1,
        },
        "analysis": {
            "analyzer": {
                "ik_smart_analyzer": {
                    "type": "custom",
                    "tokenizer": "ik_smart",
                    "filter": ["lowercase"],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "hit_id": {
                "type": "keyword",
            },
            "query": {
                "type": "text",
                "analyzer": "ik_smart_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                    },
                },
            },
            "entry_url": {
                "type": "keyword",
            },
            "hit_url": {
                "type": "keyword",
            },
            "rank": {
                "type": "integer",
            },
            "page_no": {
                "type": "integer",
            },
            "hit_title": {
                "type": "text",
                "analyzer": "ik_smart_analyzer",
                "term_vector": "with_positions_offsets",
            },
            "hit_snippet": {
                "type": "text",
                "analyzer": "ik_smart_analyzer",
                "term_vector": "with_positions_offsets",
            },
            "hit_time_hint": {
                "type": "keyword",
            },
            "hit_source_hint": {
                "type": "keyword",
            },
            "platform": {
                "type": "keyword",
            },
            "source_domain": {
                "type": "keyword",
            },
            "discovery_mode": {
                "type": "keyword",
            },
            "captured_at": {
                "type": "date",
            },
            "doc_id": {
                "type": "keyword",
            },
            "fetch_status": {
                "type": "keyword",
            },
            "extra": {
                "type": "object",
                "enabled": False,  # Not indexed
            },
        },
    },
}


@dataclass
class SearchQuery:
    """Search query parameters"""
    # Text query
    query_text: Optional[str] = None
    query_fields: List[str] = field(default_factory=lambda: ["title", "content_text"])

    # Filters
    source_domains: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)
    source_tiers: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # Time range
    publish_time_start: Optional[str] = None
    publish_time_end: Optional[str] = None
    crawl_time_start: Optional[str] = None
    crawl_time_end: Optional[str] = None

    # Exclusions
    exclude_deleted: bool = True
    exclude_low_confidence: bool = False
    min_evidence_score: Optional[float] = None

    # Pagination
    size: int = 20
    from_: int = 0

    # Sorting
    sort_by: str = "evidence_score"
    sort_order: str = "desc"

    # Highlighting
    highlight: bool = True
    highlight_fields: List[str] = field(default_factory=lambda: ["title", "content_text"])
    highlight_fragment_size: int = 200
    highlight_number_of_fragments: int = 3

    # Vector search
    vector: Optional[List[float]] = None
    vector_k: int = 10


@dataclass
class SearchResult:
    """Search result"""
    total: int
    hits: List[Dict[str, Any]]
    took_ms: int
    query: SearchQuery
    aggregations: Optional[Dict[str, Any]] = None


class OpenSearchQueryBuilder:
    """
    Build OpenSearch DSL queries.
    OpenSearch DSL 查询构建器
    """

    def build_search_query(self, params: SearchQuery) -> Dict[str, Any]:
        """
        Build OpenSearch search query DSL.
        构建 OpenSearch 搜索查询 DSL
        """
        query = {
            "size": params.size,
            "from": params.from_,
            "query": self._build_query_clause(params),
        }

        # Add sorting
        query["sort"] = self._build_sort_clause(params)

        # Add highlighting
        if params.highlight:
            query["highlight"] = self._build_highlight_clause(params)

        # Add vector search if provided
        if params.vector:
            query = self._combine_vector_search(query, params)

        return query

    def _build_query_clause(self, params: SearchQuery) -> Dict[str, Any]:
        """Build the main query clause"""
        bool_query = {
            "must": [],
            "filter": [],
            "must_not": [],
            "should": [],
        }

        # Text query
        if params.query_text:
            bool_query["must"].append({
                "multi_match": {
                    "query": params.query_text,
                    "fields": params.query_fields,
                    "type": "best_fields",
                    "operator": "and",
                    "minimum_should_match": "75%",
                }
            })

        # Source domain filter
        if params.source_domains:
            bool_query["filter"].append({
                "terms": {"source_domain": params.source_domains}
            })

        # Platform filter
        if params.platforms:
            bool_query["filter"].append({
                "terms": {"platform": params.platforms}
            })

        # Source tier filter
        if params.source_tiers:
            bool_query["filter"].append({
                "terms": {"source_tier": params.source_tiers}
            })

        # Author filter
        if params.authors:
            bool_query["filter"].append({
                "terms": {"author": params.authors}
            })

        # Tags filter
        if params.tags:
            bool_query["filter"].append({
                "terms": {"tags": params.tags}
            })

        # Time range filters
        if params.publish_time_start or params.publish_time_end:
            range_filter = {"range": {"publish_time": {}}}
            if params.publish_time_start:
                range_filter["range"]["publish_time"]["gte"] = params.publish_time_start
            if params.publish_time_end:
                range_filter["range"]["publish_time"]["lte"] = params.publish_time_end
            bool_query["filter"].append(range_filter)

        if params.crawl_time_start or params.crawl_time_end:
            range_filter = {"range": {"crawl_time": {}}}
            if params.crawl_time_start:
                range_filter["range"]["crawl_time"]["gte"] = params.crawl_time_start
            if params.crawl_time_end:
                range_filter["range"]["crawl_time"]["lte"] = params.crawl_time_end
            bool_query["filter"].append(range_filter)

        # Exclusions
        if params.exclude_deleted:
            bool_query["must_not"].append({
                "term": {"is_deleted": True}
            })

        # Minimum evidence score
        if params.min_evidence_score is not None:
            bool_query["filter"].append({
                "range": {"evidence_score": {"gte": params.min_evidence_score}}
            })

        # Exclude low confidence
        if params.exclude_low_confidence:
            bool_query["filter"].append({
                "range": {"extraction_confidence": {"gte": 0.5}}
            })

        # Build final query
        result = {"bool": {}}
        for clause in ["must", "filter", "must_not", "should"]:
            if bool_query[clause]:
                result["bool"][clause] = bool_query[clause]

        # If no query, match all
        if not result["bool"]:
            result = {"match_all": {}}

        return result

    def _build_sort_clause(self, params: SearchQuery) -> List[Dict[str, Any]]:
        """Build sort clause"""
        sort = []

        if params.sort_by == "relevance":
            # Default OpenSearch relevance scoring
            pass
        else:
            sort.append({
                params.sort_by: {"order": params.sort_order}
            })

        # Always add secondary sort by publish_time
        sort.append({
            "publish_time": {"order": "desc", "missing": "_last"}
        })

        return sort

    def _build_highlight_clause(self, params: SearchQuery) -> Dict[str, Any]:
        """Build highlight clause"""
        fields = {}
        for field in params.highlight_fields:
            fields[field] = {
                "fragment_size": params.highlight_fragment_size,
                "number_of_fragments": params.highlight_number_of_fragments,
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            }

        return {
            "fields": fields,
            "require_field_match": False,
        }

    def _combine_vector_search(
        self,
        query: Dict[str, Any],
        params: SearchQuery,
    ) -> Dict[str, Any]:
        """Combine text and vector search using KNN"""
        if not params.vector:
            return query

        # For pure vector search
        if not params.query_text:
            return {
                "size": params.vector_k,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": params.vector,
                            "k": params.vector_k,
                        }
                    }
                },
            }

        # Hybrid search: combine text and vector
        # Using RRF (Reciprocal Rank Fusion) approach
        return {
            "size": params.size,
            "query": {
                "bool": {
                    "should": [
                        query["query"],
                        {
                            "knn": {
                                "embedding": {
                                    "vector": params.vector,
                                    "k": params.vector_k,
                                    "boost": 0.5,
                                }
                            }
                        }
                    ]
                }
            },
            "highlight": query.get("highlight"),
            "sort": query.get("sort"),
        }

    def build_similar_query(
        self,
        vector: List[float],
        k: int = 10,
        exclude_doc_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build k-NN similarity search query"""
        query = {
            "size": k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": vector,
                        "k": k,
                    }
                }
            },
            "_source": [
                "doc_id", "title", "canonical_url", "publish_time",
                "source_domain", "evidence_score", "source_tier",
            ],
        }

        if exclude_doc_ids:
            query["query"] = {
                "bool": {
                    "must": [query["query"]],
                    "must_not": [
                        {"terms": {"doc_id": exclude_doc_ids}}
                    ],
                }
            }

        return query


def get_evidence_index_config() -> Dict[str, Any]:
    """Get evidence index configuration"""
    return EVIDENCE_INDEX_MAPPING.copy()


def get_search_hit_index_config() -> Dict[str, Any]:
    """Get search hit index configuration"""
    return SEARCH_HIT_INDEX_MAPPING.copy()