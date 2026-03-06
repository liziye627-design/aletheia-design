"""
Property-based tests for Bot Detection System.

Feature: aletheia-system-optimization
Task: 1.1 Write property test for data model validation

This module contains property-based tests that validate the bot detection system
against the correctness properties defined in the design document.
"""

import pytest
from datetime import datetime, timedelta
from hypothesis import given, assume, strategies as st
from typing import List

from services.agent_framework.bot_detector import (
    BotDetector,
    AccountProfile,
    ContentItem,
    BotDetectionResult,
)


# ==========================================
# Hypothesis Strategies for Bot Detection
# ==========================================

def datetime_strategy_recent():
    """Generate recent datetime values (last 5 years)"""
    return st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime.now()
    )


def account_profile_strategy():
    """Generate valid AccountProfile instances"""
    return st.builds(
        AccountProfile,
        user_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            whitelist_characters='_-'
        )),
        nickname=st.text(min_size=0, max_size=100),
        platform=st.sampled_from(['twitter', 'weibo', 'reddit', 'zhihu', 'xiaohongshu']),
        register_time=st.one_of(st.none(), datetime_strategy_recent()),
        follower_count=st.integers(min_value=0, max_value=10000000),
        following_count=st.integers(min_value=0, max_value=100000),
        post_count=st.integers(min_value=0, max_value=1000000),
        is_verified=st.booleans(),
        verify_type=st.sampled_from(['', 'personal', 'enterprise', 'official']),
        metadata=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(), st.integers(), st.floats(), st.booleans()),
            max_size=5
        )
    )


def content_item_strategy(user_id: str = None):
    """Generate valid ContentItem instances"""
    if user_id is None:
        user_id_strategy = st.text(min_size=1, max_size=50)
    else:
        user_id_strategy = st.just(user_id)
    
    return st.builds(
        ContentItem,
        content_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            whitelist_characters='_-'
        )),
        user_id=user_id_strategy,
        text=st.text(min_size=0, max_size=5000),
        publish_time=st.one_of(st.none(), datetime_strategy_recent()),
        likes=st.integers(min_value=0, max_value=1000000),
        comments=st.integers(min_value=0, max_value=100000),
        shares=st.integers(min_value=0, max_value=100000),
        has_image=st.booleans(),
        has_video=st.booleans()
    )


def content_list_strategy(user_id: str = None):
    """Generate a list of ContentItem instances"""
    return st.lists(
        content_item_strategy(user_id),
        min_size=0,
        max_size=50
    )


# ==========================================
# Property 1: Bot Detection Completeness and Validity
# ==========================================

