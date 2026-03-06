"""
Unit tests for BotDetector feature extraction.

This module tests the calculate_features() method to ensure it properly
extracts all required features for bot detection.
"""

import pytest
from datetime import datetime, timedelta
from services.agent_framework.bot_detector import (
    BotDetector,
    AccountProfile,
    ContentItem,
)


class TestBotDetectorFeatureExtraction:
    """Test the calculate_features() method"""
    
    def test_calculate_features_returns_all_required_fields(self):
        """Test that calculate_features returns all required feature fields"""
        detector = BotDetector()
        
        profile = AccountProfile(
            user_id="test_user",
            nickname="Test User",
            platform="twitter",
            register_time=datetime.now() - timedelta(days=365),
            follower_count=1000,
            following_count=500,
            post_count=100,
            is_verified=True
        )
        
        contents = [
            ContentItem(
                content_id=f"post_{i}",
                user_id="test_user",
                text=f"This is test post number {i}",
                publish_time=datetime.now() - timedelta(hours=i),
                likes=10 * i,
                comments=5 * i
            )
            for i in range(5)
        ]
        
        features = detector.calculate_features(profile, contents)
        
        # Verify all required fields are present
        assert "account_age_days" in features
        assert "posting_frequency" in features
        assert "interaction_ratio" in features
        assert "content_similarity" in features
        assert "profile_completeness" in features
        assert "temporal_entropy" in features
        assert "follower_following_ratio" in features
        assert "verified_status" in features
        
        # Verify types
        assert isinstance(features["account_age_days"], (int, float))
        assert isinstance(features["posting_frequency"], (int, float))
        assert isinstance(features["interaction_ratio"], (int, float))
        assert isinstance(features["content_similarity"], (int, float))
        assert isinstance(features["profile_completeness"], (int, float))
        assert isinstance(features["temporal_entropy"], (int, float))
        assert isinstance(features["follower_following_ratio"], (int, float))
        assert isinstance(features["verified_status"], bool)
    
    def test_calculate_features_account_age(self):
        """Test account age calculation"""
        detector = BotDetector()
        
        # Account created 100 days ago
        profile = AccountProfile(
            user_id="test_user",
            register_time=datetime.now() - timedelta(days=100)
        )
        
        features = detector.calculate_features(profile)
        
        # Should be approximately 100 days (allow small variance)
        assert 99 <= features["account_age_days"] <= 101
    
    def test_calculate_features_posting_frequency(self):
        """Test posting frequency calculation"""
        detector = BotDetector()
        
        # Account with 100 posts over 50 days = 2 posts/day
        profile = AccountProfile(
            user_id="test_user",
            register_time=datetime.now() - timedelta(days=50),
            post_count=100
        )
        
        features = detector.calculate_features(profile)
        
        # Should be approximately 2 posts per day
        assert 1.9 <= features["posting_frequency"] <= 2.1
    
    def test_calculate_features_interaction_ratio(self):
        """Test interaction ratio calculation"""
        detector = BotDetector()
        
        profile = AccountProfile(user_id="test_user")
        
        # 3 posts with 10 likes and 5 comments each = 15 interactions per post
        contents = [
            ContentItem(
                content_id=f"post_{i}",
                user_id="test_user",
                text=f"Post {i}",
                likes=10,
                comments=5
            )
            for i in range(3)
        ]
        
        features = detector.calculate_features(profile, contents)
        
        # Should be 15 (10 likes + 5 comments per post)
        assert features["interaction_ratio"] == 15.0
    
    def test_calculate_features_content_similarity(self):
        """Test content similarity calculation using TF-IDF"""
        detector = BotDetector()
        
        profile = AccountProfile(user_id="test_user")
        
        # Similar content should have high similarity
        similar_contents = [
            ContentItem(
                content_id=f"post_{i}",
                user_id="test_user",
                text="Buy now! Amazing product! Click here!"
            )
            for i in range(3)
        ]
        
        features_similar = detector.calculate_features(profile, similar_contents)
        
        # Different content should have lower similarity
        different_contents = [
            ContentItem(
                content_id="post_1",
                user_id="test_user",
                text="I love programming in Python"
            ),
            ContentItem(
                content_id="post_2",
                user_id="test_user",
                text="Today's weather is beautiful"
            ),
            ContentItem(
                content_id="post_3",
                user_id="test_user",
                text="Just finished reading a great book"
            )
        ]
        
        features_different = detector.calculate_features(profile, different_contents)
        
        # Similar content should have higher similarity score
        assert features_similar["content_similarity"] > features_different["content_similarity"]
    
    def test_calculate_features_temporal_entropy(self):
        """Test temporal entropy calculation"""
        detector = BotDetector()
        
        profile = AccountProfile(user_id="test_user")
        
        # Posts at the same hour (low entropy - mechanical)
        mechanical_contents = [
            ContentItem(
                content_id=f"post_{i}",
                user_id="test_user",
                text=f"Post {i}",
                publish_time=datetime(2024, 1, i+1, 10, 0)  # All at 10:00
            )
            for i in range(5)
        ]
        
        features_mechanical = detector.calculate_features(profile, mechanical_contents)
        
        # Posts at different hours (high entropy - natural)
        natural_contents = [
            ContentItem(
                content_id=f"post_{i}",
                user_id="test_user",
                text=f"Post {i}",
                publish_time=datetime(2024, 1, 1, i * 5, 0)  # Different hours
            )
            for i in range(5)
        ]
        
        features_natural = detector.calculate_features(profile, natural_contents)
        
        # Natural posting should have higher entropy
        assert features_natural["temporal_entropy"] > features_mechanical["temporal_entropy"]
    
    def test_calculate_features_follower_following_ratio(self):
        """Test follower/following ratio calculation"""
        detector = BotDetector()
        
        # Normal ratio
        profile = AccountProfile(
            user_id="test_user",
            follower_count=1000,
            following_count=500
        )
        
        features = detector.calculate_features(profile)
        
        # Should be 2.0 (1000/500)
        assert features["follower_following_ratio"] == 2.0
    
    def test_calculate_features_with_no_content(self):
        """Test feature calculation with no content"""
        detector = BotDetector()
        
        profile = AccountProfile(
            user_id="test_user",
            register_time=datetime.now() - timedelta(days=30),
            follower_count=100,
            following_count=50,
            post_count=10
        )
        
        features = detector.calculate_features(profile, [])
        
        # Should still return all features
        assert len(features) == 8
        
        # Content-dependent features should be 0
        assert features["interaction_ratio"] == 0.0
        assert features["content_similarity"] == 0.0
        assert features["temporal_entropy"] == 0.0
    
    def test_calculate_features_profile_completeness(self):
        """Test profile completeness calculation"""
        detector = BotDetector()
        
        # Complete profile
        complete_profile = AccountProfile(
            user_id="test_user",
            nickname="Test User",
            verify_type="personal",
            metadata={
                "bio": "Software developer",
                "location": "San Francisco",
                "profile_image_url": "https://example.com/image.jpg"
            }
        )
        
        features_complete = detector.calculate_features(complete_profile)
        
        # Incomplete profile
        incomplete_profile = AccountProfile(
            user_id="test_user",
            nickname="",
            verify_type="",
            metadata={}
        )
        
        features_incomplete = detector.calculate_features(incomplete_profile)
        
        # Complete profile should have higher completeness score
        assert features_complete["profile_completeness"] > features_incomplete["profile_completeness"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
