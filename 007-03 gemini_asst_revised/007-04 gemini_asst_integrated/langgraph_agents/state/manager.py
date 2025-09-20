import uuid
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import logging
from .models import WorkflowState, SystemState, AgentMetrics, ExecutionResult, TaskStatus

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, cleanup_interval: int = 3600):
        self.system_state = SystemState()
        self.cleanup_interval = cleanup_interval
        self._lock = asyncio.Lock()
        self._cleanup_task = None

    async def start(self):
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("StateManager started with periodic cleanup")

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("StateManager stopped")

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
            if session_id not in self.system_state.active_sessions:
                return False

            session = self.system_state.active_sessions[session_id]
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)

            session.updated_at = datetime.now()
            return True

    async def add_execution_result(self, session_id: str, task_id: str, result: ExecutionResult) -> bool:
        async with self._lock:
            if session_id not in self.system_state.active_sessions:
                return False

            session = self.system_state.active_sessions[session_id]
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

            # 평균 실행 시간 업데이트
            current_avg = metrics.average_execution_time
            total = metrics.total_executions
            metrics.average_execution_time = ((current_avg * (total - 1)) + execution_time) / total

            metrics.last_execution = datetime.now()

    async def get_agent_metrics(self, agent_name: str) -> Optional[AgentMetrics]:
        async with self._lock:
            return self.system_state.agent_metrics.get(agent_name)

    async def get_session_status(self, session_id: str) -> Dict[str, any]:
        session = await self.get_session(session_id)
        if not session:
            return {"error": "Session not found"}

        completed_tasks = sum(1 for result in session.task_results.values()
                            if result.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for result in session.task_results.values()
                         if result.status == TaskStatus.FAILED)
        total_tasks = len(session.task_results)

        return {
            "session_id": session_id,
            "current_step": session.current_step,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "is_multi_task": session.is_multi_task,
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
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    async def _cleanup_old_sessions(self):
        cutoff_time = datetime.now() - timedelta(hours=24)

        async with self._lock:
            sessions_to_remove = [
                session_id for session_id, session in self.system_state.active_sessions.items()
                if session.updated_at < cutoff_time
            ]

            for session_id in sessions_to_remove:
                del self.system_state.active_sessions[session_id]
                logger.info(f"Cleaned up old session: {session_id}")

            if sessions_to_remove:
                logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")

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

# 글로벌 인스턴스
state_manager = StateManager()