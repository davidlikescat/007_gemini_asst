from typing import Dict, Any, List
from langgraph import StateGraph, END
from langchain.schema import BaseMessage

from ..state.models import WorkflowState, TaskStatus
from ..state.manager import state_manager
from ..agents.base_agent import agent_executor

class AgenticWorkflow:
    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(WorkflowState)

        # 노드 정의
        workflow.add_node("intent_analysis", self._intent_analysis_node)
        workflow.add_node("task_decomposition", self._task_decomposition_node)
        workflow.add_node("parallel_execution", self._parallel_execution_node)
        workflow.add_node("sequential_execution", self._sequential_execution_node)
        workflow.add_node("error_handling", self._error_handling_node)
        workflow.add_node("result_aggregation", self._result_aggregation_node)
        workflow.add_node("self_reflection", self._self_reflection_node)
        workflow.add_node("notification", self._notification_node)

        # 엣지 정의 (비선형 플로우)
        workflow.set_entry_point("intent_analysis")

        # Intent Analysis 후 분기
        workflow.add_conditional_edges(
            "intent_analysis",
            self._route_after_intent_analysis,
            {
                "simple": "sequential_execution",
                "complex": "task_decomposition",
                "error": "error_handling"
            }
        )

        # Task Decomposition 후 병렬 실행
        workflow.add_edge("task_decomposition", "parallel_execution")

        # 실행 완료 후 결과 집계
        workflow.add_conditional_edges(
            "parallel_execution",
            self._check_execution_results,
            {
                "success": "result_aggregation",
                "partial_failure": "error_handling",
                "complete_failure": "error_handling"
            }
        )

        workflow.add_conditional_edges(
            "sequential_execution",
            self._check_execution_results,
            {
                "success": "result_aggregation",
                "partial_failure": "error_handling",
                "complete_failure": "error_handling"
            }
        )

        # 에러 처리 후 재시도 또는 알림
        workflow.add_conditional_edges(
            "error_handling",
            self._route_after_error_handling,
            {
                "retry": "parallel_execution",
                "notify": "notification",
                "complete": "result_aggregation"
            }
        )

        # 결과 집계 후 Self-Reflection
        workflow.add_edge("result_aggregation", "self_reflection")

        # Self-Reflection 후 알림
        workflow.add_edge("self_reflection", "notification")

        # 최종 종료
        workflow.add_edge("notification", END)

        return workflow.compile()

    async def _intent_analysis_node(self, state: WorkflowState) -> WorkflowState:
        result = await agent_executor.execute_agent(
            "intent_router",
            state,
            {"task_id": "intent_analysis"}
        )

        if result.status == TaskStatus.COMPLETED:
            # 상태 업데이트는 IntentRouterAgent에서 수행됨
            state.current_step = "intent_analyzed"
        else:
            state.current_step = "error"

        await state_manager.add_execution_result(state.session_id, "intent_analysis", result)
        return state

    async def _task_decomposition_node(self, state: WorkflowState) -> WorkflowState:
        result = await agent_executor.execute_agent(
            "task_decomposer",
            state,
            {"task_id": "task_decomposition"}
        )

        if result.status == TaskStatus.COMPLETED:
            # 실행 계획을 컨텍스트에 저장
            state.context.update(result.result)
            state.current_step = "decomposed"

        await state_manager.add_execution_result(state.session_id, "task_decomposition", result)
        return state

    async def _parallel_execution_node(self, state: WorkflowState) -> WorkflowState:
        parallel_groups = state.context.get("parallel_groups", [])

        for group_idx, group in enumerate(parallel_groups):
            group_results = await agent_executor.execute_parallel(group, state)

            # 그룹 결과를 상태에 저장
            for result in group_results:
                await state_manager.add_execution_result(state.session_id, result.task_id, result)

            # 그룹 실행 후 잠시 대기 (리소스 관리)
            if group_idx < len(parallel_groups) - 1:
                import asyncio
                await asyncio.sleep(1)

        state.current_step = "executed"
        return state

    async def _sequential_execution_node(self, state: WorkflowState) -> WorkflowState:
        for intent in state.intents:
            task_id = intent.parameters.get("task_id")
            agent_name = self._get_agent_name_from_intent(intent)

            result = await agent_executor.execute_agent(agent_name, state, intent.parameters)
            await state_manager.add_execution_result(state.session_id, task_id, result)

        state.current_step = "executed"
        return state

    async def _error_handling_node(self, state: WorkflowState) -> WorkflowState:
        failed_tasks = [
            task_id for task_id, result in state.task_results.items()
            if result.status == TaskStatus.FAILED
        ]

        state.context["failed_tasks"] = failed_tasks
        state.context["retry_count"] = state.context.get("retry_count", 0) + 1

        # 에러 분석 및 복구 전략 수립
        recovery_strategy = await self._analyze_failures(state, failed_tasks)
        state.context["recovery_strategy"] = recovery_strategy

        state.current_step = "error_handled"
        return state

    async def _result_aggregation_node(self, state: WorkflowState) -> WorkflowState:
        completed_results = {
            task_id: result for task_id, result in state.task_results.items()
            if result.status == TaskStatus.COMPLETED
        }

        aggregated_result = {
            "total_tasks": len(state.task_results),
            "completed_tasks": len(completed_results),
            "failed_tasks": len(state.task_results) - len(completed_results),
            "results": completed_results,
            "session_summary": await self._create_session_summary(state)
        }

        state.context["final_result"] = aggregated_result
        state.current_step = "aggregated"
        return state

    async def _self_reflection_node(self, state: WorkflowState) -> WorkflowState:
        result = await agent_executor.execute_agent(
            "self_reflection",
            state,
            {"task_id": "self_reflection"}
        )

        await state_manager.add_execution_result(state.session_id, "self_reflection", result)
        state.current_step = "reflected"
        return state

    async def _notification_node(self, state: WorkflowState) -> WorkflowState:
        # Discord 알림 발송
        notification_result = await agent_executor.execute_agent(
            "discord_agent",
            state,
            {
                "task_id": "final_notification",
                "action": "send_completion_summary",
                "summary": state.context.get("final_result", {})
            }
        )

        await state_manager.add_execution_result(state.session_id, "notification", notification_result)
        state.current_step = "completed"
        return state

    # 라우팅 함수들
    def _route_after_intent_analysis(self, state: WorkflowState) -> str:
        if not state.intents:
            return "error"

        if len(state.intents) == 1 and not state.intents[0].dependencies:
            return "simple"
        else:
            return "complex"

    def _check_execution_results(self, state: WorkflowState) -> str:
        if not state.task_results:
            return "complete_failure"

        completed = sum(1 for result in state.task_results.values()
                       if result.status == TaskStatus.COMPLETED)
        total = len(state.task_results)

        if completed == total:
            return "success"
        elif completed > 0:
            return "partial_failure"
        else:
            return "complete_failure"

    def _route_after_error_handling(self, state: WorkflowState) -> str:
        retry_count = state.context.get("retry_count", 0)
        max_retries = 2

        if retry_count < max_retries:
            return "retry"
        else:
            failed_count = len(state.context.get("failed_tasks", []))
            if failed_count < len(state.task_results):
                return "complete"  # 부분 성공
            else:
                return "notify"  # 완전 실패

    # 유틸리티 함수들
    def _get_agent_name_from_intent(self, intent) -> str:
        type_to_agent = {
            "notion": "notion_agent",
            "calendar": "calendar_agent",
            "gmail": "gmail_agent",
            "discord": "discord_agent"
        }
        return type_to_agent.get(intent.type.value, "unknown_agent")

    async def _analyze_failures(self, state: WorkflowState, failed_tasks: List[str]) -> Dict[str, Any]:
        # 실패 패턴 분석
        failure_types = {}
        for task_id in failed_tasks:
            result = state.task_results.get(task_id)
            if result and result.error:
                error_type = self._categorize_error(result.error)
                failure_types[error_type] = failure_types.get(error_type, 0) + 1

        return {
            "failure_types": failure_types,
            "recoverable": len(failed_tasks) < len(state.task_results) // 2,
            "suggested_action": "retry" if len(failed_tasks) <= 2 else "manual_review"
        }

    def _categorize_error(self, error_message: str) -> str:
        error_lower = error_message.lower()
        if "timeout" in error_lower or "connection" in error_lower:
            return "network_error"
        elif "auth" in error_lower or "permission" in error_lower:
            return "auth_error"
        elif "not found" in error_lower:
            return "not_found_error"
        else:
            return "unknown_error"

    async def _create_session_summary(self, state: WorkflowState) -> str:
        completed = sum(1 for result in state.task_results.values()
                       if result.status == TaskStatus.COMPLETED)
        total = len(state.task_results)

        return f"세션 완료: {completed}/{total} 작업 성공 (성공률: {completed/total*100:.1f}%)"

# 워크플로우 인스턴스
agentic_workflow = AgenticWorkflow()