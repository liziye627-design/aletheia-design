"""
Unit tests for core data models.
Tests validation logic and basic functionality of dataclasses.

Feature: aletheia-system-optimization
"""

import pytest
from datetime import datetime
from hypothesis import given, assume
from hypothesis import strategies as st

from models.dataclasses import (
    Account,
    Post,
    BotFeatures,
    BotScore,
    CIBCluster,
    FakeNewsPrediction,
    VerificationResult,
    CrawlConfig,
    CrawlMetrics,
    RetryStrategy,
    Platform,
    ContentType,
)
from tests.strategies import (
    account_strategy,
    post_strategy,
    bot_features_strategy,
    bot_score_strategy,
    cib_cluster_strategy,
    fake_news_prediction_strategy,
    verification_result_strategy,
    crawl_config_strategy,
    retry_strategy_strategy,
)


# ==========================================
# Account Model Tests
# ==========================================

class TestAccount:
    """Tests for Account dataclass"""
    
    def test_account_creation_with_valid_data(self, sample_account_data):
        """Test creating an account with valid data"""
        account = Account(**sample_account_data)
        assert account.account_id == sample_account_data["account_id"]
        assert account.platform == sample_account_data["platform"]
        assert account.follower_count == sample_account_data["follower_count"]
    
    def test_account_negative_follower_count_raises_error(self, sample_account_data):
        """Test that negative follower count raises ValueError"""
        sample_account_data["follower_count"] = -1
        with pytest.raises(ValueError, match="follower_count must be non-negative"):
            Account(**sample_account_data)
    
    def test_account_negative_following_count_raises_error(self, sample_account_data):
        """Test that negative following count raises ValueError"""
        sample_account_data["following_count"] = -1
        with pytest.raises(ValueError, match="following_count must be non-negative"):
            Account(**sample_account_data)
    
    def test_account_negative_post_count_raises_error(self, sample_account_data):
        """Test that negative post count raises ValueError"""
        sample_account_data["post_count"] = -1
        with pytest.raises(ValueError, match="post_count must be non-negative"):
            Account(**sample_account_data)
    
    @pytest.mark.property
    @given(account=account_strategy)
    def test_account_property_all_counts_non_negative(self, account):
        """
        Property test: All count fields must be non-negative.
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        """
        assert account.follower_count >= 0
        assert account.following_count >= 0
        assert account.post_count >= 0


# ==========================================
# Post Model Tests
# ==========================================

class TestPost:
    """Tests for Post dataclass"""
    
    def test_post_creation_with_valid_data(self, sample_post_data):
        """Test creating a post with valid data"""
        post = Post(**sample_post_data)
        assert post.post_id == sample_post_data["post_id"]
        assert post.content == sample_post_data["content"]
        assert post.like_count == sample_post_data["like_count"]
    
    def test_post_engagement_rate_calculation(self, sample_post_data):
        """Test engagement rate calculation"""
        post = Post(**sample_post_data)
        expected_rate = (10 + 5 + 2) / 100  # (likes + comments + shares) / views
        assert post.engagement_rate == expected_rate
    
    def test_post_engagement_rate_zero_views(self, sample_post_data):
        """Test engagement rate with zero views"""
        sample_post_data["view_count"] = 0
        post = Post(**sample_post_data)
        assert post.engagement_rate == 0.0
    
    def test_post_negative_like_count_raises_error(self, sample_post_data):
        """Test that negative like count raises ValueError"""
        sample_post_data["like_count"] = -1
        with pytest.raises(ValueError, match="like_count must be non-negative"):
            Post(**sample_post_data)
    
    @pytest.mark.property
    @given(post=post_strategy)
    def test_post_property_all_counts_non_negative(self, post):
        """
        Property test: All engagement counts must be non-negative.
        Feature: aletheia-system-optimization
        """
        assert post.like_count >= 0
        assert post.comment_count >= 0
        assert post.share_count >= 0
        assert post.view_count >= 0
    
    @pytest.mark.property
    @given(post=post_strategy)
    def test_post_property_engagement_rate_valid(self, post):
        """
        Property test: Engagement rate must be non-negative.
        Feature: aletheia-system-optimization
        """
        assert post.engagement_rate >= 0.0


# ==========================================
# BotFeatures Model Tests
# ==========================================

