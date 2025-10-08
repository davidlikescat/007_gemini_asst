from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    NOTION = "notion"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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

    intents: List[TaskIntent] = Field(default_factory=list)
    params: Dict[str, Any] = Field(default_factory=dict)
    task_results: Dict[str, ExecutionResult] = Field(default_factory=dict)
    current_step: str = "start"
    context: Dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


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
