"""
URL Normalization and Deduplication Module.
URL 规范化与去重模块

This module implements URL normalization and content deduplication
for the evidence library, including:
- URL canonicalization (rel=canonical, parameter stripping)
- Content hashing (SHA256, SimHash)
- Near-duplicate detection
"""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import (
    urlparse,
    urlunparse,
    parse_qs,
    urlencode,
    unquote,
)
from typing import Optional, List, Set, Tuple, Dict, Any
import struct


# Tracking parameters to remove from URLs
TRACKING_PARAMS = {
    # Common tracking parameters
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_referrer",
    # Chinese platforms
    "spm", "from", "source", "share_token", "share_id",
    "is_share", "app", "timestamp", "signature",
    # Social sharing
    "share_from", "s_source", "st", "ref", "referrer",
    # Other common trackers
    "fbclid", "gclid", "msclkid", "mc_eid", "mc_cid",
    "_ga", "_gl", "yclid", "wbraid", "gbraid",
}

# Parameters that affect content (should be kept)
CONTENT_PARAMS = {
    "id", "doc_id", "article_id", "post_id", "video_id",
    "page", "p", "pn", "offset", "limit",
    "keyword", "q", "query", "search", "text",
    "type", "category", "tag", "topic",
    "date", "time", "sort", "order",
}


@dataclass
class URLNormalizationResult:
    """Result of URL normalization"""
    original_url: str
    normalized_url: str
    canonical_url: Optional[str] = None
    url_hash: str = ""
    domain: str = ""
    path: str = ""
    removed_params: List[str] = None

    def __post_init__(self):
        if self.removed_params is None:
            self.removed_params = []


class URLNormalizer:
    """
    URL Normalizer for evidence deduplication.
    URL 规范化器 - 用于证据去重
    """

    def __init__(
        self,
        remove_tracking_params: bool = True,
        remove_fragment: bool = True,
        lowercase_host: bool = True,
        keep_content_params: bool = True,
    ):
        self.remove_tracking_params = remove_tracking_params
        self.remove_fragment = remove_fragment
        self.lowercase_host = lowercase_host
        self.keep_content_params = keep_content_params

    def normalize(
        self,
        url: str,
        canonical_hint: Optional[str] = None,
    ) -> URLNormalizationResult:
        """
        Normalize a URL for deduplication.
        规范化 URL 用于去重

        Args:
            url: Original URL to normalize
            canonical_hint: Optional canonical URL from rel=canonical

        Returns:
            URLNormalizationResult with normalized URL and metadata
        """
        original_url = url

        # 1. Decode any encoded characters
        try:
            url = unquote(url)
        except Exception:
            pass

        # 2. Parse URL
        try:
            parsed = urlparse(url)
        except Exception:
            # If parsing fails, return original
            return URLNormalizationResult(
                original_url=original_url,
                normalized_url=url,
                url_hash=self._hash_url(url),
            )

        # 3. Lowercase scheme and host
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc
        if self.lowercase_host:
            netloc = netloc.lower()

        # 4. Remove default port
        if netloc.endswith(":80") and scheme == "http":
            netloc = netloc[:-3]
        elif netloc.endswith(":443") and scheme == "https":
            netloc = netloc[:-4]

        # 5. Normalize path
        path = parsed.path
        # Remove trailing slash (except for root)
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        # Remove duplicate slashes
        path = re.sub(r"/+", "/", path)

        # 6. Handle query parameters
        query = parsed.query
        removed_params = []
        if query and self.remove_tracking_params:
            try:
                params = parse_qs(query, keep_blank_values=True)
                new_params = {}
                for key, values in params.items():
                    key_lower = key.lower()
                    if key_lower in TRACKING_PARAMS:
                        removed_params.append(key)
                        continue
                    if self.keep_content_params or key_lower in CONTENT_PARAMS:
                        new_params[key] = values
                    else:
                        removed_params.append(key)
                # Rebuild query string (sorted for consistency)
                query = urlencode(new_params, doseq=True)
            except Exception:
                pass

        # 7. Remove fragment
        fragment = ""
        if not self.remove_fragment:
            fragment = parsed.fragment

        # 8. Rebuild URL
        normalized = urlunparse((scheme, netloc, path, "", query, fragment))

        # 9. Handle canonical URL
        canonical_url = None
        if canonical_hint:
            canonical_url = self._validate_canonical(canonical_hint, normalized)

        # 10. Generate hash
        url_hash = self._hash_url(normalized)

        return URLNormalizationResult(
            original_url=original_url,
            normalized_url=normalized,
            canonical_url=canonical_url,
            url_hash=url_hash,
            domain=netloc,
            path=path,
            removed_params=removed_params,
        )

    def _validate_canonical(
        self,
        canonical: str,
        original: str,
    ) -> Optional[str]:
        """Validate that canonical URL is reasonable"""
        try:
            canonical_parsed = urlparse(canonical)
            original_parsed = urlparse(original)

            # Should be same domain or subdomain
            if canonical_parsed.netloc and original_parsed.netloc:
                canonical_domain = canonical_parsed.netloc.lower()
                original_domain = original_parsed.netloc.lower()
                if not (
                    canonical_domain == original_domain
                    or canonical_domain.endswith("." + original_domain)
                    or original_domain.endswith("." + canonical_domain)
                ):
                    return None

            return canonical
        except Exception:
            return None

    def _hash_url(self, url: str) -> str:
        """Generate SHA256 hash of URL"""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


