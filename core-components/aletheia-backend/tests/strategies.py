"""
Hypothesis strategies for generating test data.
These strategies are used in property-based tests to generate valid test inputs.
"""

from hypothesis import strategies as st
from datetime import datetime, timedelta
from models.dataclasses import (
    Platform,
    ContentType,
    Account,
    Post,
    BotFeatures,
    BotScore,
    CIBCluster,
    FakeNewsPrediction,
    VerificationResult,
    CrawlConfig,
    RetryStrategy,
)


# ==========================================
# Basic Strategies
# ==========================================

# Platform strategy
platform_strategy = st.sampled_from([p.value for p in Platform])

# Content type strategy
content_type_strategy = st.sampled_from([c.value for c in ContentType])

# Datetime strategy (last 5 years)
datetime_strategy = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2025, 12, 31)
)

# Recent datetime strategy (last 30 days)
recent_datetime_strategy = st.datetimes(
    min_value=datetime.now() - timedelta(days=30),
    max_value=datetime.now()
)

# Probability strategy (0-1)
probability_strategy = st.floats(min_value=0.0, max_value=1.0)

# Confidence strategy
confidence_strategy = st.sampled_from(["HIGH", "MEDIUM", "LOW"])

# Credibility level strategy
credibility_level_strategy = st.sampled_from([
    "VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"
])


# ==========================================
# Account Strategy
# ==========================================

account_strategy = st.builds(
    Account,
    account_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='_-'
    )),
    platform=st.sampled_from(Platform),
    username=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='_-'
    )),
    created_at=datetime_strategy,
    follower_count=st.integers(min_value=0, max_value=10000000),
    following_count=st.integers(min_value=0, max_value=100000),
    post_count=st.integers(min_value=0, max_value=1000000),
    verified=st.booleans(),
    bio=st.one_of(st.none(), st.text(max_size=500)),
    profile_image_url=st.one_of(st.none(), st.text(min_size=10, max_size=200)),
    location=st.one_of(st.none(), st.text(max_size=100)),
    metadata=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.integers(), st.floats(), st.booleans()),
        max_size=5
    )
)


# ==========================================
# Post Strategy
# ==========================================

post_strategy = st.builds(
    Post,
    post_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='_-'
    )),
    platform=st.sampled_from(Platform),
    author_id=st.text(min_size=1, max_size=50),
    content=st.text(min_size=1, max_size=5000),
    content_type=st.sampled_from(ContentType),
    created_at=datetime_strategy,
    like_count=st.integers(min_value=0, max_value=1000000),
    comment_count=st.integers(min_value=0, max_value=100000),
    share_count=st.integers(min_value=0, max_value=100000),
    view_count=st.integers(min_value=0, max_value=10000000),
    hashtags=st.lists(st.text(min_size=1, max_size=50), max_size=10),
    mentions=st.lists(st.text(min_size=1, max_size=50), max_size=10),
    urls=st.lists(st.text(min_size=10, max_size=200), max_size=5),
    media_urls=st.lists(st.text(min_size=10, max_size=200), max_size=5),
    parent_post_id=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    metadata=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.integers(), st.floats()),
        max_size=5
    )
)


# ==========================================
# BotFeatures Strategy
# ==========================================

bot_features_strategy = st.builds(
    BotFeatures,
    account_age_days=st.floats(min_value=0.0, max_value=3650.0),
    posting_frequency=st.floats(min_value=0.0, max_value=100.0),
    interaction_ratio=st.floats(min_value=0.0, max_value=10.0),
    content_similarity=probability_strategy,
    profile_completeness=probability_strategy,
    temporal_entropy=st.floats(min_value=0.0, max_value=10.0),
    follower_following_ratio=st.floats(min_value=0.0, max_value=100.0),
    verified_status=st.booleans()
)


# ==========================================
# BotScore Strategy
# ==========================================

bot_score_strategy = st.builds(
    BotScore,
    account_id=st.text(min_size=1, max_size=50),
    platform=st.sampled_from(Platform),
    bot_probability=probability_strategy,
    features=bot_features_strategy,
    confidence=confidence_strategy,
    detected_at=recent_datetime_strategy,
    model_version=st.text(min_size=1, max_size=20),
    metadata=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.integers(), st.floats()),
        max_size=5
    )
)


