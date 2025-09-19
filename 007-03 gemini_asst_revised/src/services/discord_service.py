import discord
from discord.ext import commands
import asyncio
import logging
from datetime import datetime
from typing import Set

from config.settings import settings
from config.logging_config import setup_logging
from models.task_models import MessageData, TaskResult
from services.gemini_service import GeminiService
from services.notion_service import NotionService

logger = logging.getLogger(__name__)

class DiscordService:
    """Discord 봇 서비스"""

    def __init__(self):
        self.processed_messages: Set[int] = set()
        self.gemini_service = GeminiService()
        self.notion_service = NotionService()
        self._setup_bot()

    def _setup_bot(self):
        """Discord 봇 설정"""
        # Discord 인텐트 설정
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True

        # Discord 봇 생성
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        self._register_events()
        self._register_commands()

    def _register_events(self):
        """이벤트 핸들러 등록"""

        @self.bot.event
        async def on_ready():
            logger.info(f'🤖 {self.bot.user}가 로그인되었습니다!')
            logger.info(f'🔗 연결된 서버: {len(self.bot.guilds)}개')

        @self.bot.event
        async def on_message(message):
            # 봇 자신의 메시지는 무시
            if message.author == self.bot.user:
                return

            # 특정 채널에서만 처리
            if settings.DISCORD_CHANNEL_ID and str(message.channel.id) != settings.DISCORD_CHANNEL_ID:
                return

            # 이미 처리된 메시지는 건너뛰기
            if message.id in self.processed_messages:
                return

            await self._process_message(message)
            await self.bot.process_commands(message)

    def _register_commands(self):
        """명령어 등록"""

        @self.bot.command(name='test')
        async def test_command(ctx):
            """봇 상태 테스트"""
            embed = discord.Embed(
                title="🧪 테스트",
                description="봇이 정상적으로 작동하고 있습니다!",
                color=0x0099ff
            )

            embed.add_field(
                name="🔧 설정 정보",
                value=(
                    f"채널 ID: {settings.DISCORD_CHANNEL_ID or '설정 안됨'}\n"
                    f"Gemini API: {'✅' if settings.GEMINI_API_KEY else '❌'}\n"
                    f"Notion API: {'✅' if settings.NOTION_API_KEY else '❌'}"
                ),
                inline=False
            )

            await ctx.send(embed=embed)

        @self.bot.command(name='help_setup')
        async def help_setup(ctx):
            """설정 도움말"""
            embed = discord.Embed(
                title="⚙️ 봇 설정 도움말",
                description="AI Task Tracker 봇 설정 방법을 안내합니다.",
                color=0x0099ff
            )

            embed.add_field(
                name="🤖 Gemini 설정",
                value="• GEMINI_API_KEY 환경변수 설정",
                inline=False
            )

            embed.add_field(
                name="📝 Notion 설정",
                value="• NOTION_API_KEY 설정\n• Task Tracker 데이터베이스 연결",
                inline=False
            )

            embed.add_field(
                name="💬 Discord 설정",
                value="• DISCORD_BOT_TOKEN 설정\n• DISCORD_CHANNEL_ID 설정 (선택사항)",
                inline=False
            )

            await ctx.send(embed=embed)

    async def _process_message(self, message):
        """메시지 처리 메인 로직"""
        try:
            # 메시지 처리 시작 로깅
            logger.info(f"📨 메시지 수신: {message.content[:50]}... by {message.author.name}")

            # 처리된 메시지로 표시
            self.processed_messages.add(message.id)

            # 진행 중 이모지 추가
            await message.add_reaction('🤖')

            # 메시지 데이터 생성
            message_data = MessageData(
                content=message.content,
                author=str(message.author),
                channel=str(message.channel),
                timestamp=message.created_at,
                message_id=str(message.id)
            )

            # Gemini로 메시지 분석
            processed_task = await self.gemini_service.analyze_message(
                message_data.content,
                message_data.author,
                message_data.timestamp
            )

            # 분석 실패 시 기본값으로 처리
            if not processed_task:
                logger.warning("Gemini 분석 실패, 기본값으로 Task 생성")
                from models.task_models import ProcessedTask
                processed_task = ProcessedTask(
                    title=message_data.content[:50] + '...' if len(message_data.content) > 50 else message_data.content,
                    category='미분류',
                    priority='Medium',
                    summary=message_data.content,
                    tags=[],
                    action_required=True,
                    notes='AI 분석 실패로 기본값 적용'
                )

            # Notion에 Task 생성
            result = await self.notion_service.create_task(message_data, processed_task)

            # 진행 중 이모지 제거
            await message.remove_reaction('🤖', self.bot.user)

            # 결과에 따른 응답
            await self._send_result_message(message, result)

        except Exception as e:
            logger.error(f"💥 메시지 처리 중 예상치 못한 오류: {e}")

            try:
                await message.remove_reaction('🤖', self.bot.user)
                await message.add_reaction('💥')

                error_embed = discord.Embed(
                    title="💥 시스템 오류",
                    description=f"예상치 못한 오류가 발생했습니다: {str(e)[:500]}",
                    color=0xff0000
                )

                await message.reply(embed=error_embed)
            except:
                pass

    async def _send_result_message(self, message, result: TaskResult):
        """처리 결과에 따른 메시지 전송"""
        if result.success:
            # 성공 이모지 추가
            await message.add_reaction('✅')

            # 성공 메시지 전송
            embed = discord.Embed(
                title="🎯 작업 완료!",
                description=result.message,
                color=0x00ff00
            )

            # 추가 상세 정보
            if result.details:
                for key, value in result.details.items():
                    if value and key not in ['created_at']:
                        embed.add_field(
                            name=key.replace('_', ' ').title(),
                            value=str(value)[:1024],
                            inline=True
                        )

            await message.reply(embed=embed)
            logger.info(f"✅ Task 생성 성공")

        else:
            # 실패 이모지 추가
            await message.add_reaction('❌')

            # 오류 메시지 전송
            error_embed = discord.Embed(
                title="❌ 처리 실패",
                description=f"**오류**: {result.error or '알 수 없는 오류'}",
                color=0xff0000
            )

            await message.reply(embed=error_embed)
            logger.error(f"❌ Task 생성 실패: {result.error}")

    def run(self):
        """봇 실행"""
        if not settings.DISCORD_BOT_TOKEN:
            logger.error("❌ DISCORD_BOT_TOKEN이 설정되지 않았습니다!")
            return

        logger.info("🚀 Discord 봇 시작...")
        logger.info(f"🎯 대상 채널 ID: {settings.DISCORD_CHANNEL_ID or '모든 채널'}")

        try:
            self.bot.run(settings.DISCORD_BOT_TOKEN)
        except Exception as e:
            logger.error(f"❌ 봇 실행 실패: {e}")