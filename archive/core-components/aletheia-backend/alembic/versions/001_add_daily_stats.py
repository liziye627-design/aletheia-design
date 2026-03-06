"""add daily_statistics table

Revision ID: 001_add_daily_stats
Revises:
Create Date: 2025-02-02 20:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_add_daily_stats"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    创建daily_statistics表 - 用于存储每日统计数据以支持基准线分析
    """
    op.create_table(
        "daily_statistics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "keyword",
            sa.String(255),
            nullable=False,
            index=True,
            comment="关键词/实体名称",
        ),
        sa.Column(
            "platform", sa.String(50), nullable=False, index=True, comment="平台名称"
        ),
        sa.Column("date", sa.Date(), nullable=False, index=True, comment="统计日期"),
        # 统计指标
        sa.Column("post_count", sa.Integer(), default=0, comment="帖子数量"),
        sa.Column("total_likes", sa.BigInteger(), default=0, comment="总点赞数"),
        sa.Column("total_comments", sa.BigInteger(), default=0, comment="总评论数"),
        sa.Column("total_shares", sa.BigInteger(), default=0, comment="总分享数"),
        sa.Column("avg_engagement", sa.Float(), default=0.0, comment="平均互动率"),
        # 账号类型分布
        sa.Column(
            "verified_account_count", sa.Integer(), default=0, comment="认证账号数"
        ),
        sa.Column("influencer_count", sa.Integer(), default=0, comment="KOL账号数"),
        sa.Column(
            "ordinary_account_count", sa.Integer(), default=0, comment="普通账号数"
        ),
        sa.Column("new_account_ratio", sa.Float(), default=0.0, comment="新账号占比"),
        # 情感分析
        sa.Column("positive_count", sa.Integer(), default=0, comment="正面情感数"),
        sa.Column("neutral_count", sa.Integer(), default=0, comment="中性情感数"),
        sa.Column("negative_count", sa.Integer(), default=0, comment="负面情感数"),
        # 时间戳
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
            nullable=False,
        ),
        # 复合唯一索引 - 防止重复统计
        sa.UniqueConstraint(
            "keyword", "platform", "date", name="uq_keyword_platform_date"
        ),
    )

    # 创建复合索引以优化查询性能
    op.create_index(
        "idx_keyword_platform_date",
        "daily_statistics",
        ["keyword", "platform", "date"],
    )

    # 创建日期索引（用于时间范围查询）
    op.create_index(
        "idx_date_desc",
        "daily_statistics",
        ["date"],
        postgresql_ops={"date": "DESC"},
    )


def downgrade() -> None:
    """
    删除daily_statistics表
    """
    op.drop_index("idx_date_desc", table_name="daily_statistics")
    op.drop_index("idx_keyword_platform_date", table_name="daily_statistics")
    op.drop_table("daily_statistics")