class ContentDeduplicator:
    """
    Content deduplication using multiple strategies.
    内容去重 - 使用多种策略
    """

    def __init__(
        self,
        exact_match_threshold: float = 1.0,
        simhash_threshold: int = 3,  # Hamming distance threshold
        minhash_threshold: float = 0.8,
    ):
        self.exact_match_threshold = exact_match_threshold
        self.simhash_threshold = simhash_threshold
        self.minhash_threshold = minhash_threshold

    def compute_content_hash(self, content: str) -> str:
        """
        Compute SHA256 hash of normalized content.
        计算规范化内容的 SHA256 哈希
        """
        normalized = self._normalize_content(content)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def compute_simhash(self, content: str) -> str:
        """
        Compute SimHash for near-duplicate detection.
        计算 SimHash 用于近似去重
        """
        normalized = self._normalize_content(content)
        tokens = self._tokenize(normalized)

        # Compute hash for each token and combine
        v = [0] * 64
        for token in tokens:
            token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)
            for i in range(64):
                bit = (token_hash >> i) & 1
                v[i] += 1 if bit else -1

        # Generate final hash
        fingerprint = 0
        for i in range(64):
            if v[i] >= 0:
                fingerprint |= (1 << i)

        return format(fingerprint, "016x")

    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two SimHash values.
        计算两个 SimHash 的汉明距离
        """
        try:
            h1 = int(hash1, 16)
            h2 = int(hash2, 16)
            return bin(h1 ^ h2).count("1")
        except Exception:
            return 64  # Maximum distance

    def is_duplicate(
        self,
        content1: str,
        content2: str,
    ) -> Tuple[bool, str]:
        """
        Check if two pieces of content are duplicates.
        判断两段内容是否重复

        Returns:
            Tuple of (is_duplicate, duplicate_type)
            duplicate_type: "exact", "near", or "none"
        """
        # Exact match
        hash1 = self.compute_content_hash(content1)
        hash2 = self.compute_content_hash(content2)
        if hash1 == hash2:
            return True, "exact"

        # Near duplicate check using SimHash
        sim1 = self.compute_simhash(content1)
        sim2 = self.compute_simhash(content2)
        distance = self.hamming_distance(sim1, sim2)
        if distance <= self.simhash_threshold:
            return True, "near"

        return False, "none"

    def _normalize_content(self, content: str) -> str:
        """Normalize content for hashing"""
        if not content:
            return ""

        # Remove extra whitespace
        content = re.sub(r"\s+", " ", content)
        # Remove punctuation (keep Chinese characters)
        content = re.sub(r"[^\w\s\u4e00-\u9fff]", "", content)
        # Lowercase
        content = content.lower()
        # Strip
        content = content.strip()

        return content

    def _tokenize(self, content: str) -> List[str]:
        """Tokenize content for SimHash"""
        # Simple character-based tokenization for Chinese
        # For production, consider using jieba
        tokens = []

        # Chinese character n-grams
        for i in range(len(content) - 1):
            tokens.append(content[i:i+2])

        # Also add individual characters
        tokens.extend(list(content))

        return tokens


@dataclass
class DeduplicationResult:
    """Result of deduplication check"""
    is_duplicate: bool
    duplicate_type: str  # exact, near, none
    existing_doc_id: Optional[str] = None
    similarity_score: float = 0.0


class EvidenceDeduplicator:
    """
    Combined URL and content deduplication for evidence.
    证据去重器 - 结合 URL 和内容去重
    """

    def __init__(self):
        self.url_normalizer = URLNormalizer()
        self.content_deduper = ContentDeduplicator()

        # In-memory cache (replace with Redis in production)
        self._url_hash_cache: Dict[str, str] = {}  # url_hash -> doc_id
        self._content_hash_cache: Dict[str, str] = {}  # content_hash -> doc_id
        self._simhash_index: List[Tuple[str, str]] = []  # [(simhash, doc_id), ...]

    async def check_duplicate(
        self,
        url: str,
        content: str,
        canonical_hint: Optional[str] = None,
    ) -> DeduplicationResult:
        """
        Check if evidence is a duplicate.
        检查证据是否重复

        Args:
            url: Evidence URL
            content: Evidence content
            canonical_hint: Optional canonical URL from HTML

        Returns:
            DeduplicationResult with duplicate status
        """
        # 1. Normalize URL
        url_result = self.url_normalizer.normalize(url, canonical_hint)
        url_hash = url_result.url_hash

        # 2. Check URL exact match
        if url_hash in self._url_hash_cache:
            return DeduplicationResult(
                is_duplicate=True,
                duplicate_type="exact_url",
                existing_doc_id=self._url_hash_cache[url_hash],
                similarity_score=1.0,
            )

        # 3. Check canonical URL if available
        if url_result.canonical_url:
            canonical_norm = self.url_normalizer.normalize(url_result.canonical_url)
            if canonical_norm.url_hash in self._url_hash_cache:
                return DeduplicationResult(
                    is_duplicate=True,
                    duplicate_type="canonical_match",
                    existing_doc_id=self._url_hash_cache[canonical_norm.url_hash],
                    similarity_score=1.0,
                )

        # 4. Check content hash
        if content:
            content_hash = self.content_deduper.compute_content_hash(content)
            if content_hash in self._content_hash_cache:
                return DeduplicationResult(
                    is_duplicate=True,
                    duplicate_type="exact_content",
                    existing_doc_id=self._content_hash_cache[content_hash],
                    similarity_score=1.0,
                )

            # 5. Check near-duplicate using SimHash
            simhash = self.content_deduper.compute_simhash(content)
            for existing_simhash, existing_doc_id in self._simhash_index:
                distance = self.content_deduper.hamming_distance(simhash, existing_simhash)
                if distance <= 3:  # Threshold
                    similarity = 1.0 - (distance / 64.0)
                    return DeduplicationResult(
                        is_duplicate=True,
                        duplicate_type="near_duplicate",
                        existing_doc_id=existing_doc_id,
                        similarity_score=similarity,
                    )

        return DeduplicationResult(
            is_duplicate=False,
            duplicate_type="none",
            similarity_score=0.0,
        )

    async def register_evidence(
        self,
        doc_id: str,
        url: str,
        content: str,
        canonical_hint: Optional[str] = None,
    ) -> None:
        """
        Register new evidence in deduplication index.
        在去重索引中注册新证据
        """
        # Normalize and register URL
        url_result = self.url_normalizer.normalize(url, canonical_hint)
        self._url_hash_cache[url_result.url_hash] = doc_id

        if url_result.canonical_url:
            canonical_norm = self.url_normalizer.normalize(url_result.canonical_url)
            self._url_hash_cache[canonical_norm.url_hash] = doc_id

        # Register content
        if content:
            content_hash = self.content_deduper.compute_content_hash(content)
            self._content_hash_cache[content_hash] = doc_id

            simhash = self.content_deduper.compute_simhash(content)
            self._simhash_index.append((simhash, doc_id))

    def get_stats(self) -> Dict[str, int]:
        """Get deduplication index statistics"""
        return {
            "url_hashes": len(self._url_hash_cache),
            "content_hashes": len(self._content_hash_cache),
            "simhash_entries": len(self._simhash_index),
        }


# Utility functions
def normalize_url(url: str, canonical: Optional[str] = None) -> str:
    """Simple URL normalization utility"""
    normalizer = URLNormalizer()
    result = normalizer.normalize(url, canonical)
    return result.normalized_url


def compute_content_hash(content: str) -> str:
    """Simple content hash utility"""
    deduper = ContentDeduplicator()
    return deduper.compute_content_hash(content)


def compute_simhash(content: str) -> str:
    """Simple SimHash utility"""
    deduper = ContentDeduplicator()
    return deduper.compute_simhash(content)