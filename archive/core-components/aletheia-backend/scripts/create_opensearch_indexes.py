#!/usr/bin/env python3
"""
OpenSearch Index Creation Script.
OpenSearch 索引创建脚本

Creates evidence and search_hit indexes with:
- IK Chinese analyzer
- ngram tokenizer for partial matching
- k-NN vector search

Usage:
    python scripts/create_opensearch_indexes.py [--host HOST] [--port PORT]
"""

import argparse
import json
import sys
import time
from typing import Dict, Any, Optional

import requests
from requests.exceptions import RequestException


# Evidence Index Mapping
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
                    "filter": ["lowercase"],
                },
                "ik_max_word_analyzer": {
                    "type": "custom",
                    "tokenizer": "ik_max_word",
                    "filter": ["lowercase"],
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
                    "token_chars": ["letter", "digit"],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "doc_id": {"type": "keyword"},
            "version_id": {"type": "keyword"},
            "original_url": {"type": "keyword", "index": False},
            "canonical_url": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "ik_max_word_analyzer",
                "search_analyzer": "ik_smart_analyzer",
                "fields": {
                    "keyword": {"type": "keyword", "ignore_above": 256},
                    "ngram": {"type": "text", "analyzer": "ngram_analyzer"},
                },
                "term_vector": "with_positions_offsets",
            },
            "content_text": {
                "type": "text",
                "analyzer": "ik_max_word_analyzer",
                "search_analyzer": "ik_smart_analyzer",
                "fields": {
                    "ngram": {"type": "text", "analyzer": "ngram_analyzer"},
                },
                "term_vector": "with_positions_offsets",
            },
            "content_html": {"type": "text", "index": False},
            "media_type": {"type": "keyword"},
            "images": {"type": "keyword", "index": False},
            "videos": {"type": "keyword", "index": False},
            "publish_time": {"type": "date"},
            "crawl_time": {"type": "date"},
            "author": {
                "type": "keyword",
                "fields": {"text": {"type": "text", "analyzer": "ik_smart_analyzer"}},
            },
            "source_org": {"type": "keyword"},
            "language": {"type": "keyword"},
            "tags": {
                "type": "keyword",
                "fields": {"text": {"type": "text", "analyzer": "ik_smart_analyzer"}},
            },
            "topics": {"type": "keyword"},
            "platform": {"type": "keyword"},
            "source_domain": {"type": "keyword"},
            "platform_doc_id": {"type": "keyword"},
            "extraction_method": {"type": "keyword"},
            "extraction_confidence": {"type": "float"},
            "source_tier": {"type": "keyword"},
            "evidence_score": {"type": "float"},
            "credibility_level": {"type": "keyword"},
            "is_latest": {"type": "boolean"},
            "version_count": {"type": "integer"},
            "is_deleted": {"type": "boolean"},
            "is_updated": {"type": "boolean"},
            "has_correction": {"type": "boolean"},
            "url_hash": {"type": "keyword"},
            "content_hash": {"type": "keyword"},
            "simhash": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {"ef_construction": 256, "m": 16},
                },
            },
            "raw_snapshot_uri": {"type": "keyword", "index": False},
            "http_status": {"type": "integer"},
            "fetch_latency_ms": {"type": "integer"},
            "hit_ids": {"type": "keyword"},
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
            "hit_id": {"type": "keyword"},
            "query": {
                "type": "text",
                "analyzer": "ik_smart_analyzer",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "entry_url": {"type": "keyword"},
            "hit_url": {"type": "keyword"},
            "rank": {"type": "integer"},
            "page_no": {"type": "integer"},
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
            "hit_time_hint": {"type": "keyword"},
            "hit_source_hint": {"type": "keyword"},
            "platform": {"type": "keyword"},
            "source_domain": {"type": "keyword"},
            "discovery_mode": {"type": "keyword"},
            "captured_at": {"type": "date"},
            "doc_id": {"type": "keyword"},
            "fetch_status": {"type": "keyword"},
            "extra": {"type": "object", "enabled": False},
        },
    },
}


class OpenSearchClient:
    """Simple OpenSearch client for index creation"""

    def __init__(self, host: str = "localhost", port: int = 9200):
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def health_check(self) -> bool:
        """Check if OpenSearch is healthy"""
        try:
            response = self.session.get(f"{self.base_url}/_cluster/health")
            if response.status_code == 200:
                health = response.json()
                return health.get("status") in ["green", "yellow"]
            return False
        except RequestException:
            return False

    def index_exists(self, index_name: str) -> bool:
        """Check if index exists"""
        try:
            response = self.session.head(f"{self.base_url}/{index_name}")
            return response.status_code == 200
        except RequestException:
            return False

    def create_index(self, index_name: str, mapping: Dict[str, Any]) -> bool:
        """Create an index with given mapping"""
        try:
            response = self.session.put(
                f"{self.base_url}/{index_name}",
                data=json.dumps(mapping),
            )
            if response.status_code in [200, 201]:
                print(f"  ✓ Index '{index_name}' created successfully")
                return True
            else:
                print(f"  ✗ Failed to create index '{index_name}': {response.text}")
                return False
        except RequestException as e:
            print(f"  ✗ Error creating index '{index_name}': {e}")
            return False

    def delete_index(self, index_name: str) -> bool:
        """Delete an index"""
        try:
            response = self.session.delete(f"{self.base_url}/{index_name}")
            return response.status_code == 200
        except RequestException:
            return False

    def get_cluster_info(self) -> Optional[Dict[str, Any]]:
        """Get cluster information"""
        try:
            response = self.session.get(self.base_url)
            if response.status_code == 200:
                return response.json()
        except RequestException:
            pass
        return None


def main():
    parser = argparse.ArgumentParser(description="Create OpenSearch indexes for Evidence Library")
    parser.add_argument("--host", default="localhost", help="OpenSearch host")
    parser.add_argument("--port", type=int, default=9200, help="OpenSearch port")
    parser.add_argument("--force", action="store_true", help="Delete existing indexes before creating")
    args = parser.parse_args()

    print("=" * 60)
    print("OpenSearch Index Creation for Evidence Library")
    print("=" * 60)

    client = OpenSearchClient(host=args.host, port=args.port)

    # Wait for OpenSearch to be ready
    print("\nWaiting for OpenSearch to be ready...")
    max_retries = 30
    for i in range(max_retries):
        if client.health_check():
            print("  ✓ OpenSearch is healthy")
            break
        print(f"  Waiting... ({i+1}/{max_retries})")
        time.sleep(2)
    else:
        print("  ✗ OpenSearch is not responding")
        sys.exit(1)

    # Get cluster info
    info = client.get_cluster_info()
    if info:
        print(f"\nCluster: {info.get('cluster_name', 'unknown')}")
        print(f"Version: {info.get('version', {}).get('number', 'unknown')}")

    # Create indexes
    indexes = [
        ("evidence", EVIDENCE_INDEX_MAPPING),
        ("search_hits", SEARCH_HIT_INDEX_MAPPING),
    ]

    print("\nCreating indexes:")
    for index_name, mapping in indexes:
        print(f"\n  Index: {index_name}")

        if args.force and client.index_exists(index_name):
            print(f"    Deleting existing index...")
            client.delete_index(index_name)

        if client.index_exists(index_name):
            print(f"    Index already exists (use --force to recreate)")
            continue

        client.create_index(index_name, mapping)

    # Verify indexes
    print("\n" + "=" * 60)
    print("Verification:")
    for index_name, _ in indexes:
        if client.index_exists(index_name):
            print(f"  ✓ {index_name}: OK")
        else:
            print(f"  ✗ {index_name}: MISSING")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()