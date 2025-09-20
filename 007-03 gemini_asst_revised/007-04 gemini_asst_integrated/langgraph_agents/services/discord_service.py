import discord
import os
import aiohttp
import re
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import SystemMessage, HumanMessage

from ..agents.base_agent import BaseAgent
from ..state.models import WorkflowState, ExecutionResult, TaskStatus

class DiscordAgent(BaseAgent):
    def __init__(self):
        super().__init__("discord_agent")
        self.bot_token = os.getenv("DISCORD_TOKEN")
        self.channel_id = int(os.getenv("DISCORD_CHANNEL_ID", 0))
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro",
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.3
        )

    async def execute(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        try:
            action = task_params.get("action", "send_message")

            if action == "send_message":
                result = await self._send_message(task_params)
            elif action == "summarize_url":
                result = await self._summarize_url(task_params)
            elif action == "send_completion_summary":
                result = await self._send_completion_summary(task_params, state)
            else:
                raise ValueError(f"Unknown action: {action}")

            return ExecutionResult(
                task_id=task_params.get("task_id", "discord_task"),
                status=TaskStatus.COMPLETED,
                result=result
            )

        except Exception as e:
            return ExecutionResult(
                task_id=task_params.get("task_id", "discord_task"),
                status=TaskStatus.FAILED,
                error=str(e)
            )

    async def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        content = params.get("content", "메시지 내용이 없습니다.")
        channel_id = params.get("channel_id", self.channel_id)

        # Discord REST API 사용
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json"
        }
        data = {"content": content}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "message_id": result["id"],
                        "channel_id": channel_id,
                        "content": content,
                        "sent": True
                    }
                else:
                    error_text = await response.text()
                    raise Exception(f"Discord API error: {response.status} - {error_text}")

    async def _summarize_url(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = params.get("url")
        if not url:
            raise ValueError("URL is required for summarization")

        # URL에서 컨텐츠 가져오기
        content = await self._fetch_url_content(url)

        # Gemini로 요약
        summary = await self._generate_summary(url, content)

        # Discord에 요약 결과 전송
        summary_message = f"🔗 **URL 요약**\n📍 {url}\n\n📄 **요약**\n{summary}"

        send_result = await self._send_message({
            "content": summary_message,
            "channel_id": params.get("output_channel_id", self.channel_id)
        })

        return {
            "url": url,
            "summary": summary,
            "message_sent": send_result.get("sent", False)
        }

    async def _fetch_url_content(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        text = await response.text()
                        # HTML 태그 제거 (간단한 방식)
                        clean_text = re.sub(r'<[^>]+>', '', text)
                        # 첫 2000자만 사용 (Gemini 토큰 제한)
                        return clean_text[:2000]
                    else:
                        return f"페이지를 불러올 수 없습니다. (상태코드: {response.status})"
            except Exception as e:
                return f"URL 접근 오류: {str(e)}"

    async def _generate_summary(self, url: str, content: str) -> str:
        system_prompt = """
당신은 웹페이지 내용을 간결하고 명확하게 요약하는 전문가입니다.

요약 규칙:
1. 핵심 내용을 3-5줄로 요약
2. 중요한 키워드는 **굵게** 표시
3. 링크가 YouTube인 경우 동영상 주제 중심으로 요약
4. 기술 문서인 경우 주요 기능과 사용법 중심
5. 뉴스인 경우 5W1H 중심
6. 내용이 불분명하면 "요약하기 어려운 페이지입니다" 응답

응답은 한국어로, 친근하고 이해하기 쉽게 작성해주세요.
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"URL: {url}\n\n내용:\n{content}")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            return f"요약 생성 중 오류가 발생했습니다: {str(e)}"

    async def _send_completion_summary(self, params: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
        summary = params.get("summary", {})

        # 완료 요약 메시지 생성
        total_tasks = summary.get("total_tasks", 0)
        completed_tasks = summary.get("completed_tasks", 0)
        failed_tasks = summary.get("failed_tasks", 0)

        success_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        message = f"""
🤖 **작업 완료 보고서**

📝 **원본 요청**: {state.user_input[:100]}{'...' if len(state.user_input) > 100 else ''}

📊 **실행 결과**
• 전체 작업: {total_tasks}개
• 완료: {completed_tasks}개 ✅
• 실패: {failed_tasks}개 ❌
• 성공률: {success_rate:.1f}%

⏱️ **소요 시간**: {self._format_duration(state)}

{self._get_status_emoji(success_rate)} **상태**: {self._get_status_text(success_rate)}
        """.strip()

        return await self._send_message({"content": message})

    def _format_duration(self, state: WorkflowState) -> str:
        from datetime import datetime
        duration = (datetime.now() - state.created_at).total_seconds()
        if duration < 60:
            return f"{duration:.1f}초"
        else:
            return f"{duration/60:.1f}분"

    def _get_status_emoji(self, success_rate: float) -> str:
        if success_rate >= 100:
            return "🎉"
        elif success_rate >= 80:
            return "✅"
        elif success_rate >= 60:
            return "⚠️"
        else:
            return "❌"

    def _get_status_text(self, success_rate: float) -> str:
        if success_rate >= 100:
            return "모든 작업이 성공적으로 완료되었습니다!"
        elif success_rate >= 80:
            return "대부분의 작업이 완료되었습니다."
        elif success_rate >= 60:
            return "일부 작업에서 문제가 발생했습니다."
        else:
            return "다수의 작업이 실패했습니다. 확인이 필요합니다."