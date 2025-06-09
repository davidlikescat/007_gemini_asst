import discord
from discord.ext import commands
import asyncio
from sub import ActionProcessor
import logging
import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)

# Discord 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ActionProcessor 인스턴스 생성
processor = ActionProcessor()

@bot.event
async def on_ready():
    logger.info(f'{bot.user}가 로그인되었습니다!')

@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 무시
    if message.author == bot.user:
        return
    
    # 특정 채널에서의 모든 메시지를 처리
    target_channel_id = os.getenv('TARGET_CHANNEL_ID')
    if target_channel_id and str(message.channel.id) != target_channel_id:
        return
    
    try:
        # 메시지 처리 시작
        logger.info(f"메시지 처리 시작: {message.content[:50]}...")
        
        # 진행 중 이모지 추가
        processing_emoji = await message.add_reaction('🤖')
        
        # 메시지 처리
        result = await processor.process_message(message)
        
        # 진행 중 이모지 제거
        await message.remove_reaction('🤖', bot.user)
        
        # 진행 상황 메시지 표시
        progress_msg = result.get('progress_message', '')
        if progress_msg:
            await message.reply(progress_msg)
        
        if result['success']:
            # 성공 이모지 추가
            await message.add_reaction('✅')
            
            # 상세한 완료 메시지 전송
            embed = discord.Embed(
                title="🎯 작업 완료!",
                description=result.get('response_message', '✅ 처리가 완료되었습니다.'),
                color=0x00ff00  # 녹색
            )
            
            # 추가 상세 정보가 있으면 필드로 추가
            details = result.get('details', {})
            for key, value in details.items():
                if value:  # 값이 있는 경우만
                    embed.add_field(
                        name=key.replace('_', ' ').title(),
                        value=str(value),
                        inline=True
                    )
            
            # 분석 정보 추가
            if result.get('analysis_confidence'):
                embed.set_footer(
                    text=f"분석 신뢰도: {result['analysis_confidence']:.0%} | 액션: {result.get('action_type', 'unknown')}"
                )
            
            await message.reply(embed=embed)
            logger.info(f"처리 성공: {result.get('action_type')}")
            
        else:
            # 실패 이모지 추가
            await message.add_reaction('❌')
            
            # 오류 메시지 전송
            error_embed = discord.Embed(
                title="❌ 처리 실패",
                description=f"**오류**: {result.get('error', '알 수 없는 오류')}\n\n",
                color=0xff0000  # 빨간색
            )
            
            # 해결방안이 있으면 추가
            if 'solution' in result:
                solutions = result['solution']
                if isinstance(solutions, list):
                    solution_text = '\n'.join(f"• {sol}" for sol in solutions)
                else:
                    solution_text = str(solutions)
                
                error_embed.add_field(
                    name="💡 해결방안",
                    value=solution_text,
                    inline=False
                )
            
            # 오류 코드가 있으면 추가
            if result.get('error_code'):
                error_embed.set_footer(text=f"오류 코드: {result['error_code']}")
            
            await message.reply(embed=error_embed)
            logger.error(f"처리 실패: {result.get('error')}")
        
    except Exception as e:
        # 예상치 못한 오류 처리
        await message.remove_reaction('🤖', bot.user)
        await message.add_reaction('💥')
        
        error_embed = discord.Embed(
            title="💥 시스템 오류",
            description=f"예상치 못한 오류가 발생했습니다: {str(e)}",
            color=0xff0000
        )
        
        await message.reply(embed=error_embed)
        logger.error(f"예상치 못한 오류: {e}")
    
    # 다른 명령어도 처리할 수 있도록
    await bot.process_commands(message)

@bot.command(name='test')
async def test_command(ctx):
    """테스트 명령어"""
    embed = discord.Embed(
        title="🧪 테스트",
        description="봇이 정상적으로 작동하고 있습니다!",
        color=0x0099ff
    )
    await ctx.send(embed=embed)

@bot.command(name='help_setup')
async def help_setup(ctx):
    """설정 도움말"""
    embed = discord.Embed(
        title="⚙️ 봇 설정 도움말",
        description="AI 어시스턴트 봇 설정 방법을 안내합니다.",
        color=0x0099ff
    )
    
    embed.add_field(
        name="📅 Google Calendar 설정",
        value="• Google Cloud Console에서 OAuth2 설정\n• credentials_oauth.json 파일 추가",
        inline=False
    )
    
    embed.add_field(
        name="📝 Notion 설정",
        value="• NOTION_API_KEY 설정\n• NOTION_DATABASE_ID 설정\n• Integration 연결",
        inline=False
    )
    
    embed.add_field(
        name="🤖 Gemini 설정",
        value="• GEMINI_API_KEY 설정",
        inline=False
    )
    
    await ctx.send(embed=embed)

# 봇 실행
if __name__ == "__main__":
    discord_token = os.getenv('DISCORD_BOT_TOKEN')
    if not discord_token:
        logger.error("DISCORD_BOT_TOKEN이 설정되지 않았습니다!")
    else:
        bot.run(discord_token)