#!/usr/bin/env python3
"""
Reflection 기반 개선된 Discord 봇
실제 LangGraph 워크플로우를 직접 호출
"""
import asyncio
import os
import sys
import discord
import logging
import time
from discord.ext import commands
from dotenv import load_dotenv

# 프로젝트 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'langgraph_agents'))

# 환경변수 로드
load_dotenv(os.path.join(os.path.dirname(__file__), 'langgraph_agents', '.env'))

# Reflection 시스템 import
from reflection_system import ImprovedDiscordBot

# LangGraph 모듈들
from langgraph_agents.state.manager import state_manager
from langgraph_agents.agents.base_agent import agent_executor
from langgraph_agents.agents.intent_router import IntentRouterAgent
from langgraph_agents.agents.action_planner import ActionPlannerAgent
from langgraph_agents.services.gmail_service import GmailAgent
from langgraph_agents.services.notion_service import NotionAgent
from langgraph_agents.services.gmail_contacts_manager import get_contacts_manager
from langgraph_agents.workflows.graph_definition import agentic_workflow

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('improved_discord_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

logger.info("🤖 개선된 Discord Bot 시작 (Reflection + LangGraph)")
logger.info("=" * 60)

# 환경 확인
logger.info(f"📋 Discord Token: {'설정됨' if os.getenv('DISCORD_TOKEN') else '❌ 없음'}")
logger.info(f"📧 Gmail: {os.getenv('GMAIL_EMAIL', '없음')}")
logger.info(f"🔑 Gemini API: {'설정됨' if os.getenv('GEMINI_API_KEY') else '❌ 없음'}")
logger.info(f"📊 LangSmith: {'설정됨' if os.getenv('LANGCHAIN_API_KEY') else '❌ 없음'}")

# Discord 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 타겟 채널 설정
TARGET_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))

# Reflection 기반 봇 인스턴스
reflection_bot = None

# 중복 메시지 처리 방지를 위한 캐시 (메시지 ID → 타임스탬프)
_recent_msg_ids = {}

# 메시지별 처리 락 (동일 메시지 동시 처리 방지)
_processing_locks = {}
_processing_lock = asyncio.Lock()

@bot.event
async def on_ready():
    global reflection_bot

    logger.info(f'✅ {bot.user}로 로그인했습니다!')
    logger.info(f'🎯 타겟 채널 ID: {TARGET_CHANNEL_ID}')

    # 길드 정보 출력
    for guild in bot.guilds:
        logger.info(f'📋 연결된 서버: {guild.name} (ID: {guild.id})')
        for channel in guild.text_channels:
            if channel.id == TARGET_CHANNEL_ID:
                logger.info(f'   🎯 타겟 채널: #{channel.name} (ID: {channel.id})')

    # StateManager 시작
    await state_manager.start()
    logger.info('📊 StateManager 시작됨')

    # 실제 에이전트들 등록
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if gemini_api_key:
        try:
            agent_executor.register_agent(IntentRouterAgent(gemini_api_key))
            logger.info('🎯 IntentRouterAgent 등록됨')

            agent_executor.register_agent(ActionPlannerAgent(gemini_api_key))
            logger.info('📋 ActionPlannerAgent 등록됨')
        except Exception as e:
            logger.error(f"❌ Gemini 에이전트 등록 실패: {e}")

    # 연락처 매니저 초기화
    contacts_manager = get_contacts_manager()
    status = contacts_manager.get_api_status()

    if status['gmail_service_ready']:
        logger.info('📞 Gmail API 연락처 동기화: ✅ 활성화')
    else:
        logger.info('📞 Gmail API 연락처 동기화: ⚠️ 비활성화 (하드코딩 사용)')

    # 서비스 에이전트들
    agent_executor.register_agent(GmailAgent())
    logger.info('📧 GmailAgent 등록됨')

    agent_executor.register_agent(NotionAgent())
    logger.info('📝 NotionAgent 등록됨')

    # Reflection 봇 초기화
    reflection_bot = ImprovedDiscordBot()
    # Gmail API 초기화 시도
    await reflection_bot.initialize()
    logger.info('🧠 Reflection 시스템 초기화 완료')

    logger.info('🔧 모든 에이전트 등록 완료!')

