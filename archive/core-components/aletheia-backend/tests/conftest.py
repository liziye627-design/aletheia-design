"""
Pytest configuration and fixtures for Aletheia system tests.
Includes hypothesis configuration for property-based testing.
"""

import pytest
from datetime import datetime, timedelta
from hypothesis import settings, Verbosity
from typing import Generator
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ==========================================
# Hypothesis Configuration
# ==========================================

# Register custom hypothesis profile for property-based testing
# Minimum 100 iterations per property test as per design document
settings.register_profile(
    "aletheia",
    max_examples=100,
    deadline=None,  # Disable deadline for complex tests
    verbosity=Verbosity.normal,
    print_blob=True,  # Print failing examples
)

# Use the aletheia profile by default
settings.load_profile("aletheia")


# ==========================================
# Test Fixtures
# ==========================================

@pytest.fixture
def sample_datetime() -> datetime:
    """Provide a consistent datetime for testing."""
    return datetime(2025, 2, 8, 12, 0, 0)


@pytest.fixture
def sample_account_data() -> dict:
    """Provide sample account data for testing."""
    return {
        "account_id": "test_user_123",
        "platform": "twitter",
        "username": "testuser",
        "created_at": datetime(2020, 1, 1),
        "follower_count": 1000,
        "following_count": 500,
        "post_count": 250,
        "verified": False,
        "bio": "Test user bio",
        "location": "Test City",
    }


@pytest.fixture
def sample_post_data() -> dict:
    """Provide sample post data for testing."""
    return {
        "post_id": "post_123",
        "platform": "twitter",
        "author_id": "test_user_123",
        "content": "This is a test post",
        "content_type": "text",
        "created_at": datetime(2025, 2, 8, 12, 0, 0),
        "like_count": 10,
        "comment_count": 5,
        "share_count": 2,
        "view_count": 100,
        "hashtags": ["#test", "#example"],
        "mentions": ["@user1"],
        "urls": ["https://example.com"],
    }


@pytest.fixture
def sample_bot_features() -> dict:
    """Provide sample bot features for testing."""
    return {
        "account_age_days": 365.0,
        "posting_frequency": 5.0,
        "interaction_ratio": 0.5,
        "content_similarity": 0.3,
        "profile_completeness": 0.8,
        "temporal_entropy": 2.5,
        "follower_following_ratio": 2.0,
        "verified_status": False,
    }


@pytest.fixture
def sample_crawl_config() -> dict:
    """Provide sample crawl configuration for testing."""
    return {
        "platform": "twitter",
        "max_depth": 3,
        "max_pages": 100,
        "max_retries": 5,
        "base_delay": 1.0,
        "max_delay": 60.0,
        "exponential_base": 2.0,
        "timeout": 30,
    }


@pytest.fixture
def sample_retry_strategy() -> dict:
    """Provide sample retry strategy for testing."""
    return {
        "max_attempts": 5,
        "base_delay": 1.0,
        "max_delay": 60.0,
        "exponential_base": 2.0,
        "jitter": True,
        "jitter_range": 0.1,
    }


# ==========================================
# Database Fixtures (for integration tests)
# ==========================================

@pytest.fixture
def db_session():
    """
    Provide a database session for integration tests.
    Note: This is a placeholder. Implement actual database setup when needed.
    """
    # TODO: Implement database session setup
    # from core.database import SessionLocal
    # db = SessionLocal()
    # try:
    #     yield db
    # finally:
    #     db.close()
    pass


# ==========================================
# Async Fixtures
# ==========================================

@pytest.fixture
async def async_client():
    """
    Provide an async HTTP client for API testing.
    Note: This is a placeholder. Implement when API tests are needed.
    """
    # TODO: Implement async client setup
    # from httpx import AsyncClient
    # from main import app
    # async with AsyncClient(app=app, base_url="http://test") as client:
    #     yield client
    pass


# ==========================================
# Markers
# ==========================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "property: Property-based tests using hypothesis"
    )
    config.addinivalue_line(
        "markers", "unit: Unit tests for specific functionality"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests across components"
    )
    config.addinivalue_line(
        "markers", "slow: Slow-running tests"
    )
    config.addinivalue_line(
        "markers", "async: Asynchronous tests"
    )
