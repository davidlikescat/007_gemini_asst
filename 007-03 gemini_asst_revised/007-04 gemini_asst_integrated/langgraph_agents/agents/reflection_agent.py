import json
from typing import Dict, Any, List
from datetime import datetime, timedelta
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import SystemMessage, HumanMessage

from .base_agent import BaseAgent
from ..state.models import WorkflowState, ExecutionResult, TaskStatus
from ..state.manager import state_manager

class SelfReflectionAgent(BaseAgent):
    def __init__(self, gemini_api_key: str):
        super().__init__("self_reflection")
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro",
            google_api_key=gemini_api_key,
            temperature=0.3
        )

    async def execute(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        try:
            # 세션 실행 결과 분석
            performance_analysis = await self._analyze_session_performance(state)

            # 시스템 전체 메트릭 분석
            system_analysis = await self._analyze_system_metrics()

            # AI 기반 개선 제안
            improvement_suggestions = await self._generate_improvement_suggestions(
                state, performance_analysis, system_analysis
            )

            # 학습 데이터 업데이트
            await self._update_learning_data(state, performance_analysis)

            return ExecutionResult(
                task_id=task_params.get("task_id", "self_reflection"),
                status=TaskStatus.COMPLETED,
                result={
                    "session_analysis": performance_analysis,
                    "system_analysis": system_analysis,
                    "improvement_suggestions": improvement_suggestions,
                    "confidence_score": performance_analysis.get("overall_confidence", 0.8)
                }
            )

        except Exception as e:
            return ExecutionResult(
                task_id=task_params.get("task_id", "self_reflection"),
                status=TaskStatus.FAILED,
                error=str(e)
            )

    async def _analyze_session_performance(self, state: WorkflowState) -> Dict[str, Any]:
        total_tasks = len(state.task_results)
        if total_tasks == 0:
            return {"overall_score": 0.0, "details": "No tasks executed"}

        completed_tasks = sum(1 for result in state.task_results.values()
                            if result.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for result in state.task_results.values()
                         if result.status == TaskStatus.FAILED)

        success_rate = completed_tasks / total_tasks
        avg_execution_time = sum(result.execution_time or 0 for result in state.task_results.values()) / total_tasks
        avg_retry_count = sum(result.retry_count for result in state.task_results.values()) / total_tasks

        # 작업별 성능 분석
        task_performance = {}
        for task_id, result in state.task_results.items():
            task_performance[task_id] = {
                "status": result.status.value,
                "execution_time": result.execution_time,
                "retry_count": result.retry_count,
                "efficiency_score": self._calculate_efficiency_score(result)
            }

        return {
            "session_id": state.session_id,
            "overall_score": success_rate * 0.7 + (1 - min(avg_retry_count, 1)) * 0.3,
            "success_rate": success_rate,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "average_execution_time": avg_execution_time,
            "average_retry_count": avg_retry_count,
            "task_performance": task_performance,
            "session_duration": (datetime.now() - state.created_at).total_seconds(),
            "is_multi_task": state.is_multi_task
        }

    def _calculate_efficiency_score(self, result: ExecutionResult) -> float:
        if result.status != TaskStatus.COMPLETED:
            return 0.0

        # 실행 시간과 재시도 횟수를 기반으로 효율성 점수 계산
        time_penalty = min((result.execution_time or 0) / 30, 1.0)  # 30초 기준
        retry_penalty = result.retry_count * 0.2

        return max(1.0 - time_penalty - retry_penalty, 0.0)

    async def _analyze_system_metrics(self) -> Dict[str, Any]:
        system_metrics = await state_manager.get_system_metrics()

        return {
            "active_sessions": system_metrics["active_sessions"],
            "total_agents": system_metrics["total_agents"],
            "agent_performance": system_metrics["agent_metrics"],
            "system_health": self._assess_system_health(system_metrics)
        }

    def _assess_system_health(self, metrics: Dict[str, Any]) -> str:
        agent_metrics = metrics.get("agent_metrics", {})

        if not agent_metrics:
            return "unknown"

        avg_success_rate = sum(agent["success_rate"] for agent in agent_metrics.values()) / len(agent_metrics)
        avg_execution_time = sum(agent["average_execution_time"] for agent in agent_metrics.values()) / len(agent_metrics)

        if avg_success_rate > 0.9 and avg_execution_time < 10:
            return "excellent"
        elif avg_success_rate > 0.8 and avg_execution_time < 20:
            return "good"
        elif avg_success_rate > 0.6:
            return "fair"
        else:
            return "poor"

    async def _generate_improvement_suggestions(self, state: WorkflowState,
                                               performance: Dict[str, Any],
                                               system: Dict[str, Any]) -> List[str]:
        context = {
            "session_performance": performance,
            "system_metrics": system,
            "user_input": state.user_input,
            "task_types": [intent.type.value for intent in state.intents]
        }

        system_prompt = """
당신은 AI 시스템의 성능을 분석하고 개선 방안을 제시하는 전문가입니다.

다음 정보를 바탕으로 구체적이고 실행 가능한 개선 제안을 해주세요:
1. 성능이 낮은 작업 유형 식별
2. 실행 시간 최적화 방안
3. 재시도 횟수 감소 방안
4. 사용자 경험 개선 방안

JSON 형식으로 응답해주세요:
{
  "suggestions": [
    "구체적인 개선 제안 1",
    "구체적인 개선 제안 2"
  ],
  "priority_actions": [
    "우선순위 높은 액션"
  ]
}
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"분석 데이터: {json.dumps(context, default=str, ensure_ascii=False)}")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            result = json.loads(response.content)
            return result.get("suggestions", []) + result.get("priority_actions", [])
        except Exception as e:
            self.logger.error(f"Failed to generate improvement suggestions: {e}")
            return self._get_default_suggestions(performance)

    def _get_default_suggestions(self, performance: Dict[str, Any]) -> List[str]:
        suggestions = []

        if performance["success_rate"] < 0.8:
            suggestions.append("작업 실패율이 높습니다. 에러 처리 로직을 강화하세요.")

        if performance["average_retry_count"] > 1:
            suggestions.append("재시도가 빈번합니다. 초기 실행 안정성을 개선하세요.")

        if performance["average_execution_time"] > 15:
            suggestions.append("평균 실행 시간이 깁니다. 성능 최적화를 고려하세요.")

        return suggestions if suggestions else ["전반적으로 양호한 성능입니다."]

    async def _update_learning_data(self, state: WorkflowState, performance: Dict[str, Any]):
        learning_data = {
            "timestamp": datetime.now().isoformat(),
            "user_input_pattern": state.user_input[:50],  # 처음 50자만 저장
            "task_count": len(state.intents),
            "task_types": [intent.type.value for intent in state.intents],
            "success_rate": performance["success_rate"],
            "execution_time": performance["average_execution_time"],
            "improvement_needed": performance["overall_score"] < 0.8
        }

        # 상태에 학습 데이터 저장
        state.performance_metrics.update({
            "session_score": performance["overall_score"],
            "success_rate": performance["success_rate"],
            "execution_time": performance["average_execution_time"]
        })

        # 향후 ML 모델 학습을 위한 데이터 저장 (파일 또는 DB)
        # await self._save_learning_data(learning_data)

    async def validate_params(self, params: Dict[str, Any]) -> bool:
        return True