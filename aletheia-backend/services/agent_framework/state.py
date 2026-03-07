"""
Agent Framework - State Management
==================================

状态管理和数据模型定义
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class VerificationStatus(Enum):
    """验证状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SearchResult:
    """搜索结果"""
    source: str
    content: str
    relevance_score: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningStep:
    """推理步骤"""
    step_number: int
    description: str
    reasoning: str
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class VerificationState:
    """验证状态"""
    content: str
    status: VerificationStatus = VerificationStatus.PENDING
    search_results: List[SearchResult] = field(default_factory=list)
    reasoning_steps: List[ReasoningStep] = field(default_factory=list)
    credibility_score: float = 0.0
    final_verdict: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentState:
    """Agent 状态"""
    session_id: str
    verification_states: List[VerificationState] = field(default_factory=list)
    current_state: Optional[VerificationState] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
