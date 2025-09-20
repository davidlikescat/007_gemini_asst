from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class TaskType(str, Enum):
    NOTION = "notion"
    CALENDAR = "calendar"
    GMAIL = "gmail"
    DISCORD = "discord"

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskIntent(BaseModel):
    type: TaskType
    action: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    priority: Priority = Priority.MEDIUM
    dependencies: List[str] = Field(default_factory=list)

class ExecutionResult(BaseModel):
    task_id: str
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    retry_count: int = 0

class WorkflowState(BaseModel):
    session_id: str
    user_input: str
    original_message: str

    # Intent 분석 결과
    intents: List[TaskIntent] = Field(default_factory=list)
    is_multi_task: bool = False

    # 실행 상태
    task_results: Dict[str, ExecutionResult] = Field(default_factory=dict)
    current_step: str = "start"

    # 컨텍스트
    context: Dict[str, Any] = Field(default_factory=dict)

    # 메타데이터
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Self-reflection 데이터
    performance_metrics: Dict[str, float] = Field(default_factory=dict)
    confidence_scores: Dict[str, float] = Field(default_factory=dict)

class AgentMetrics(BaseModel):
    agent_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    average_execution_time: float = 0.0
    last_execution: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

class SystemState(BaseModel):
    active_sessions: Dict[str, WorkflowState] = Field(default_factory=dict)
    agent_metrics: Dict[str, AgentMetrics] = Field(default_factory=dict)
    global_context: Dict[str, Any] = Field(default_factory=dict)