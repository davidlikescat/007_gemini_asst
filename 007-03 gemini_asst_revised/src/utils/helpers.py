"""유틸리티 함수들"""

def truncate_text(text: str, max_length: int = 50) -> str:
    """텍스트를 지정된 길이로 자르기"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

def mask_sensitive_info(text: str, show_chars: int = 4) -> str:
    """민감한 정보 마스킹"""
    if not text:
        return "NOT_SET"
    if len(text) <= show_chars * 2:
        return "*" * len(text)
    return text[:show_chars] + "*" * (len(text) - show_chars * 2) + text[-show_chars:]