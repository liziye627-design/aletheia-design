"""add bot detection and verification tables

Revision ID: 002_add_bot_detection
Revises: 001_add_daily_stats
Create Date: 2025-02-08 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002_add_bot_detection"
down_revision = "001_add_daily_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create bot detection and verification tables with partitioning support.
    """
    
    # ==========================================
    # 1. Accounts table (partitioned by platform)
    # ==========================================
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column("account_id", sa.String(), nullable=False, index=True),
        sa.Column("platform", sa.String(50), nullable=False, index=True),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("follower_count", sa.Integer(), default=0, nullable=False),
        sa.Column("following_count", sa.Integer(), default=0, nullable=False),
        sa.Column("post_count", sa.Integer(), default=0, nullable=False),
        sa.Column("verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("bio", sa.String(), nullable=True),
        sa.Column("profile_image_url", sa.String(), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("first_seen", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column(
            "last_updated",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
            nullable=False
        ),
    )
    
    op.create_index("idx_account_platform_id", "accounts", ["platform", "account_id"])
    op.create_index("idx_account_username", "accounts", ["username"])
    op.create_index("idx_account_created", "accounts", ["created_at"])
    
    # ==========================================
    # 2. Posts table (partitioned by date range)
    # ==========================================
    op.create_table(
        "posts",
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column("post_id", sa.String(), nullable=False, index=True),
        sa.Column("platform", sa.String(50), nullable=False, index=True),
        sa.Column("author_id", sa.String(), nullable=False, index=True),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("like_count", sa.Integer(), default=0, nullable=False),
        sa.Column("comment_count", sa.Integer(), default=0, nullable=False),
        sa.Column("share_count", sa.Integer(), default=0, nullable=False),
        sa.Column("view_count", sa.Integer(), default=0, nullable=False),
        sa.Column("hashtags", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("mentions", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("urls", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("media_urls", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("parent_post_id", sa.String(), nullable=True, index=True),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
    )
    
    op.create_index("idx_post_platform_created", "posts", ["platform", "created_at"])
    op.create_index("idx_post_author", "posts", ["author_id", "created_at"])
    op.create_index("idx_post_parent", "posts", ["parent_post_id"])
    
    # ==========================================
    # 3. Bot Scores table
    # ==========================================
    op.create_table(
        "bot_scores",
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column("account_id", sa.String(), nullable=False, index=True),
        sa.Column("platform", sa.String(50), nullable=False, index=True),
        sa.Column("bot_probability", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("features", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("model_version", sa.String(50), default="1.0", nullable=False),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
    )
    
    op.create_index("idx_bot_score_account", "bot_scores", ["account_id", "detected_at"])
    op.create_index("idx_bot_score_probability", "bot_scores", ["bot_probability"])
    op.create_index("idx_bot_score_platform", "bot_scores", ["platform", "bot_probability"])
    
    # ==========================================
    # 4. CIB Clusters table
    # ==========================================
    op.create_table(
        "cib_clusters",
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column("cluster_id", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("platform", sa.String(50), nullable=False, index=True),
        sa.Column("account_ids", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("cluster_score", sa.Float(), nullable=False),
        sa.Column("behavior_patterns", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False, index=True),
        sa.Column(
            "last_updated",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
            nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
    )
    
    op.create_index("idx_cib_platform_score", "cib_clusters", ["platform", "cluster_score"])
    op.create_index("idx_cib_detected", "cib_clusters", ["detected_at"])
    
    # ==========================================
    # 5. Fake News Predictions table
    # ==========================================
    op.create_table(
        "fake_news_predictions",
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column("text_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("logistic_regression_score", sa.Float(), nullable=False),
        sa.Column("decision_tree_score", sa.Float(), nullable=False),
        sa.Column("gradient_boost_score", sa.Float(), nullable=False),
        sa.Column("random_forest_score", sa.Float(), nullable=False),
        sa.Column("ensemble_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(50), default="1.0", nullable=False),
        sa.Column("predicted_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    
    op.create_index("idx_prediction_hash", "fake_news_predictions", ["text_hash"])
    op.create_index("idx_prediction_ensemble", "fake_news_predictions", ["ensemble_score"])
    op.create_index("idx_prediction_expires", "fake_news_predictions", ["expires_at"])
    
    # ==========================================
    # 6. Verification Results table
    # ==========================================
    op.create_table(
        "verification_results",
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column("content_id", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("content_hash", sa.String(64), nullable=False, index=True),
        sa.Column("content_text", sa.String(), nullable=False),
        sa.Column("credibility_score", sa.Float(), nullable=False),
        sa.Column("credibility_level", sa.String(20), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("risk_flags", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("reasoning_chain", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("fake_news_prediction", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("bot_scores", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("physics_verification", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("logic_verification", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("entropy_analysis", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), default=0, nullable=False),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    
    op.create_index("idx_verification_content", "verification_results", ["content_id"])
    op.create_index("idx_verification_hash", "verification_results", ["content_hash"])
    op.create_index("idx_verification_score", "verification_results", ["credibility_score"])
    op.create_index("idx_verification_level", "verification_results", ["credibility_level"])
    op.create_index("idx_verification_verified", "verification_results", ["verified_at"])
    
    # ==========================================
    # Optional: Create partitions for accounts table
    # ==========================================
    # Note: Partitioning is commented out for initial setup
    # Uncomment and customize based on your PostgreSQL version and requirements
    
    # Example for PostgreSQL 10+ declarative partitioning:
    # op.execute("""
    #     CREATE TABLE accounts_twitter PARTITION OF accounts
    #     FOR VALUES IN ('twitter');
    # """)
    # op.execute("""
    #     CREATE TABLE accounts_weibo PARTITION OF accounts
    #     FOR VALUES IN ('weibo');
    # """)
    
    # ==========================================
    # Optional: Create partitions for posts table by date range
    # ==========================================
    # Example for PostgreSQL 10+ range partitioning:
    # op.execute("""
    #     CREATE TABLE posts_2025_01 PARTITION OF posts
    #     FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
    # """)


def downgrade() -> None:
    """
    Drop all bot detection and verification tables.
    """
    
    # Drop tables in reverse order
    op.drop_index("idx_verification_verified", table_name="verification_results")
    op.drop_index("idx_verification_level", table_name="verification_results")
    op.drop_index("idx_verification_score", table_name="verification_results")
    op.drop_index("idx_verification_hash", table_name="verification_results")
    op.drop_index("idx_verification_content", table_name="verification_results")
    op.drop_table("verification_results")
    
    op.drop_index("idx_prediction_expires", table_name="fake_news_predictions")
    op.drop_index("idx_prediction_ensemble", table_name="fake_news_predictions")
    op.drop_index("idx_prediction_hash", table_name="fake_news_predictions")
    op.drop_table("fake_news_predictions")
    
    op.drop_index("idx_cib_detected", table_name="cib_clusters")
    op.drop_index("idx_cib_platform_score", table_name="cib_clusters")
    op.drop_table("cib_clusters")
    
    op.drop_index("idx_bot_score_platform", table_name="bot_scores")
    op.drop_index("idx_bot_score_probability", table_name="bot_scores")
    op.drop_index("idx_bot_score_account", table_name="bot_scores")
    op.drop_table("bot_scores")
    
    op.drop_index("idx_post_parent", table_name="posts")
    op.drop_index("idx_post_author", table_name="posts")
    op.drop_index("idx_post_platform_created", table_name="posts")
    op.drop_table("posts")
    
    op.drop_index("idx_account_created", table_name="accounts")
    op.drop_index("idx_account_username", table_name="accounts")
    op.drop_index("idx_account_platform_id", table_name="accounts")
    op.drop_table("accounts")
