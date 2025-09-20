import re
import json
from typing import Dict, Any, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import SystemMessage, HumanMessage

from .base_agent import BaseAgent
from ..state.models import WorkflowState, ExecutionResult, TaskStatus, TaskIntent, TaskType, Priority

class IntentRouterAgent(BaseAgent):
    def __init__(self, gemini_api_key: str):
        super().__init__("intent_router")
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro",
            google_api_key=gemini_api_key,
            temperature=0.1
        )

    async def execute(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        try:
            user_input = state.user_input.strip()

            # LLM을 통한 의도 분석
            intent_analysis = await self._analyze_intent(user_input)

            # TaskIntent 객체들로 변환
            intents = self._parse_intents(intent_analysis)

            # 상태 업데이트
            await self._update_state(state, intents)

            return ExecutionResult(
                task_id=task_params.get("task_id", "intent_analysis"),
                status=TaskStatus.COMPLETED,
                result={
                    "intents": [intent.dict() for intent in intents],
                    "is_multi_task": len(intents) > 1,
                    "analysis": intent_analysis
                }
            )

        except Exception as e:
            return ExecutionResult(
                task_id=task_params.get("task_id", "intent_analysis"),
                status=TaskStatus.FAILED,
                error=str(e)
            )

    async def _analyze_intent(self, user_input: str) -> Dict[str, Any]:
        system_prompt = """
당신은 Discord 메모를 분석하여 사용자의 의도를 파악하는 AI 어시스턴트입니다.

**분석 가능한 작업 유형:**
1. NOTION: 할 일, 메모, 작업 기록 등
2. CALENDAR: 일정 등록, 수정, 조회 등
3. GMAIL: 이메일 발송, 회신 등
4. DISCORD: URL 요약, 채널 메시지 등

**응답 형식 (JSON):**
{
  "intents": [
    {
      "type": "notion|calendar|gmail|discord",
      "action": "구체적인 행동 설명",
      "parameters": {
        "key": "value"
      },
      "priority": "low|medium|high|urgent",
      "dependencies": ["다른 작업의 task_id"]
    }
  ],
  "confidence": 0.0-1.0,
  "reasoning": "분석 근거 설명"
}

**분석 예시:**
- "내일 회의 일정 잡고 참석자들에게 메일 보내줘"
  → CALENDAR(일정등록) + GMAIL(메일발송), dependencies 설정
- "https://youtube.com/watch?v=123 이거 요약해줘"
  → DISCORD(URL 요약)
- "프로젝트 진행상황 정리해서 노션에 올려줘"
  → NOTION(문서작성)

**중요 규칙:**
- 복수 작업 시 의존성을 명확히 설정
- 우선순위를 적절히 판단
- 불명확한 요청은 confidence를 낮게 설정
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"분석할 메모: {user_input}")
        ]

        response = await self.llm.ainvoke(messages)

        try:
            # JSON 추출
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                raise ValueError("JSON 형식의 응답을 찾을 수 없습니다")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 파싱 오류: {e}")

    def _parse_intents(self, analysis: Dict[str, Any]) -> List[TaskIntent]:
        intents = []

        for i, intent_data in enumerate(analysis.get("intents", [])):
            try:
                intent = TaskIntent(
                    type=TaskType(intent_data["type"]),
                    action=intent_data["action"],
                    parameters=intent_data.get("parameters", {}),
                    priority=Priority(intent_data.get("priority", "medium")),
                    dependencies=intent_data.get("dependencies", [])
                )

                # task_id 자동 생성
                intent.parameters["task_id"] = f"{intent.type.value}_{i+1}"

                intents.append(intent)

            except (KeyError, ValueError) as e:
                self.logger.warning(f"Invalid intent data: {intent_data}, error: {e}")
                continue

        return intents

    async def _update_state(self, state: WorkflowState, intents: List[TaskIntent]):
        state.intents = intents
        state.is_multi_task = len(intents) > 1
        state.current_step = "intent_analyzed"

        # 컨텍스트 업데이트
        state.context.update({
            "total_tasks": len(intents),
            "task_types": [intent.type.value for intent in intents],
            "has_dependencies": any(intent.dependencies for intent in intents)
        })

    async def validate_params(self, params: Dict[str, Any]) -> bool:
        return True