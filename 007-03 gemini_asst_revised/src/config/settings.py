import os
from typing import Optional
import logging

# 안전한 환경변수 로딩
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as e:
    logging.warning(f".env 파일 로딩 실패, 시스템 환경변수 사용: {e}")

class Settings:
    """애플리케이션 설정 관리 클래스"""

    # Discord 설정
    DISCORD_BOT_TOKEN: str = os.getenv('DISCORD_BOT_TOKEN', '')
    DISCORD_CHANNEL_ID: str = os.getenv('DISCORD_CHANNEL_ID', '')

    # Gemini AI 설정
    GEMINI_API_KEY: str = os.getenv('GEMINI_API_KEY', '')

    # Notion 설정
    NOTION_API_KEY: str = os.getenv('NOTION_API_KEY', '')
    TASK_TRACKER_DATABASE_ID: str = "158b592202868001a536e6a1172f0c96"  # 새로운 페이지 ID

    @classmethod
    def validate_required_settings(cls) -> bool:
        """필수 설정 검증"""
        required = [
            ('DISCORD_BOT_TOKEN', cls.DISCORD_BOT_TOKEN),
            ('GEMINI_API_KEY', cls.GEMINI_API_KEY),
            ('NOTION_API_KEY', cls.NOTION_API_KEY),
        ]

        missing = [name for name, value in required if not value]

        if missing:
            raise ValueError(f"필수 환경변수가 설정되지 않았습니다: {', '.join(missing)}")

        return True

    @classmethod
    def get_masked_token(cls, token: str, show_chars: int = 4) -> str:
        """토큰을 마스킹하여 안전하게 로깅"""
        if not token:
            return "NOT_SET"
        if len(token) <= show_chars * 2:
            return "*" * len(token)
        return token[:show_chars] + "*" * (len(token) - show_chars * 2) + token[-show_chars:]

settings = Settings()