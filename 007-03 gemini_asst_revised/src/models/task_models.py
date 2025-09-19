from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

@dataclass
class MessageData:
    """원본 메시지 데이터"""
    content: str
    author: str
    channel: str
    timestamp: datetime
    message_id: Optional[str] = None

@dataclass
class ProcessedTask:
    """Gemini로 처리된 작업 데이터"""
    title: str
    category: str
    priority: str
    summary: str
    tags: List[str]
    action_required: bool
    due_date: Optional[str] = None
    notes: Optional[str] = None

@dataclass
class TaskResult:
    """작업 처리 결과"""
    success: bool
    message: str
    notion_task_id: Optional[str] = None
    notion_url: Optional[str] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None