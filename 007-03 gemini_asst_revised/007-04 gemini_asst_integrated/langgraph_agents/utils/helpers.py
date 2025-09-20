import re
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

def extract_urls_from_text(text: str) -> List[str]:
    """텍스트에서 URL 추출"""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(url_pattern, text)

def is_url_request(text: str) -> bool:
    """URL 요약 요청인지 판단"""
    urls = extract_urls_from_text(text)
    summary_keywords = ['요약', 'summary', '정리', '설명']

    return len(urls) > 0 and any(keyword in text.lower() for keyword in summary_keywords)

def extract_email_info(text: str) -> Optional[Dict[str, Any]]:
    """이메일 발송 정보 추출"""
    email_keywords = ['메일', 'email', '이메일', '보내']
    if not any(keyword in text.lower() for keyword in email_keywords):
        return None

    # 수신자 추출 (간단한 패턴)
    recipient_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    recipients = re.findall(recipient_pattern, text)

    # 제목 추출
    subject_patterns = [
        r'제목[:\s]*([^\n\r]+)',
        r'subject[:\s]*([^\n\r]+)',
        r'title[:\s]*([^\n\r]+)'
    ]

    subject = None
    for pattern in subject_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            subject = match.group(1).strip()
            break

    return {
        'recipients': recipients,
        'subject': subject,
        'content': text
    } if recipients or subject else None

def extract_calendar_info(text: str) -> Optional[Dict[str, Any]]:
    """일정 정보 추출"""
    calendar_keywords = ['일정', '회의', '미팅', '약속', 'meeting', 'schedule']
    if not any(keyword in text.lower() for keyword in calendar_keywords):
        return None

    # 날짜 패턴 (다양한 형식)
    date_patterns = [
        r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # 2024-01-01, 2024/01/01
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # 01-01-2024, 01/01/2024
        r'(내일|tomorrow)',
        r'(오늘|today)',
        r'(다음주|next week)',
    ]

    # 시간 패턴
    time_patterns = [
        r'(\d{1,2}):(\d{2})',  # 14:30
        r'(\d{1,2})시\s*(\d{1,2})?분?',  # 2시 30분, 2시
        r'(오전|오후|AM|PM)\s*(\d{1,2}):?(\d{2})?',  # 오후 2:30
    ]

    dates = []
    times = []

    for pattern in date_patterns:
        dates.extend(re.findall(pattern, text, re.IGNORECASE))

    for pattern in time_patterns:
        times.extend(re.findall(pattern, text, re.IGNORECASE))

    # 참석자 추출
    attendee_patterns = [
        r'참석자[:\s]*([^\n\r]+)',
        r'attendees?[:\s]*([^\n\r]+)',
        r'와[함께]*\s*([^\n\r]+)',
    ]

    attendees = []
    for pattern in attendee_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        attendees.extend(matches)

    return {
        'dates': dates,
        'times': times,
        'attendees': attendees,
        'content': text
    } if dates or times else None

def clean_text(text: str) -> str:
    """텍스트 정리"""
    # 연속된 공백 제거
    text = re.sub(r'\s+', ' ', text)
    # 앞뒤 공백 제거
    text = text.strip()
    return text

def format_json_for_llm(data: Dict[str, Any]) -> str:
    """LLM이 이해하기 쉬운 JSON 형식으로 변환"""
    return json.dumps(data, ensure_ascii=False, indent=2)

def parse_llm_json_response(response: str) -> Optional[Dict[str, Any]]:
    """LLM 응답에서 JSON 추출"""
    # JSON 블록 찾기
    json_patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
        r'\{.*\}',
    ]

    for pattern in json_patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    return None

def estimate_task_complexity(text: str) -> str:
    """작업 복잡도 추정"""
    # 키워드 기반 복잡도 계산
    complex_keywords = [
        '일정', '메일', 'url', 'http', '요약', '회의', '참석자',
        '그리고', '이후', '완료되면', '동시에'
    ]

    keyword_count = sum(1 for keyword in complex_keywords if keyword in text.lower())

    if keyword_count >= 3:
        return "high"
    elif keyword_count >= 2:
        return "medium"
    else:
        return "low"

def generate_task_id(task_type: str, index: int = 1) -> str:
    """작업 ID 생성"""
    timestamp = datetime.now().strftime("%H%M%S")
    return f"{task_type}_{index}_{timestamp}"

def validate_environment_variables(required_vars: List[str]) -> List[str]:
    """환경변수 검증"""
    import os
    missing_vars = []

    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    return missing_vars

def mask_sensitive_data(text: str) -> str:
    """민감한 데이터 마스킹"""
    # 이메일 마스킹
    text = re.sub(r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                  r'\1***@\2', text)

    # API 키 패턴 마스킹
    text = re.sub(r'([a-zA-Z0-9]{8})[a-zA-Z0-9]{16,}', r'\1***', text)

    return text