class TestBotFeatures:
    """Tests for BotFeatures dataclass"""
    
    def test_bot_features_creation_with_valid_data(self, sample_bot_features):
        """Test creating bot features with valid data"""
        features = BotFeatures(**sample_bot_features)
        assert features.account_age_days == sample_bot_features["account_age_days"]
        assert features.posting_frequency == sample_bot_features["posting_frequency"]
    
    def test_bot_features_invalid_content_similarity(self, sample_bot_features):
        """Test that content similarity outside [0,1] raises ValueError"""
        sample_bot_features["content_similarity"] = 1.5
        with pytest.raises(ValueError, match="content_similarity must be between 0 and 1"):
            BotFeatures(**sample_bot_features)
    
    def test_bot_features_invalid_profile_completeness(self, sample_bot_features):
        """Test that profile completeness outside [0,1] raises ValueError"""
        sample_bot_features["profile_completeness"] = -0.1
        with pytest.raises(ValueError, match="profile_completeness must be between 0 and 1"):
            BotFeatures(**sample_bot_features)
    
    @pytest.mark.property
    @given(features=bot_features_strategy)
    def test_bot_features_property_scores_in_range(self, features):
        """
        Property test: Similarity and completeness scores must be in [0,1].
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        assert 0.0 <= features.content_similarity <= 1.0
        assert 0.0 <= features.profile_completeness <= 1.0
        assert features.temporal_entropy >= 0.0


# ==========================================
# BotScore Model Tests
# ==========================================

class TestBotScore:
    """Tests for BotScore dataclass"""
    
    def test_bot_score_creation_with_valid_data(self, sample_bot_features):
        """Test creating a bot score with valid data"""
        features = BotFeatures(**sample_bot_features)
        bot_score = BotScore(
            account_id="test_123",
            platform=Platform.TWITTER,
            bot_probability=0.75,
            features=features,
            confidence="HIGH",
            detected_at=datetime.now(),
        )
        assert bot_score.bot_probability == 0.75
        assert bot_score.is_bot is True  # >= 0.7 threshold
    
    def test_bot_score_invalid_probability(self, sample_bot_features):
        """Test that bot probability outside [0,1] raises ValueError"""
        features = BotFeatures(**sample_bot_features)
        with pytest.raises(ValueError, match="bot_probability must be between 0 and 1"):
            BotScore(
                account_id="test_123",
                platform=Platform.TWITTER,
                bot_probability=1.5,
                features=features,
                confidence="HIGH",
                detected_at=datetime.now(),
            )
    
    def test_bot_score_invalid_confidence(self, sample_bot_features):
        """Test that invalid confidence raises ValueError"""
        features = BotFeatures(**sample_bot_features)
        with pytest.raises(ValueError, match="confidence must be HIGH, MEDIUM, or LOW"):
            BotScore(
                account_id="test_123",
                platform=Platform.TWITTER,
                bot_probability=0.5,
                features=features,
                confidence="INVALID",
                detected_at=datetime.now(),
            )
    
    def test_bot_score_is_bot_threshold(self, sample_bot_features):
        """Test is_bot property with different thresholds"""
        features = BotFeatures(**sample_bot_features)
        
        # Below threshold
        bot_score_low = BotScore(
            account_id="test_123",
            platform=Platform.TWITTER,
            bot_probability=0.6,
            features=features,
            confidence="MEDIUM",
            detected_at=datetime.now(),
        )
        assert bot_score_low.is_bot is False
        
        # At threshold
        bot_score_threshold = BotScore(
            account_id="test_123",
            platform=Platform.TWITTER,
            bot_probability=0.7,
            features=features,
            confidence="HIGH",
            detected_at=datetime.now(),
        )
        assert bot_score_threshold.is_bot is True
    
    @pytest.mark.property
    @given(bot_score=bot_score_strategy)
    def test_bot_score_property_probability_in_range(self, bot_score):
        """
        Property test: Bot probability must be in [0,1].
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        assert 0.0 <= bot_score.bot_probability <= 1.0
        assert bot_score.confidence in ["HIGH", "MEDIUM", "LOW"]


# ==========================================
# CIBCluster Model Tests
# ==========================================

