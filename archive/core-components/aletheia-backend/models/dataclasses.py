"""
Core data models using dataclasses for the Aletheia system optimization.
These models represent the business logic entities used throughout the system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class Platform(str, Enum):
    """Supported platforms"""
    TWITTER = "twitter"
    WEIBO = "weibo"
    REDDIT = "reddit"
    ZHIHU = "zhihu"
    XIAOHONGSHU = "xiaohongshu"
    BILIBILI = "bilibili"
    DOUYIN = "douyin"
    WECHAT = "wechat"


class ContentType(str, Enum):
    """Content types"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MIXED = "mixed"


@dataclass
class Account:
    """
    Social media account model.
    Represents a user account on a social media platform.
    """
    account_id: str
    platform: Platform
    username: str
    created_at: datetime
    follower_count: int
    following_count: int
    post_count: int
    verified: bool = False
    bio: Optional[str] = None
    profile_image_url: Optional[str] = None
    location: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate account data"""
        if self.follower_count < 0:
            raise ValueError("follower_count must be non-negative")
        if self.following_count < 0:
            raise ValueError("following_count must be non-negative")
        if self.post_count < 0:
            raise ValueError("post_count must be non-negative")


@dataclass
class Post:
    """
    Social media post model.
    Represents a single post/tweet/status update.
    """
    post_id: str
    platform: Platform
    author_id: str
    content: str
    content_type: ContentType
    created_at: datetime
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    view_count: int = 0
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    media_urls: List[str] = field(default_factory=list)
    parent_post_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate post data"""
        if self.like_count < 0:
            raise ValueError("like_count must be non-negative")
        if self.comment_count < 0:
            raise ValueError("comment_count must be non-negative")
        if self.share_count < 0:
            raise ValueError("share_count must be non-negative")
        if self.view_count < 0:
            raise ValueError("view_count must be non-negative")
    
    @property
    def engagement_rate(self) -> float:
        """Calculate engagement rate"""
        if self.view_count == 0:
            return 0.0
        total_engagement = self.like_count + self.comment_count + self.share_count
        return total_engagement / self.view_count


@dataclass
class BotFeatures:
    """
    Features extracted for bot detection.
    """
    account_age_days: float
    posting_frequency: float  # posts per day
    interaction_ratio: float  # (likes + comments) / posts
    content_similarity: float  # 0-1, average similarity between posts
    profile_completeness: float  # 0-1, how complete the profile is
    temporal_entropy: float  # entropy of posting times
    follower_following_ratio: float
    verified_status: bool
    
    def __post_init__(self):
        """Validate features"""
        if not 0 <= self.content_similarity <= 1:
            raise ValueError("content_similarity must be between 0 and 1")
        if not 0 <= self.profile_completeness <= 1:
            raise ValueError("profile_completeness must be between 0 and 1")
        if self.temporal_entropy < 0:
            raise ValueError("temporal_entropy must be non-negative")


@dataclass
class BotScore:
    """
    Bot detection result for an account.
    """
    account_id: str
    platform: Platform
    bot_probability: float  # 0-1, probability of being a bot
    features: BotFeatures
    confidence: str  # HIGH, MEDIUM, LOW
    detected_at: datetime
    model_version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate bot score"""
        if not 0 <= self.bot_probability <= 1:
            raise ValueError("bot_probability must be between 0 and 1")
        if self.confidence not in ["HIGH", "MEDIUM", "LOW"]:
            raise ValueError("confidence must be HIGH, MEDIUM, or LOW")
    
    @property
    def is_bot(self) -> bool:
        """Check if account is likely a bot (threshold: 0.7)"""
        return self.bot_probability >= 0.7


@dataclass
class CIBCluster:
    """
    Coordinated Inauthentic Behavior cluster.
    Represents a group of accounts exhibiting coordinated behavior.
    """
    cluster_id: str
    account_ids: List[str]
    platform: Platform
    cluster_score: float  # 0-1, strength of coordination
    behavior_patterns: Dict[str, Any]
    detected_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate CIB cluster"""
        if not 0 <= self.cluster_score <= 1:
            raise ValueError("cluster_score must be between 0 and 1")
        if len(self.account_ids) < 2:
            raise ValueError("CIB cluster must contain at least 2 accounts")


