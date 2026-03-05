"""
Evidence Library Metrics and Monitoring.
证据库监控与指标

Collects Prometheus metrics for:
- Collection success/failure rates
- Deduplication statistics
- Evidence score distribution
- Platform-level statistics
- Latency metrics

Author: Aletheia Team
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
import structlog

try:
    from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

logger = structlog.get_logger()


# ============================================================
# Prometheus Metrics Definitions
# ============================================================

if HAS_PROMETHEUS:
    # Collection metrics
    EVIDENCE_COLLECTION_TOTAL = Counter(
        "evidence_collection_total",
        "Total evidence collection attempts",
        ["platform", "status"],
    )

    EVIDENCE_COLLECTION_DURATION = Histogram(
        "evidence_collection_duration_seconds",
        "Evidence collection duration in seconds",
        ["platform"],
        buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    )

    # Deduplication metrics
    EVIDENCE_DEDUP_TOTAL = Counter(
        "evidence_dedup_total",
        "Total deduplication checks",
        ["result"],  # unique, exact_dup, near_dup
    )

    # Scoring metrics
    EVIDENCE_SCORE = Histogram(
        "evidence_score",
        "Evidence credibility score distribution",
        ["source_tier"],
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )

    EVIDENCE_EXTRACTION_CONFIDENCE = Histogram(
        "evidence_extraction_confidence",
        "Content extraction confidence distribution",
        ["method"],
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )

    # Index metrics
    EVIDENCE_INDEX_OPERATIONS = Counter(
        "evidence_index_operations_total",
        "Total index operations",
        ["operation", "status"],  # operation: index, bulk, search
    )

    EVIDENCE_INDEX_LATENCY = Histogram(
        "evidence_index_latency_seconds",
        "Index operation latency",
        ["operation"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )

    # Document counts
    EVIDENCE_DOC_COUNT = Gauge(
        "evidence_doc_count",
        "Total evidence documents",
        ["source_tier", "platform"],
    )

    EVIDENCE_SEARCH_HIT_COUNT = Gauge(
        "evidence_search_hit_count",
        "Total search hit records",
        ["platform"],
    )

    # Version metrics
    EVIDENCE_VERSION_COUNT = Histogram(
        "evidence_version_count",
        "Number of versions per document",
        buckets=[1, 2, 3, 5, 10, 20],
    )

    EVIDENCE_CORRECTIONS = Counter(
        "evidence_corrections_total",
        "Total documents with corrections/retractions",
        ["type"],  # correction, retraction, update
    )


@dataclass
class CollectionMetrics:
    """Collection metrics for a single operation"""
    platform: str
    query: str
    total_items: int = 0
    successful: int = 0
    failed: int = 0
    duplicates: int = 0
    duration_ms: int = 0

    # Score distribution
    scores: List[float] = field(default_factory=list)

    # Extraction methods
    extraction_methods: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "query": self.query,
            "total_items": self.total_items,
            "successful": self.successful,
            "failed": self.failed,
            "duplicates": self.duplicates,
            "duration_ms": self.duration_ms,
            "success_rate": self.successful / self.total_items if self.total_items > 0 else 0,
            "dedup_rate": self.duplicates / self.total_items if self.total_items > 0 else 0,
            "avg_score": sum(self.scores) / len(self.scores) if self.scores else 0,
            "extraction_methods": self.extraction_methods,
        }


@dataclass
class AggregateMetrics:
    """Aggregate metrics over time"""
    total_collections: int = 0
    total_items: int = 0
    total_successful: int = 0
    total_failed: int = 0
    total_duplicates: int = 0

    # By platform
    by_platform: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))

    # By tier
    by_tier: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Score distribution
    score_buckets: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Extraction method distribution
    extraction_methods: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_collections": self.total_collections,
            "total_items": self.total_items,
            "total_successful": self.total_successful,
            "total_failed": self.total_failed,
            "total_duplicates": self.total_duplicates,
            "success_rate": self.total_successful / self.total_items if self.total_items > 0 else 0,
            "dedup_rate": self.total_duplicates / self.total_items if self.total_items > 0 else 0,
            "by_platform": dict(self.by_platform),
            "by_tier": dict(self.by_tier),
            "score_buckets": dict(self.score_buckets),
            "extraction_methods": dict(self.extraction_methods),
        }


class EvidenceMetricsCollector:
    """
    Collects and aggregates evidence library metrics.
    证据库指标收集器
    """

    def __init__(self):
        self.aggregate = AggregateMetrics()
        self._collection_history: List[CollectionMetrics] = []

    def record_collection(self, metrics: CollectionMetrics) -> None:
        """Record a collection operation"""
        self._collection_history.append(metrics)

        # Update aggregates
        self.aggregate.total_collections += 1
        self.aggregate.total_items += metrics.total_items
        self.aggregate.total_successful += metrics.successful
        self.aggregate.total_failed += metrics.failed
        self.aggregate.total_duplicates += metrics.duplicates

        # Update by_platform
        self.aggregate.by_platform[metrics.platform]["total"] += metrics.total_items
        self.aggregate.by_platform[metrics.platform]["successful"] += metrics.successful
        self.aggregate.by_platform[metrics.platform]["failed"] += metrics.failed
        self.aggregate.by_platform[metrics.platform]["duplicates"] += metrics.duplicates

        # Update score distribution
        for score in metrics.scores:
            bucket = self._get_score_bucket(score)
            self.aggregate.score_buckets[bucket] += 1

        # Update extraction methods
        for method, count in metrics.extraction_methods.items():
            self.aggregate.extraction_methods[method] += count

        # Update Prometheus metrics
        if HAS_PROMETHEUS:
            self._update_prometheus(metrics)

    def record_dedup(
        self,
        is_duplicate: bool,
        duplicate_type: str = "none",
    ) -> None:
        """Record a deduplication check"""
        if HAS_PROMETHEUS:
            if is_duplicate:
                EVIDENCE_DEDUP_TOTAL.labels(result=duplicate_type).inc()
            else:
                EVIDENCE_DEDUP_TOTAL.labels(result="unique").inc()

    def record_evidence_score(
        self,
        score: float,
        source_tier: str,
    ) -> None:
        """Record an evidence score"""
        self.aggregate.by_tier[source_tier] += 1

        if HAS_PROMETHEUS:
            EVIDENCE_SCORE.labels(source_tier=source_tier).observe(score)

    def record_extraction(
        self,
        method: str,
        confidence: float,
    ) -> None:
        """Record an extraction result"""
        if HAS_PROMETHEUS:
            EVIDENCE_EXTRACTION_CONFIDENCE.labels(method=method).observe(confidence)

    def record_index_operation(
        self,
        operation: str,
        success: bool,
        latency_seconds: float,
    ) -> None:
        """Record an index operation"""
        if HAS_PROMETHEUS:
            status = "success" if success else "failure"
            EVIDENCE_INDEX_OPERATIONS.labels(operation=operation, status=status).inc()
            EVIDENCE_INDEX_LATENCY.labels(operation=operation).observe(latency_seconds)

    def record_version(self, version_count: int, has_correction: bool, has_retraction: bool) -> None:
        """Record version information"""
        if HAS_PROMETHEUS:
            EVIDENCE_VERSION_COUNT.observe(version_count)
            if has_correction:
                EVIDENCE_CORRECTIONS.labels(type="correction").inc()
            if has_retraction:
                EVIDENCE_CORRECTIONS.labels(type="retraction").inc()

    def update_doc_counts(
        self,
        counts_by_tier_platform: Dict[str, Dict[str, int]],
    ) -> None:
        """Update document count gauges"""
        if HAS_PROMETHEUS:
            for tier, platform_counts in counts_by_tier_platform.items():
                for platform, count in platform_counts.items():
                    EVIDENCE_DOC_COUNT.labels(source_tier=tier, platform=platform).set(count)

    def _get_score_bucket(self, score: float) -> str:
        """Get the bucket for a score"""
        if score < 0.2:
            return "0.0-0.2"
        elif score < 0.4:
            return "0.2-0.4"
        elif score < 0.6:
            return "0.4-0.6"
        elif score < 0.8:
            return "0.6-0.8"
        else:
            return "0.8-1.0"

    def _update_prometheus(self, metrics: CollectionMetrics) -> None:
        """Update Prometheus metrics from collection metrics"""
        # Collection counts
        EVIDENCE_COLLECTION_TOTAL.labels(platform=metrics.platform, status="success").inc(metrics.successful)
        EVIDENCE_COLLECTION_TOTAL.labels(platform=metrics.platform, status="failure").inc(metrics.failed)

        # Duration
        EVIDENCE_COLLECTION_DURATION.labels(platform=metrics.platform).observe(
            metrics.duration_ms / 1000.0
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return self.aggregate.to_dict()

    def get_platform_stats(self, platform: str) -> Dict[str, Any]:
        """Get statistics for a specific platform"""
        return dict(self.aggregate.by_platform.get(platform, {}))

    def get_recent_collections(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent collection operations"""
        recent = self._collection_history[-limit:]
        return [m.to_dict() for m in recent]

    def reset(self) -> None:
        """Reset all metrics"""
        self.aggregate = AggregateMetrics()
        self._collection_history.clear()


