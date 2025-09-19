#!/usr/bin/env python3
"""
최적화된 Discord Task Bot
- Discord 메시지를 Gemini AI로 분석하여 Notion Task로 변환
"""

import sys
import logging
from pathlib import Path

# 현재 디렉토리를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings
from config.logging_config import setup_logging
from services.discord_service import DiscordService

def main():
    """메인 실행 함수"""
    # 로깅 설정
    logger = setup_logging()

    try:
        # 필수 설정 검증
        settings.validate_required_settings()
        logger.info("✅ 설정 검증 완료")

        # 설정 정보 로깅 (민감한 정보는 마스킹)
        logger.info(f"🎯 대상 채널: {settings.DISCORD_CHANNEL_ID or '모든 채널'}")
        logger.info(f"🤖 Gemini API: {settings.get_masked_token(settings.GEMINI_API_KEY)}")
        logger.info(f"📝 Notion API: {settings.get_masked_token(settings.NOTION_API_KEY)}")

        # Discord 서비스 실행
        discord_service = DiscordService()
        discord_service.run()

    except ValueError as e:
        logger.error(f"❌ 설정 오류: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 예상치 못한 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()