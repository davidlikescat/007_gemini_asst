import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import google.generativeai as genai


logger = logging.getLogger(__name__)


class MemoRefiner:
    """Gemini 모델을 활용해 Discord 원문을 정제하고 업무 메타데이터를 생성."""

    FALLBACK_ANALYSIS: Dict[str, Any] = {
        "refined_summary": "",
        "category": "미분류",
        "priority": "Medium",
        "tags": [],
        "action_required": False,
        "notes": "AI 분석 실패로 기본값 적용",
        "analysis_success": False,
    }

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY 환경변수가 필요합니다.")

        genai.configure(api_key=api_key)

        preferred = os.getenv("GEMINI_LLM_MODEL")
        candidates = []
        if preferred:
            candidates.append(preferred)
        candidates.extend([
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-1.0-pro",
            "gemini-pro",
        ])

        self.model = None
        for name in candidates:
            try:
                self.model = genai.GenerativeModel(model_name=name)
                logger.info("MemoRefiner using Gemini model: %s", name)
                break
            except Exception as err:  # pylint: disable=broad-except
                logger.warning("Gemini 모델 %s 초기화 실패: %s", name, err)

        if not self.model:
            raise RuntimeError("사용 가능한 Gemini 모델을 찾을 수 없습니다.")

    async def analyze(self, text: str) -> Dict[str, Any]:
        """원문을 입력 받아 정제 요약 및 분류 정보를 반환."""
        prompt = (
            "너는 업무 메모를 정리하는 비서야. 아래 메시지를 분석해서 JSON으로만 답해.\n"
            "필수 키: refined_summary(간결한 한국어 정제 요약), category(짧은 카테고리),"
            " priority(LOW/MEDIUM/HIGH/URGENT 중 하나), tags(관련 키워드 배열),"
            " action_required(true/false), notes(추가 메모, 없으면 빈 문자열).\n"
            "JSON 이외의 설명은 포함하지 마.\n\n"
            f"메시지: {text}"
        )

        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config={"temperature": float(os.getenv("GEMINI_TEMPERATURE", "0.4"))},
            )
            raw = getattr(response, "text", "") or ""
            logger.debug("Gemini raw response: %s", raw)
            parsed = self._parse_json(raw)
            return self._normalize(parsed, original=text)
        except json.JSONDecodeError as err:
            logger.warning("Gemini JSON 파싱 실패: %s", err)
            return self._fallback(original=text, reason="JSON 파싱 실패")
        except Exception:
            logger.exception("Gemini 분석 호출 실패")
            return self._fallback(original=text, reason="Gemini 호출 실패")

    @classmethod
    def _fallback(cls, original: str, reason: str = "") -> Dict[str, Any]:
        data = dict(cls.FALLBACK_ANALYSIS)
        data["refined_summary"] = original.strip()
        if reason:
            data["notes"] = reason
        return data

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        text = (content or "").strip()

        if text.startswith("```"):
            text = text.strip("`")
            if "\n" in text:
                text = text.split("\n", 1)[1]
            text = text.lstrip()
            if text.lower().startswith("json"):
                text = text[4:].lstrip()

        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)

        return json.loads(text)

    @staticmethod
    def _extract_text(content: Optional[str]) -> str:
        if not content:
            return ""
        return str(content).strip()

    def _normalize(self, data: Dict[str, Any], original: str) -> Dict[str, Any]:
        """JSON 응답을 안전하게 정규화. 실패 시 fallback 구조 반환."""
        if not isinstance(data, dict):
            return self._fallback(original)

        refined = data.get("refined_summary") or original.strip()

        priority = (data.get("priority") or "Medium").strip().upper()
        priority_map = {
            "LOW": "Low",
            "MEDIUM": "Medium",
            "MID": "Medium",
            "HIGH": "High",
            "URGENT": "Urgent",
        }
        normalized_priority = priority_map.get(priority, "Medium")

        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        elif isinstance(tags, (int, float)):
            tags = [str(tags)]
        elif not isinstance(tags, list):
            tags = []

        analysis_success = data.get("analysis_success")
        if analysis_success is None:
            analysis_success = True

        normalized = {
            "refined_summary": refined,
            "category": (data.get("category") or "미분류").strip(),
            "priority": normalized_priority,
            "tags": tags,
            "action_required": bool(data.get("action_required")),
            "notes": (data.get("notes") or "").strip(),
            "analysis_success": analysis_success,
        }

        return normalized
