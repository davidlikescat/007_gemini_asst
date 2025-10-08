import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from ..state.models import WorkflowState, ExecutionResult, TaskStatus
from ..state.manager import state_manager

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, name: str, max_retries: int = 3):
        self.name = name
        self.max_retries = max_retries
        self.logger = logging.getLogger(f"agent.{name}")

    @abstractmethod
    async def execute(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        """에이전트가 실제 작업을 수행하는 메서드"""
        raise NotImplementedError

    async def run_with_metrics(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        start_time = time.time()
        task_id = task_params.get("task_id", f"{self.name}_{int(start_time)}")

        try:
            self.logger.info(f"Starting execution: {task_id}")

            result = await self._execute_with_retry(state, task_params)

            execution_time = time.time() - start_time
            result.execution_time = execution_time

            # 메트릭 업데이트
            success = result.status == TaskStatus.COMPLETED
            await state_manager.update_agent_metrics(self.name, success, execution_time)

            if success:
                self.logger.info(f"Completed execution: {task_id} in {execution_time:.2f}s")
            else:
                self.logger.error(f"Failed execution: {task_id} - {result.error}")

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            error_result = ExecutionResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time=execution_time
            )

            await state_manager.update_agent_metrics(self.name, False, execution_time)
            self.logger.error(f"Exception in execution: {task_id} - {e}")

            return error_result

    async def _execute_with_retry(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt
                    self.logger.info(f"Retrying {self.name} (attempt {attempt + 1}) in {wait_time}s")
                    await asyncio.sleep(wait_time)

                result = await self.execute(state, task_params)
                result.retry_count = attempt

                if result.status == TaskStatus.COMPLETED:
                    return result
                elif result.status == TaskStatus.FAILED and attempt < self.max_retries:
                    last_error = result.error
                    continue
                else:
                    return result

            except Exception as e:
                last_error = str(e)
                if attempt == self.max_retries:
                    break

        task_id = task_params.get("task_id", f"{self.name}_failed")
        return ExecutionResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error=f"Max retries exceeded. Last error: {last_error}",
            retry_count=self.max_retries
        )

    async def validate_params(self, params: Dict[str, Any]) -> bool:
        return True

    async def pre_execute(self, state: WorkflowState, params: Dict[str, Any]) -> Dict[str, Any]:
        return params

    async def post_execute(self, state: WorkflowState, result: ExecutionResult) -> ExecutionResult:
        return result


class AgentExecutor:
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent):
        self.agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name}")

    async def execute_agent(self, agent_name: str, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        if agent_name not in self.agents:
            return ExecutionResult(
                task_id=task_params.get("task_id", "unknown"),
                status=TaskStatus.FAILED,
                error=f"Agent {agent_name} not found"
            )

        agent = self.agents[agent_name]
        return await agent.run_with_metrics(state, task_params)

    async def execute_parallel(self, tasks: List[Dict[str, Any]], state: WorkflowState) -> List[ExecutionResult]:
        semaphore = asyncio.Semaphore(5)  # 최대 5개 동시 실행

        async def execute_with_semaphore(task):
            async with semaphore:
                agent_name = task.get("agent")
                return await self.execute_agent(agent_name, state, task)

        results = await asyncio.gather(
            *[execute_with_semaphore(task) for task in tasks],
            return_exceptions=True
        )

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(ExecutionResult(
                    task_id=tasks[i].get("task_id", f"task_{i}"),
                    status=TaskStatus.FAILED,
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        return processed_results


# 글로벌 executor 인스턴스
agent_executor = AgentExecutor()