class TestCIBCluster:
    """Tests for CIBCluster dataclass"""
    
    def test_cib_cluster_creation_with_valid_data(self):
        """Test creating a CIB cluster with valid data"""
        cluster = CIBCluster(
            cluster_id="cluster_123",
            account_ids=["acc1", "acc2", "acc3"],
            platform=Platform.TWITTER,
            cluster_score=0.85,
            behavior_patterns={"similarity": 0.9},
            detected_at=datetime.now(),
        )
        assert len(cluster.account_ids) == 3
        assert cluster.cluster_score == 0.85
    
    def test_cib_cluster_invalid_score(self):
        """Test that cluster score outside [0,1] raises ValueError"""
        with pytest.raises(ValueError, match="cluster_score must be between 0 and 1"):
            CIBCluster(
                cluster_id="cluster_123",
                account_ids=["acc1", "acc2"],
                platform=Platform.TWITTER,
                cluster_score=1.5,
                behavior_patterns={},
                detected_at=datetime.now(),
            )
    
    def test_cib_cluster_insufficient_accounts(self):
        """Test that cluster with < 2 accounts raises ValueError"""
        with pytest.raises(ValueError, match="CIB cluster must contain at least 2 accounts"):
            CIBCluster(
                cluster_id="cluster_123",
                account_ids=["acc1"],
                platform=Platform.TWITTER,
                cluster_score=0.8,
                behavior_patterns={},
                detected_at=datetime.now(),
            )
    
    @pytest.mark.property
    @given(cluster=cib_cluster_strategy)
    def test_cib_cluster_property_valid_structure(self, cluster):
        """
        Property test: CIB cluster must have valid structure.
        Feature: aletheia-system-optimization, Property 2: CIB Cluster Detection
        **Validates: Requirements 1.3**
        """
        assert len(cluster.account_ids) >= 2
        assert 0.0 <= cluster.cluster_score <= 1.0
        assert len(cluster.behavior_patterns) > 0


# ==========================================
# FakeNewsPrediction Model Tests
# ==========================================

class TestFakeNewsPrediction:
    """Tests for FakeNewsPrediction dataclass"""
    
    def test_fake_news_prediction_creation(self):
        """Test creating a fake news prediction with valid data"""
        prediction = FakeNewsPrediction(
            text_hash="abc123",
            logistic_regression_score=0.7,
            decision_tree_score=0.6,
            gradient_boost_score=0.8,
            random_forest_score=0.75,
            ensemble_score=0.72,
            confidence=0.85,
            predicted_at=datetime.now(),
        )
        assert prediction.ensemble_score == 0.72
    
    def test_fake_news_prediction_invalid_score(self):
        """Test that score outside [0,1] raises ValueError"""
        with pytest.raises(ValueError, match="All scores must be between 0 and 1"):
            FakeNewsPrediction(
                text_hash="abc123",
                logistic_regression_score=1.5,
                decision_tree_score=0.6,
                gradient_boost_score=0.8,
                random_forest_score=0.75,
                ensemble_score=0.72,
                confidence=0.85,
                predicted_at=datetime.now(),
            )
    
    @pytest.mark.property
    @given(prediction=fake_news_prediction_strategy)
    def test_fake_news_prediction_property_all_scores_valid(self, prediction):
        """
        Property test: All prediction scores must be in [0,1].
        Feature: aletheia-system-optimization, Property 11: Fake News Model Response Completeness
        **Validates: Requirements 3.3**
        """
        assert 0.0 <= prediction.logistic_regression_score <= 1.0
        assert 0.0 <= prediction.decision_tree_score <= 1.0
        assert 0.0 <= prediction.gradient_boost_score <= 1.0
        assert 0.0 <= prediction.random_forest_score <= 1.0
        assert 0.0 <= prediction.ensemble_score <= 1.0
        assert 0.0 <= prediction.confidence <= 1.0


# ==========================================
# VerificationResult Model Tests
# ==========================================

class TestVerificationResult:
    """Tests for VerificationResult dataclass"""
    
    def test_verification_result_creation(self):
        """Test creating a verification result with valid data"""
        result = VerificationResult(
            content_id="content_123",
            content_text="Test content",
            credibility_score=0.75,
            credibility_level="HIGH",
            confidence="HIGH",
        )
        assert result.credibility_score == 0.75
        assert result.credibility_level == "HIGH"
    
    def test_verification_result_invalid_score(self):
        """Test that credibility score outside [0,1] raises ValueError"""
        with pytest.raises(ValueError, match="credibility_score must be between 0 and 1"):
            VerificationResult(
                content_id="content_123",
                content_text="Test content",
                credibility_score=1.5,
                credibility_level="HIGH",
                confidence="HIGH",
            )
    
    def test_verification_result_invalid_level(self):
        """Test that invalid credibility level raises ValueError"""
        with pytest.raises(ValueError):
            VerificationResult(
                content_id="content_123",
                content_text="Test content",
                credibility_score=0.75,
                credibility_level="INVALID",
                confidence="HIGH",
            )
    
    @pytest.mark.property
    @given(result=verification_result_strategy)
    def test_verification_result_property_valid_structure(self, result):
        """
        Property test: Verification result must have valid structure.
        Feature: aletheia-system-optimization, Property 12: Credibility Score Aggregation
        **Validates: Requirements 3.4**
        """
        assert 0.0 <= result.credibility_score <= 1.0
        assert result.credibility_level in ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"]
        assert result.confidence in ["HIGH", "MEDIUM", "LOW"]
        assert result.processing_time_ms >= 0