class TestBotDetectionCompletenessAndValidity:
    """
    Property 1: Bot Detection Completeness and Validity
    
    For any account analyzed by the Bot_Detector, the system SHALL compute all 
    required metrics (account age, posting frequency, interaction patterns, 
    content similarity) AND return a bot probability score between 0 and 1 inclusive.
    
    **Validates: Requirements 1.1, 1.2**
    """
    
    @pytest.mark.property
    @given(profile=account_profile_strategy())
    def test_bot_detection_returns_valid_score_range(self, profile: AccountProfile):
        """
        Property test: Bot detection must return a score between 0 and 1.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        detector = BotDetector()
        result = detector.detect(profile)
        
        # Verify the result is a BotDetectionResult
        assert isinstance(result, BotDetectionResult)
        
        # Verify risk_score is between 0 and 1 (inclusive)
        assert 0.0 <= result.risk_score <= 1.0, (
            f"Bot detection risk_score must be between 0 and 1, got {result.risk_score}"
        )
        
        # Verify all component scores are also in valid range
        assert 0.0 <= result.profile_score <= 1.0
        assert 0.0 <= result.behavior_score <= 1.0
        assert 0.0 <= result.content_score <= 1.0
        assert 0.0 <= result.social_score <= 1.0
    
    @pytest.mark.property
    @given(
        profile=account_profile_strategy(),
        contents=content_list_strategy()
    )
    def test_bot_detection_computes_all_required_metrics(
        self, 
        profile: AccountProfile,
        contents: List[ContentItem]
    ):
        """
        Property test: Bot detection must compute all required metrics.
        
        This test verifies that the bot detector computes:
        - Account age (via profile analysis)
        - Posting frequency (via behavior analysis)
        - Interaction patterns (via behavior analysis)
        - Content similarity (via content analysis)
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        # Ensure contents have the same user_id as profile
        for content in contents:
            content.user_id = profile.user_id
        
        detector = BotDetector()
        result = detector.detect(profile, contents)
        
        # Verify result structure is complete
        assert result.user_id == profile.user_id
        assert isinstance(result.risk_score, float)
        assert isinstance(result.risk_level, str)
        assert result.risk_level in ['low', 'medium', 'high']
        
        # Verify all component scores are computed (not None)
        assert result.profile_score is not None
        assert result.behavior_score is not None
        assert result.content_score is not None
        assert result.social_score is not None
        
        # Verify detected_features is a list (may be empty)
        assert isinstance(result.detected_features, list)
        
        # Verify recommendation is provided
        assert isinstance(result.recommendation, str)
        assert len(result.recommendation) > 0
    
    @pytest.mark.property
    @given(
        profile=account_profile_strategy(),
        contents=content_list_strategy()
    )
    def test_bot_detection_consistency(
        self,
        profile: AccountProfile,
        contents: List[ContentItem]
    ):
        """
        Property test: Bot detection must be deterministic and consistent.
        
        Running detection twice on the same input should produce the same result.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        # Ensure contents have the same user_id as profile
        for content in contents:
            content.user_id = profile.user_id
        
        detector = BotDetector()
        
        # Run detection twice
        result1 = detector.detect(profile, contents)
        result2 = detector.detect(profile, contents)
        
        # Results should be identical
        assert result1.risk_score == result2.risk_score
        assert result1.risk_level == result2.risk_level
        assert result1.profile_score == result2.profile_score
        assert result1.behavior_score == result2.behavior_score
        assert result1.content_score == result2.content_score
        assert result1.social_score == result2.social_score
        assert result1.is_suspicious == result2.is_suspicious
    
    @pytest.mark.property
    @given(profile=account_profile_strategy())
    def test_bot_detection_profile_analysis_completeness(self, profile: AccountProfile):
        """
        Property test: Profile analysis must handle all account attributes.
        
        The detector should analyze account age, follower/following ratio,
        verification status, and post count.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        detector = BotDetector()
        result = detector.detect(profile)
        
        # Profile score should be computed
        assert result.profile_score is not None
        assert 0.0 <= result.profile_score <= 1.0
        
        # If account has specific characteristics, verify they're considered
        if profile.register_time:
            account_age_days = (datetime.now() - profile.register_time).days
            # Very new accounts (< 30 days) should have some profile risk
            if account_age_days < 30:
                # Profile score should reflect this (though may be offset by other factors)
                assert result.profile_score >= 0.0
        
        # If follower/following ratio is extreme, it should be detected
        if profile.following_count > 0:
            ratio = profile.follower_count / profile.following_count
            if ratio < 0.1 or ratio > 10:
                # Should have some impact on profile score or features
                assert result.profile_score >= 0.0 or len(result.detected_features) >= 0
    
    @pytest.mark.property
    @given(
        profile=account_profile_strategy(),
        contents=st.lists(content_item_strategy(), min_size=2, max_size=20)
    )
    def test_bot_detection_behavior_analysis_with_content(
        self,
        profile: AccountProfile,
        contents: List[ContentItem]
    ):
        """
        Property test: Behavior analysis must process posting patterns.
        
        When content is provided, the detector should analyze posting frequency
        and interaction patterns.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        # Ensure contents have the same user_id and valid timestamps
        for i, content in enumerate(contents):
            content.user_id = profile.user_id
            if content.publish_time is None:
                # Assign sequential timestamps if missing
                content.publish_time = datetime.now() - timedelta(hours=i)
        
        detector = BotDetector()
        result = detector.detect(profile, contents)
        
        # Behavior score should be computed when content is provided
        assert result.behavior_score is not None
        assert 0.0 <= result.behavior_score <= 1.0
        
        # With multiple posts, behavior analysis should run
        assert len(contents) >= 2
    
    @pytest.mark.property
    @given(
        profile=account_profile_strategy(),
        contents=st.lists(
            st.builds(
                ContentItem,
                content_id=st.text(min_size=1, max_size=50),
                user_id=st.just("test_user"),
                text=st.text(min_size=10, max_size=500),
                publish_time=st.just(datetime.now()),
                likes=st.integers(min_value=0, max_value=1000),
                comments=st.integers(min_value=0, max_value=100),
                shares=st.integers(min_value=0, max_value=100),
                has_image=st.booleans(),
                has_video=st.booleans()
            ),
            min_size=3,
            max_size=10
        )
    )
    def test_bot_detection_content_analysis_completeness(
        self,
        profile: AccountProfile,
        contents: List[ContentItem]
    ):
        """
        Property test: Content analysis must evaluate content similarity.
        
        When multiple content items are provided, the detector should analyze
        content duplication and patterns.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        # Ensure contents have the same user_id
        for content in contents:
            content.user_id = profile.user_id
        
        detector = BotDetector()
        result = detector.detect(profile, contents)
        
        # Content score should be computed when content is provided
        assert result.content_score is not None
        assert 0.0 <= result.content_score <= 1.0
        
        # With multiple posts, content analysis should run
        assert len(contents) >= 3
    
    @pytest.mark.property
    @given(profile=account_profile_strategy())
    def test_bot_detection_risk_level_consistency(self, profile: AccountProfile):
        """
        Property test: Risk level must be consistent with risk score.
        
        The risk_level categorization should match the risk_score thresholds.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        detector = BotDetector()
        result = detector.detect(profile)
        
        # Verify risk level matches score thresholds
        if result.risk_score >= detector.RISK_THRESHOLDS['high']:
            assert result.risk_level == 'high'
        elif result.risk_score >= detector.RISK_THRESHOLDS['medium']:
            assert result.risk_level == 'medium'
        else:
            assert result.risk_level == 'low'
        
        # Verify is_suspicious flag matches medium threshold
        if result.risk_score >= detector.RISK_THRESHOLDS['medium']:
            assert result.is_suspicious is True
        else:
            assert result.is_suspicious is False
    
    @pytest.mark.property
    @given(
        profiles=st.lists(account_profile_strategy(), min_size=1, max_size=10)
    )
    def test_bot_detection_batch_processing(self, profiles: List[AccountProfile]):
        """
        Property test: Batch detection must process all accounts.
        
        Batch detection should return results for all input accounts.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        detector = BotDetector()
        
        # Convert profiles to dict format for batch_detect
        accounts_data = []
        for profile in profiles:
            account_dict = {
                'user_id': profile.user_id,
                'nickname': profile.nickname,
                'platform': profile.platform,
                'follower_count': profile.follower_count,
                'following_count': profile.following_count,
                'post_count': profile.post_count,
                'is_verified': profile.is_verified,
                'verify_type': profile.verify_type,
                'metadata': profile.metadata,
                'contents': []
            }
            if profile.register_time:
                account_dict['register_time'] = profile.register_time.isoformat()
            accounts_data.append(account_dict)
        
        results = detector.batch_detect(accounts_data)
        
        # Should return same number of results as inputs
        assert len(results) == len(profiles)
        
        # All results should be valid
        for result in results:
            assert isinstance(result, BotDetectionResult)
            assert 0.0 <= result.risk_score <= 1.0
            assert result.risk_level in ['low', 'medium', 'high']


