"""
用户和报告数据模型
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from core.database import Base


class User(Base):
    """用户表"""

    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # 用户信息
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)

    # 权限
    is_active = Column(Integer, default=1, nullable=False)
    is_superuser = Column(Integer, default=0, nullable=False)

    # 配置
    preferences = Column(JSON, nullable=True)
    # {
    #   "language": "zh-CN",
    #   "theme": "dark",
    #   "notification_enabled": true
    # }

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_login = Column(DateTime, nullable=True)

    # 关系
    intels = relationship("Intel", back_populates="user")
    reports = relationship("Report", back_populates="user")


class Report(Base):
    """分析报告表"""

    __tablename__ = "reports"

    id = Column(String, primary_key=True, index=True)

    # 关联情报
    intel_id = Column(String, ForeignKey("intels.id"), nullable=False)

    # 标题和摘要
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)

    # 报告内容(HTML)
    content_html = Column(Text, nullable=False)

    # JSON-LD结构化数据
    jsonld_schema = Column(JSON, nullable=True)

    # SEO元数据
    seo_metadata = Column(JSON, nullable=True)
    # {
    #   "meta_title": "...",
    #   "meta_description": "...",
    #   "keywords": ["..."],
    #   "canonical_url": "..."
    # }

    # GEO预测
    geo_prediction = Column(JSON, nullable=True)
    # {
    #   "predicted_rank_position": 3,
    #   "search_visibility": 0.75,
    #   "improvement_actions": ["..."]
    # }

    # 发布状态
    is_published = Column(Integer, default=0, nullable=False)
    published_at = Column(DateTime, nullable=True)

    # 用户
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # 关系
    intel = relationship("Intel", back_populates="reports")
    user = relationship("User", back_populates="reports")

    __table_args__ = (
        Index("idx_user_created", "user_id", "created_at"),
        Index("idx_published", "is_published", "published_at"),
    )


class AuditLog(Base):
    """审计日志"""

    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, index=True)

    # 操作信息
    action = Column(String(100), nullable=False)  # analyze, generate_report, etc
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String, nullable=True)

    # 用户
    user_id = Column(String, ForeignKey("users.id"), nullable=True)

    # 详情
    details = Column(JSON, nullable=True)

    # IP和设备
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    # 结果
    success = Column(Integer, default=1, nullable=False)
    error_message = Column(Text, nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (Index("idx_user_action", "user_id", "action", "created_at"),)