# Singleton instance
_metrics_collector: Optional[EvidenceMetricsCollector] = None


def get_metrics_collector() -> EvidenceMetricsCollector:
    """Get or create metrics collector singleton"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = EvidenceMetricsCollector()
    return _metrics_collector


# ============================================================
# Monitoring Dashboard Configuration
# ============================================================

GRAFANA_DASHBOARD_CONFIG = {
    "dashboard": {
        "title": "Evidence Library Monitoring",
        "panels": [
            {
                "title": "Collection Success Rate",
                "type": "gauge",
                "targets": [
                    {
                        "expr": "rate(evidence_collection_total{status=\"success\"}[5m]) / rate(evidence_collection_total[5m])",
                        "legendFormat": "{{platform}}",
                    }
                ],
            },
            {
                "title": "Evidence Score Distribution",
                "type": "histogram",
                "targets": [
                    {
                        "expr": "rate(evidence_score_bucket[5m])",
                        "legendFormat": "{{le}}",
                    }
                ],
            },
            {
                "title": "Deduplication Rate",
                "type": "piechart",
                "targets": [
                    {
                        "expr": "rate(evidence_dedup_total[5m])",
                        "legendFormat": "{{result}}",
                    }
                ],
            },
            {
                "title": "Collection Latency",
                "type": "graph",
                "targets": [
                    {
                        "expr": "histogram_quantile(0.95, rate(evidence_collection_duration_seconds_bucket[5m]))",
                        "legendFormat": "p95 {{platform}}",
                    }
                ],
            },
            {
                "title": "Extraction Methods",
                "type": "piechart",
                "targets": [
                    {
                        "expr": "rate(evidence_extraction_confidence_count[5m])",
                        "legendFormat": "{{method}}",
                    }
                ],
            },
            {
                "title": "Documents by Tier",
                "type": "graph",
                "targets": [
                    {
                        "expr": "evidence_doc_count",
                        "legendFormat": "{{source_tier}} - {{platform}}",
                    }
                ],
            },
        ],
    }
}