@bot.event
async def on_message(message):
    """단일 진입점 패턴으로 동시 처리 방지"""
    global _recent_msg_ids, _processing_locks, _processing_lock

    logger.info(f"🔍 메시지 감지: '{message.content}' from {message.author} in #{message.channel.name} (ID: {message.channel.id})")

    # 봇 자신의 메시지는 무시
    if message.author == bot.user:
        logger.info("⏭️ 봇 자신의 메시지, 무시")
        return

    # [BLOCK] 11번 채널(Success Logic)은 절대 처리하지 않음
    BLOCKED_CHANNEL_ID = 1425020218182467665  # 11-success-logic 채널
    if message.channel.id == BLOCKED_CHANNEL_ID:
        logger.info(f"🚫 차단된 채널 (11-success-logic), 무시")
        return

    # 타겟 채널에서만 반응 (초기 필터링)
    if TARGET_CHANNEL_ID and message.channel.id != TARGET_CHANNEL_ID:
        logger.info(f"⏭️ 타겟 채널({TARGET_CHANNEL_ID})이 아님, 현재: {message.channel.id}")
        return

    # [CRITICAL] 메시지별 동시 처리 방지 락
    async with _processing_lock:
        # 이미 처리 중인 메시지 확인
        if message.id in _processing_locks:
            logger.warning(f"🔒 메시지 {message.id}가 이미 처리 중 - 중복 요청 무시")
            return

        # 처리 락 설정
        _processing_locks[message.id] = asyncio.Lock()

    # 메시지별 개별 락으로 처리
    async with _processing_locks[message.id]:
        try:
            # 중복 메시지 처리 방지 (5초 캐시) - 락 내부에서 다시 확인
            now = time.time()
            if message.id in _recent_msg_ids and (now - _recent_msg_ids[message.id]) < 5:
                logger.info(f"⏭️ 중복 메시지 무시: {message.id}")
                return
            _recent_msg_ids[message.id] = now

            # 오래된 캐시 정리 (10개 이상이면 정리)
            if len(_recent_msg_ids) > 10:
                cutoff = now - 30  # 30초 이전 항목 삭제
                _recent_msg_ids = {mid: ts for mid, ts in _recent_msg_ids.items() if ts > cutoff}

            logger.info(f"✅ 메시지 처리 시작: {message.content}")

            # [DISCORD] 핵심 로그 포인트 1 - 동시성 정보 포함
            logger.info(f"[DISCORD] msg_id={message.id} user={message.author} content={message.content[:80]!r} processing_locks_count={len(_processing_locks)}")

            # 기본 응답
            await message.reply("🤖 Reflection 기반 처리 시작합니다...")

            # Reflection 기반 처리
            if reflection_bot:
                logger.info("🧠 Reflection 시스템으로 처리")
                # Discord 메시지 ID를 포함한 고유 식별자 생성 (LangGraph 스레드 충돌 방지)
                unique_user_id = f"{message.author}_{message.id}"
                result = await reflection_bot.process_message(message.content, unique_user_id)

                # 결과 분석 및 응답
                await _handle_reflection_result(message, result)
            else:
                logger.error("❌ Reflection 봇이 초기화되지 않음")
                await message.reply("❌ 시스템이 아직 준비되지 않았습니다.")

        except Exception as e:
            logger.error(f"❌ 메시지 처리 오류 (msg_id={message.id}): {e}")
            import traceback
            traceback.print_exc()
            await message.reply(f"❌ 처리 중 오류가 발생했습니다: {str(e)}")

        finally:
            # 처리 완료 후 락 정리
            async with _processing_lock:
                if message.id in _processing_locks:
                    del _processing_locks[message.id]
                    logger.info(f"🔓 메시지 {message.id} 처리 락 해제")


async def _handle_reflection_result(message, result):
    """Reflection 결과 처리 (분리된 함수로 중복 방지)"""
    execution_result = result['execution_result']
    reflection_result = result['reflection']

    if execution_result.get('success'):
        await message.reply("✅ 작업 완료!")

        # 상세 결과 출력 (유효한 수신자가 있을 때만)
        details = []
        recips = execution_result.get('recipients', [])
        if recips and isinstance(recips, list) and len(recips) > 0:
            # 유효한 이메일만 표시 (@와 도메인 확인)
            valid_recips = [r for r in recips if isinstance(r, str) and "@" in r and "." in r.split("@")[-1]]
            if valid_recips:
                details.append(f"📧 수신자: {', '.join(valid_recips)}")

        if execution_result.get('improvements_applied'):
            details.append(f"🔧 적용된 개선사항: {', '.join(execution_result['improvements_applied'])}")

        if execution_result.get('workflow_result'):
            details.append("⚡ LangGraph 워크플로우 실행됨")

        if details:
            await message.reply("\n".join(details))

        # Reflection 학습 내용
        if reflection_result['issues']:
            await message.reply(f"🔍 발견된 문제점: {', '.join(reflection_result['issues'])}")

        if reflection_result['improvements']:
            await message.reply(f"💡 제안된 개선사항: {', '.join(reflection_result['improvements'])}")

    else:
        await message.reply(f"❌ 작업 실패")
        if execution_result.get('error'):
            await message.reply(f"오류: {execution_result['error']}")

# 하드코딩 연락처 제거됨 - Gmail API만 사용

async def update_contact_mapping():
    """연락처 매핑 업데이트 (Gmail API 기반)"""
    global reflection_bot
    if reflection_bot:
        logger.info("📞 Gmail API 연락처 동기화 완료")

# 봇 실행
if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("❌ DISCORD_TOKEN이 설정되지 않았습니다!")
        exit(1)

    try:
        logger.info("🚀 개선된 Discord 봇 시작 중...")
        bot.run(token)
    except KeyboardInterrupt:
        logger.info("\n👋 봇을 종료합니다.")
    except Exception as e:
        logger.error(f"\n❌ 봇 실행 오류: {e}")
        import traceback
        traceback.print_exc()