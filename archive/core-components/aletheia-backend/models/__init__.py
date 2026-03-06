"""
Models package.
Exports both dataclasses and database models.
"""

# Dataclasses (business logic models)
from .dataclasses import (
    Platform,
    ContentType as DataclassContentType,
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
)

# Database models
from .database import (
    Intel,
    Baseline,
    WaterArmySignal,
    DailyStatistics,
    CredibilityLevel,
    RiskFlag,
    ContentType as DBContentType,
    User,
    Report,
    AuditLog,
    AccountModel,
    PostModel,
    BotScoreModel,
    CIBClusterModel,
    FakeNewsPredictionModel,
    VerificationResultModel,
)

__all__ = [
    # Enums
    "Platform",
    "DataclassContentType",
    "CredibilityLevel",
    "RiskFlag",
    "DBContentType",
    # Dataclasses
    "Account",
    "Post",
    "BotFeatures",
    "BotScore",
    "CIBCluster",
    "FakeNewsPrediction",
    "VerificationResult",
    "CrawlConfig",
    "CrawlMetrics",
    "RetryStrategy",
    # Database models
    "Intel",
    "Baseline",
    "WaterArmySignal",
    "DailyStatistics",
    "User",
    "Report",
    "AuditLog",
    "AccountModel",
    "PostModel",
    "BotScoreModel",
    "CIBClusterModel",
    "FakeNewsPredictionModel",
    "VerificationResultModel",
]