# ==========================================
# CIBCluster Strategy
# ==========================================

cib_cluster_strategy = st.builds(
    CIBCluster,
    cluster_id=st.text(min_size=1, max_size=50),
    account_ids=st.lists(st.text(min_size=1, max_size=50), min_size=2, max_size=20),
    platform=st.sampled_from(Platform),
    cluster_score=probability_strategy,
    behavior_patterns=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.floats(), st.booleans()),
        min_size=1,
        max_size=10
    ),
    detected_at=recent_datetime_strategy,
    metadata=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.integers(), st.floats()),
        max_size=5
    )
)


# ==========================================
# FakeNewsPrediction Strategy
# ==========================================

fake_news_prediction_strategy = st.builds(
    FakeNewsPrediction,
    text_hash=st.text(min_size=32, max_size=64, alphabet='0123456789abcdef'),
    logistic_regression_score=probability_strategy,
    decision_tree_score=probability_strategy,
    gradient_boost_score=probability_strategy,
    random_forest_score=probability_strategy,
    ensemble_score=probability_strategy,
    confidence=probability_strategy,
    predicted_at=recent_datetime_strategy,
    model_version=st.text(min_size=1, max_size=20)
)


# ==========================================
# VerificationResult Strategy
# ==========================================

verification_result_strategy = st.builds(
    VerificationResult,
    content_id=st.text(min_size=1, max_size=50),
    content_text=st.text(min_size=1, max_size=5000),
    credibility_score=probability_strategy,
    credibility_level=credibility_level_strategy,
    confidence=confidence_strategy,
    risk_flags=st.lists(st.text(min_size=1, max_size=50), max_size=10),
    reasoning_chain=st.lists(st.text(min_size=1, max_size=200), max_size=10),
    fake_news_prediction=st.one_of(st.none(), fake_news_prediction_strategy),
    bot_scores=st.lists(bot_score_strategy, max_size=5),
    physics_verification=st.one_of(st.none(), st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.floats(), st.booleans()),
        max_size=5
    )),
    logic_verification=st.one_of(st.none(), st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.floats(), st.booleans()),
        max_size=5
    )),
    entropy_analysis=st.one_of(st.none(), st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.floats(), st.booleans()),
        max_size=5
    )),
    verified_at=recent_datetime_strategy,
    processing_time_ms=st.integers(min_value=0, max_value=60000),
    metadata=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.integers(), st.floats()),
        max_size=5
    )
)


# ==========================================
# CrawlConfig Strategy
# ==========================================

crawl_config_strategy = st.builds(
    CrawlConfig,
    platform=st.sampled_from(Platform),
    max_depth=st.integers(min_value=0, max_value=10),
    max_pages=st.integers(min_value=1, max_value=1000),
    max_retries=st.integers(min_value=0, max_value=10),
    base_delay=st.floats(min_value=0.1, max_value=10.0),
    max_delay=st.floats(min_value=10.0, max_value=300.0),
    exponential_base=st.floats(min_value=1.0, max_value=5.0),
    timeout=st.integers(min_value=1, max_value=300),
    user_agents=st.lists(st.text(min_size=10, max_size=200), max_size=5),
    headers=st.dictionaries(
        keys=st.text(min_size=1, max_size=50),
        values=st.text(min_size=1, max_size=200),
        max_size=10
    ),
    cookies=st.dictionaries(
        keys=st.text(min_size=1, max_size=50),
        values=st.text(min_size=1, max_size=200),
        max_size=10
    ),
    proxy=st.one_of(st.none(), st.text(min_size=10, max_size=200)),
    validate_schema=st.booleans(),
    collect_metadata=st.booleans(),
    follow_links=st.booleans(),
    metadata=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(), st.integers(), st.floats()),
        max_size=5
    )
)


# ==========================================
# RetryStrategy Strategy
# ==========================================

retry_strategy_strategy = st.builds(
    RetryStrategy,
    max_attempts=st.integers(min_value=1, max_value=10),
    base_delay=st.floats(min_value=0.1, max_value=10.0),
    max_delay=st.floats(min_value=10.0, max_value=300.0),
    exponential_base=st.floats(min_value=1.0, max_value=5.0),
    jitter=st.booleans(),
    jitter_range=st.floats(min_value=0.0, max_value=1.0)
)
