"""
Evidence Reranker Service

Provides LLM-based reranking of evidence items using SiliconFlow's Qwen3-Reranker-8B model.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from core.config import settings
from services.llm.siliconflow_client import get_siliconflow_client


class EvidenceReranker:
    """
    Evidence Reranker using LLM-based semantic relevance scoring.

    Uses SiliconFlow's rerank API (Qwen3-Reranker-8B) to score and rank
    evidence items based on their relevance to a claim.
    """

    def __init__(
        self,
        batch_size: int = 32,
        timeout_sec: float = 12.0,
        model: str = "Qwen/Qwen3-Reranker-8B",
    ):
        """
        Initialize the reranker.

        Args:
            batch_size: Maximum number of documents per API call
            timeout_sec: Timeout for each API call
            model: Rerank model to use
        """
        self.batch_size = batch_size
        self.timeout_sec = timeout_sec
        self.model = model
        self._client = None

    @property
    def client(self):
        """Lazy load the SiliconFlow client."""
        if self._client is None:
            self._client = get_siliconflow_client()
        return self._client

    def _build_document_text(self, item: Dict[str, Any]) -> str:
        """
        Build a text representation of an evidence item for reranking.

        Args:
            item: Evidence item dictionary

        Returns:
            Combined text for reranking
        """
        parts = []

        # Title/headline
        title = item.get("title") or item.get("headline")
        if title:
            parts.append(str(title).strip())

        # Snippet/content
        snippet = item.get("snippet") or item.get("content_text") or item.get("content")
        if snippet:
            parts.append(str(snippet).strip()[:500])

        # Source name
        source = item.get("source_name")
        if source:
            parts.append(f"[{source}]")

        return " | ".join(parts) if parts else ""

    async def rerank_evidence(
        self,
        claim_text: str,
        evidence_items: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank evidence items based on semantic relevance to the claim.

        Args:
            claim_text: The claim to compare against
            evidence_items: List of evidence item dictionaries
            top_n: Number of top items to return (default: all)

        Returns:
            List of evidence items with added 'rerank_score' field,
            sorted by relevance in descending order
        """
        if not evidence_items:
            return []

        if not claim_text or not claim_text.strip():
            logger.warning("Empty claim text provided to reranker")
            return evidence_items

        # Build documents for reranking
        documents = []
        valid_indices = []

        for idx, item in enumerate(evidence_items):
            doc_text = self._build_document_text(item)
            if doc_text:
                documents.append(doc_text)
                valid_indices.append(idx)

        if not documents:
            logger.warning("No valid documents to rerank")
            return evidence_items

        # Process in batches
        all_results = []
        top_n_value = top_n or len(documents)

        try:
            for i in range(0, len(documents), self.batch_size):
                batch_docs = documents[i : i + self.batch_size]
                batch_top_n = min(self.batch_size, len(batch_docs))

                try:
                    result = await self.client.rerank_documents(
                        query=claim_text.strip(),
                        documents=batch_docs,
                        model=self.model,
                        top_n=batch_top_n,
                        timeout_sec=self.timeout_sec,
                    )

                    # Process results
                    for res in result.get("results", []):
                        original_idx = valid_indices[i + res["index"]]
                        all_results.append(
                            {
                                "index": original_idx,
                                "relevance_score": res.get("relevance_score", 0.0),
                            }
                        )

                except Exception as e:
                    logger.warning(f"Rerank batch failed: {e}")
                    # Fallback: assign neutral scores to failed batch
                    for j, doc_idx in enumerate(valid_indices[i : i + self.batch_size]):
                        all_results.append(
                            {
                                "index": doc_idx,
                                "relevance_score": 0.5,  # Neutral fallback
                            }
                        )

            # Sort by relevance score (descending)
            all_results.sort(key=lambda x: x["relevance_score"], reverse=True)

            # Build result list with scores
            reranked = []
            for res in all_results[: (top_n or len(all_results))]:
                idx = res["index"]
                item = evidence_items[idx].copy()
                item["rerank_score"] = res["relevance_score"]
                reranked.append(item)

            logger.info(
                f"Reranked {len(evidence_items)} evidence items, "
                f"returned top {len(reranked)}"
            )

            return reranked

        except Exception as e:
            logger.error(f"Rerank failed: {e}")
            # Return original items with neutral scores
            return [
                {**item, "rerank_score": 0.5} for item in evidence_items[: (top_n or len(evidence_items))]
            ]

    async def compute_rerank_scores(
        self,
        claim_text: str,
        evidence_items: List[Dict[str, Any]],
    ) -> Dict[int, float]:
        """
        Compute rerank scores for evidence items.

        Args:
            claim_text: The claim to compare against
            evidence_items: List of evidence item dictionaries

        Returns:
            Dictionary mapping evidence index to rerank score
        """
        if not evidence_items or not claim_text:
            return {}

        reranked = await self.rerank_evidence(claim_text, evidence_items)

        # Map back to original indices
        scores = {}
        for item in reranked:
            # Find original index
            for idx, orig in enumerate(evidence_items):
                if item.get("id") == orig.get("id") or item.get("url") == orig.get("url"):
                    scores[idx] = item.get("rerank_score", 0.5)
                    break

        return scores


# Global reranker instance
_reranker: Optional[EvidenceReranker] = None


def get_evidence_reranker() -> EvidenceReranker:
    """Get the global EvidenceReranker instance."""
    global _reranker
    if _reranker is None:
        _reranker = EvidenceReranker(
            batch_size=getattr(settings, "INVESTIGATION_RERANK_BATCH_SIZE", 32),
            timeout_sec=getattr(settings, "INVESTIGATION_RLM_SEMANTIC_RERANK_TIMEOUT_SEC", 12.0),
            model=getattr(settings, "SILICONFLOW_RERANK_MODEL", "Qwen/Qwen3-Reranker-8B"),
        )
    return _reranker