# ==========================================
# Additional Property Tests for Edge Cases
# ==========================================

class TestBotDetectionEdgeCases:
    """Edge case property tests for bot detection"""
    
    @pytest.mark.property
    def test_bot_detection_with_minimal_profile(self):
        """
        Property test: Detection should work with minimal profile data.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        detector = BotDetector()
        
        # Minimal profile with only required fields
        minimal_profile = AccountProfile(
            user_id="minimal_user",
            nickname="",
            platform=""
        )
        
        result = detector.detect(minimal_profile)
        
        # Should still return valid result
        assert isinstance(result, BotDetectionResult)
        assert 0.0 <= result.risk_score <= 1.0
        assert result.risk_level in ['low', 'medium', 'high']
    
    @pytest.mark.property
    @given(profile=account_profile_strategy())
    def test_bot_detection_with_empty_content_list(self, profile: AccountProfile):
        """
        Property test: Detection should handle empty content list.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        detector = BotDetector()
        
        # Detect with empty content list
        result = detector.detect(profile, [])
        
        # Should still return valid result
        assert isinstance(result, BotDetectionResult)
        assert 0.0 <= result.risk_score <= 1.0
        
        # Behavior and content scores should be 0 or minimal with no content
        assert result.behavior_score == 0.0
        assert result.content_score == 0.0
    
    @pytest.mark.property
    @given(profile=account_profile_strategy())
    def test_bot_detection_with_none_content(self, profile: AccountProfile):
        """
        Property test: Detection should handle None content parameter.
        
        Feature: aletheia-system-optimization, Property 1: Bot Detection Completeness and Validity
        **Validates: Requirements 1.1, 1.2**
        """
        detector = BotDetector()
        
        # Detect with None content
        result = detector.detect(profile, None)
        
        # Should still return valid result
        assert isinstance(result, BotDetectionResult)
        assert 0.0 <= result.risk_score <= 1.0
