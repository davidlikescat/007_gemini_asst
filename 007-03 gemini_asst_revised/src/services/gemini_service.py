import google.generativeai as genai
import json
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from config.settings import settings
from models.task_models import ProcessedTask

logger = logging.getLogger(__name__)

class GeminiService:
    """Gemini AI 서비스 클래스"""

    def __init__(self):
        self._setup_gemini()

    def _setup_gemini(self):
        """Gemini API 설정"""
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다!")

        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('models/gemini-1.5-pro')
        logger.info("Gemini API 설정 완료")

    async def analyze_message(self, content: str, author: str, timestamp: datetime) -> Optional[ProcessedTask]:
        """메시지를 분석하여 ProcessedTask 객체 반환"""
        try:
            kst = timezone(timedelta(hours=9))
            current_time = datetime.now(kst)

            prompt = self._create_analysis_prompt(content, author, timestamp, current_time)

            logger.info("Gemini에 분석 요청 전송")
            response = self.model.generate_content(prompt)

            logger.debug(f"Gemini 원본 응답: {response.text}")

            parsed_data = self._extract_json_from_response(response.text)

            if parsed_data:
                logger.info("Gemini 분석 성공")
                return ProcessedTask(
                    title=parsed_data.get('title', content[:50] + '...'),
                    category=parsed_data.get('category', '기타'),
                    priority=parsed_data.get('priority', 'Medium'),
                    summary=parsed_data.get('summary', ''),
                    tags=parsed_data.get('tags', []),
                    action_required=parsed_data.get('action_required', False),
                    due_date=parsed_data.get('due_date'),
                    notes=parsed_data.get('notes', '')
                )
            else:
                logger.error("Gemini 응답에서 유효한 JSON을 찾을 수 없음")
                return None

        except Exception as e:
            logger.error(f"Gemini 분석 실패: {str(e)}")
            return None

    def _create_analysis_prompt(self, content: str, author: str, timestamp: datetime, current_time: datetime) -> str:
        """분석용 프롬프트 생성"""
        return f"""
다음 Discord 메시지를 분석하고 정제하여 JSON으로만 응답해주세요.

메시지 내용: "{content}"
작성자: {author}
작성시간: {timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else 'Unknown'}
현재시간: {current_time.strftime('%Y-%m-%d %H:%M:%S')}

다음 형태로 JSON 응답해주세요:

{{
    "title": "메시지의 핵심 제목 (50자 이내)",
    "category": "업무|아이디어|정보|질문|기타 중 하나",
    "priority": "High|Medium|Low 중 하나",
    "summary": "메시지 내용을 정리한 요약 (100자 이내)",
    "tags": ["관련", "키워드", "목록"],
    "action_required": true/false,
    "due_date": "YYYY-MM-DD 형식 (언급된 경우만, 없으면 null)",
    "notes": "추가 분석 내용이나 컨텍스트"
}}

분석 규칙:
1. title: 메시지의 핵심을 한 줄로 요약
2. category: 내용 성격에 따라 분류
3. priority: 긴급성/중요도에 따라 판단
4. summary: 핵심 내용만 간단히 정리
5. tags: 검색에 유용한 키워드 3-5개
6. action_required: 후속 작업이 필요한지 판단
7. due_date: 날짜가 명시된 경우만 추출
8. notes: 컨텍스트나 추가 정보

JSON 이외의 어떤 텍스트도 포함하지 마세요.
"""

    def _extract_json_from_response(self, text: str) -> Optional[dict]:
        """응답에서 JSON 추출"""
        try:
            # 1. 코드 블록 안의 JSON 찾기
            code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
            matches = re.findall(code_block_pattern, text, re.DOTALL)

            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict):
                        logger.debug("코드 블록에서 JSON 추출 성공")
                        return parsed
                except json.JSONDecodeError:
                    continue

            # 2. 중괄호로 감싸진 JSON 패턴 찾기
            json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
            matches = re.findall(json_pattern, text, re.DOTALL)

            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict):
                        logger.debug("일반 패턴에서 JSON 추출 성공")
                        return parsed
                except json.JSONDecodeError:
                    continue

            return None

        except Exception as e:
            logger.error(f"JSON 추출 중 오류: {str(e)}")
            return None