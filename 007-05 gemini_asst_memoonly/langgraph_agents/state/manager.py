import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from .models import WorkflowState, SystemState, AgentMetrics, ExecutionResult, TaskStatus

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, cleanup_interval: int = 3600):
        self.system_state = SystemState()
        self.cleanup_interval = cleanup_interval
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info("StateManager started with periodic cleanup task.")

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("StateManager cleanup task stopped.")

    async def create_session(self, user_input: str, original_message: str) -> str:
        session_id = str(uuid.uuid4())

        async with self._lock:
            workflow_state = WorkflowState(
                session_id=session_id,
                user_input=user_input,
                original_message=original_message
            )
            self.system_state.active_sessions[session_id] = workflow_state

        logger.info(f"Created new session: {session_id}")
        return session_id

    async def get_session(self, session_id: str) -> Optional[WorkflowState]:
        async with self._lock:
            return self.system_state.active_sessions.get(session_id)

    async def update_session(self, session_id: str, **kwargs) -> bool:
        async with self._lock:
            session = self.system_state.active_sessions.get(session_id)
            if not session:
                return False

            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            session.updated_at = datetime.now()
            return True

    async def add_execution_result(self, session_id: str, task_id: str, result: ExecutionResult) -> bool:
        async with self._lock:
            session = self.system_state.active_sessions.get(session_id)
            if not session:
                return False

            session.task_results[task_id] = result
            session.updated_at = datetime.now()
            return True

    async def update_agent_metrics(self, agent_name: str, success: bool, execution_time: float):
        async with self._lock:
            if agent_name not in self.system_state.agent_metrics:
                self.system_state.agent_metrics[agent_name] = AgentMetrics(agent_name=agent_name)

            metrics = self.system_state.agent_metrics[agent_name]
            metrics.total_executions += 1

            if success:
                metrics.successful_executions += 1
            else:
                metrics.failed_executions += 1

            total = metrics.total_executions
            metrics.average_execution_time = ((metrics.average_execution_time * (total - 1)) + execution_time) / total
            metrics.last_execution = datetime.now()

    async def get_session_status(self, session_id: str) -> Dict[str, any]:
        session = await self.get_session(session_id)
        if not session:
            return {"error": "Session not found"}

        completed_tasks = sum(1 for result in session.task_results.values() if result.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for result in session.task_results.values() if result.status == TaskStatus.FAILED)

        return {
            "session_id": session_id,
            "current_step": session.current_step,
            "total_tasks": len(session.task_results),
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "created_at": session.created_at,
            "updated_at": session.updated_at
        }

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self.system_state.active_sessions:
                del self.system_state.active_sessions[session_id]
                logger.info(f"Closed session: {session_id}")
                return True
        return False

    async def _periodic_cleanup(self):
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_sessions()
        except asyncio.CancelledError:
            logger.debug("StateManager cleanup task cancelled.")

    async def _cleanup_old_sessions(self):
        cutoff_time = datetime.now() - timedelta(hours=12)

        async with self._lock:
            expired_sessions = [
                session_id
                for session_id, session in self.system_state.active_sessions.items()
                if session.updated_at < cutoff_time
            ]

            for session_id in expired_sessions:
                del self.system_state.active_sessions[session_id]

            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired sessions.")

    async def get_system_metrics(self) -> Dict[str, any]:
        async with self._lock:
            return {
                "active_sessions": len(self.system_state.active_sessions),
                "total_agents": len(self.system_state.agent_metrics),
                "agent_metrics": {
                    name: {
                        "success_rate": metrics.success_rate,
                        "total_executions": metrics.total_executions,
                        "average_execution_time": metrics.average_execution_time
                    }
                    for name, metrics in self.system_state.agent_metrics.items()
                }
            }


state_manager = StateManager()
