#!/usr/bin/env python3
"""
LangGraph 기반 Agentic AI 시스템
Discord 메시지를 Multi-Agent로 처리하는 비선형 워크플로우
"""

import asyncio
import logging
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from state.manager import state_manager
from agents.base_agent import agent_executor
from agents.intent_router import IntentRouterAgent
from agents.task_decomposer import TaskDecomposerAgent
from agents.reflection_agent import SelfReflectionAgent
from services.notion_service import NotionAgent
from services.discord_service import DiscordAgent
from workflows.graph_definition import agentic_workflow

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('agentic_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class AgenticBot:
    def __init__(self):
        self.setup_discord()
        self.setup_agents()

    def setup_discord(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True

        self.bot = commands.Bot(command_prefix='!', intents=intents)
        self.target_channel_id = int(os.getenv('DISCORD_CHANNEL_ID', 0))

        @self.bot.event
        async def on_ready():
            logger.info(f'🤖 {self.bot.user}가 로그인되었습니다!')
            logger.info(f'🎯 타겟 채널 ID: {self.target_channel_id}')

            # StateManager 시작
            await state_manager.start()
            logger.info('📊 StateManager 시작됨')

        @self.bot.event
        async def on_message(message):
            # 봇 자신의 메시지는 무시
            if message.author == self.bot.user:
                return

            # 타겟 채널에서만 반응
            if self.target_channel_id and message.channel.id != self.target_channel_id:
                return

            # 메시지 처리
            await self.process_message(message)

    def setup_agents(self):
        gemini_api_key = os.getenv('GEMINI_API_KEY')

        # Agent 등록
        agent_executor.register_agent(IntentRouterAgent(gemini_api_key))
        agent_executor.register_agent(TaskDecomposerAgent())
        agent_executor.register_agent(SelfReflectionAgent(gemini_api_key))
        agent_executor.register_agent(NotionAgent())
        agent_executor.register_agent(DiscordAgent())

        logger.info('🔧 모든 Agent가 등록되었습니다')

    async def process_message(self, message):
        try:
            logger.info(f'📨 새 메시지 처리 시작: {message.content[:50]}...')

            # 세션 생성
            session_id = await state_manager.create_session(
                user_input=message.content,
                original_message=message.content
            )

            # 워크플로우 상태 가져오기
            workflow_state = await state_manager.get_session(session_id)
            if not workflow_state:
                logger.error(f'세션을 찾을 수 없습니다: {session_id}')
                return

            # LangGraph 워크플로우 실행
            result = await agentic_workflow.graph.ainvoke(workflow_state)

            logger.info(f'✅ 워크플로우 완료: {session_id}')

            # 세션 정리
            await state_manager.close_session(session_id)

        except Exception as e:
            logger.error(f'❌ 메시지 처리 중 오류: {e}')

            # 에러 응답 전송
            await message.channel.send(
                f'⚠️ 처리 중 오류가 발생했습니다: {str(e)[:100]}...'
            )

    async def run(self):
        try:
            token = os.getenv('DISCORD_TOKEN')
            if not token:
                raise ValueError('DISCORD_TOKEN이 설정되지 않았습니다!')

            await self.bot.start(token)

        except Exception as e:
            logger.error(f'봇 실행 중 오류: {e}')
            raise
        finally:
            await state_manager.stop()

async def main():
    # 필수 환경변수 검증
    required_vars = [
        'DISCORD_TOKEN',
        'DISCORD_CHANNEL_ID',
        'GEMINI_API_KEY',
        'NOTION_API_KEY',
        'NOTION_DATABASE_ID'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f'필수 환경변수가 누락되었습니다: {missing_vars}')
        return

    # 봇 실행
    bot = AgenticBot()
    await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('👋 봇이 정상적으로 종료되었습니다')
    except Exception as e:
        logger.error(f'예상치 못한 오류: {e}')