# ==========================================
# CrawlConfig Model Tests
# ==========================================

class TestCrawlConfig:
    """Tests for CrawlConfig dataclass"""
    
    def test_crawl_config_creation(self, sample_crawl_config):
        """Test creating crawl config with valid data"""
        config = CrawlConfig(**sample_crawl_config)
        assert config.max_depth == 3
        assert config.max_retries == 5
    
    def test_crawl_config_invalid_max_delay(self, sample_crawl_config):
        """Test that max_delay < base_delay raises ValueError"""
        sample_crawl_config["max_delay"] = 0.5
        with pytest.raises(ValueError, match="max_delay must be >= base_delay"):
            CrawlConfig(**sample_crawl_config)
    
    @pytest.mark.property
    @given(config=crawl_config_strategy)
    def test_crawl_config_property_valid_delays(self, config):
        """
        Property test: Delay configuration must be valid.
        Feature: aletheia-system-optimization, Property 5: Exponential Backoff Retry
        **Validates: Requirements 2.1**
        """
        assert config.base_delay >= 0
        assert config.max_delay >= config.base_delay
        assert config.exponential_base >= 1
        assert config.max_retries >= 0


# ==========================================
# RetryStrategy Model Tests
# ==========================================

class TestRetryStrategy:
    """Tests for RetryStrategy dataclass"""
    
    def test_retry_strategy_creation(self, sample_retry_strategy):
        """Test creating retry strategy with valid data"""
        strategy = RetryStrategy(**sample_retry_strategy)
        assert strategy.max_attempts == 5
        assert strategy.base_delay == 1.0
    
    def test_retry_strategy_get_delay(self, sample_retry_strategy):
        """Test delay calculation"""
        strategy = RetryStrategy(**sample_retry_strategy)
        
        # Test delay increases exponentially
        delay_0 = strategy.get_delay(0)
        delay_1 = strategy.get_delay(1)
        delay_2 = strategy.get_delay(2)
        
        # Delays should generally increase (accounting for jitter)
        assert delay_0 <= strategy.max_delay
        assert delay_1 <= strategy.max_delay
        assert delay_2 <= strategy.max_delay
    
    def test_retry_strategy_get_delay_caps_at_max(self, sample_retry_strategy):
        """Test that delay is capped at max_delay"""
        strategy = RetryStrategy(**sample_retry_strategy)
        
        # Large attempt number should be capped
        delay = strategy.get_delay(100)
        assert delay <= strategy.max_delay
    
    def test_retry_strategy_get_delay_negative_attempt_raises_error(self, sample_retry_strategy):
        """Test that negative attempt raises ValueError"""
        strategy = RetryStrategy(**sample_retry_strategy)
        with pytest.raises(ValueError, match="attempt must be non-negative"):
            strategy.get_delay(-1)
    
    @pytest.mark.property
    @given(strategy=retry_strategy_strategy, attempt=st.integers(min_value=0, max_value=20))
    def test_retry_strategy_property_delay_bounded(self, strategy, attempt):
        """
        Property test: Delay must be bounded by max_delay.
        Feature: aletheia-system-optimization, Property 5: Exponential Backoff Retry
        **Validates: Requirements 2.1**
        """
        delay = strategy.get_delay(attempt)
        assert 0 <= delay <= strategy.max_delay


# ==========================================
# CrawlMetrics Model Tests
# ==========================================

class TestCrawlMetrics:
    """Tests for CrawlMetrics dataclass"""
    
    def test_crawl_metrics_success_rate(self):
        """Test success rate calculation"""
        metrics = CrawlMetrics(
            total_requests=100,
            successful_requests=80,
            failed_requests=20,
        )
        assert metrics.success_rate == 0.8
    
    def test_crawl_metrics_success_rate_zero_requests(self):
        """Test success rate with zero requests"""
        metrics = CrawlMetrics()
        assert metrics.success_rate == 0.0
    
    def test_crawl_metrics_quality_score(self):
        """Test quality score calculation"""
        metrics = CrawlMetrics(
            items_collected=100,
            validation_failures=10,
        )
        assert metrics.quality_score == 0.9
    
    def test_crawl_metrics_duration(self):
        """Test duration calculation"""
        start = datetime(2025, 2, 8, 12, 0, 0)
        end = datetime(2025, 2, 8, 12, 5, 30)
        metrics = CrawlMetrics(
            start_time=start,
            end_time=end,
        )
        assert metrics.duration_seconds == 330.0  # 5 minutes 30 seconds