@dataclass
class FakeNewsPrediction:
    """
    Fake news detection model prediction.
    Contains predictions from multiple ML algorithms.
    """
    text_hash: str
    logistic_regression_score: float
    decision_tree_score: float
    gradient_boost_score: float
    random_forest_score: float
    ensemble_score: float  # weighted average
    confidence: float
    predicted_at: datetime
    model_version: str = "1.0"
    
    def __post_init__(self):
        """Validate predictions"""
        scores = [
            self.logistic_regression_score,
            self.decision_tree_score,
            self.gradient_boost_score,
            self.random_forest_score,
            self.ensemble_score,
            self.confidence
        ]
        for score in scores:
            if not 0 <= score <= 1:
                raise ValueError(f"All scores must be between 0 and 1, got {score}")


@dataclass
class VerificationResult:
    """
    Final verification result combining multiple analysis methods.
    """
    content_id: str
    content_text: str
    credibility_score: float  # 0-1, final credibility assessment
    credibility_level: str  # VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW
    confidence: str  # HIGH, MEDIUM, LOW
    risk_flags: List[str] = field(default_factory=list)
    reasoning_chain: List[str] = field(default_factory=list)
    fake_news_prediction: Optional[FakeNewsPrediction] = None
    bot_scores: List[BotScore] = field(default_factory=list)
    physics_verification: Optional[Dict[str, Any]] = None
    logic_verification: Optional[Dict[str, Any]] = None
    entropy_analysis: Optional[Dict[str, Any]] = None
    verified_at: datetime = field(default_factory=datetime.utcnow)
    processing_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate verification result"""
        if not 0 <= self.credibility_score <= 1:
            raise ValueError("credibility_score must be between 0 and 1")
        valid_levels = ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"]
        if self.credibility_level not in valid_levels:
            raise ValueError(f"credibility_level must be one of {valid_levels}")
        if self.confidence not in ["HIGH", "MEDIUM", "LOW"]:
            raise ValueError("confidence must be HIGH, MEDIUM, or LOW")


@dataclass
class CrawlConfig:
    """
    Configuration for crawling operations.
    """
    platform: Platform
    max_depth: int = 3
    max_pages: int = 100
    max_retries: int = 5
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    timeout: int = 30  # seconds
    user_agents: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    proxy: Optional[str] = None
    validate_schema: bool = True
    collect_metadata: bool = True
    follow_links: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate crawl config"""
        if self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.base_delay < 0:
            raise ValueError("base_delay must be non-negative")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if self.exponential_base < 1:
            raise ValueError("exponential_base must be >= 1")
        if self.timeout < 1:
            raise ValueError("timeout must be at least 1 second")


@dataclass
class CrawlMetrics:
    """
    Metrics for a crawl operation.
    """
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    retried_requests: int = 0
    pages_crawled: int = 0
    items_collected: int = 0
    validation_failures: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    @property
    def coverage(self) -> float:
        """Calculate coverage (pages crawled / total requests)"""
        if self.total_requests == 0:
            return 0.0
        return self.pages_crawled / self.total_requests
    
    @property
    def quality_score(self) -> float:
        """Calculate quality score based on validation success"""
        if self.items_collected == 0:
            return 0.0
        valid_items = self.items_collected - self.validation_failures
        return valid_items / self.items_collected
    
    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds"""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()


@dataclass
class RetryStrategy:
    """
    Retry strategy configuration with exponential backoff.
    """
    max_attempts: int = 5
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_range: float = 0.1  # +/- 10% jitter
    
    def __post_init__(self):
        """Validate retry strategy"""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay < 0:
            raise ValueError("base_delay must be non-negative")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if self.exponential_base < 1:
            raise ValueError("exponential_base must be >= 1")
        if not 0 <= self.jitter_range <= 1:
            raise ValueError("jitter_range must be between 0 and 1")
    
    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt number.
        Formula: min(base_delay * (exponential_base ^ attempt) + jitter, max_delay)
        """
        import random
        
        if attempt < 0:
            raise ValueError("attempt must be non-negative")
        
        # Calculate base delay with exponential backoff
        delay = self.base_delay * (self.exponential_base ** attempt)
        
        # Add jitter if enabled
        if self.jitter:
            jitter_amount = delay * self.jitter_range
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        # Cap at max_delay
        return min(delay, self.max_delay)
