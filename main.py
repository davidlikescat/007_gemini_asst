#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import asyncio
from sub import ActionProcessor
import logging
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 처리된 메시지 ID들을 저장하는 전역 변수 (추가!)
processed_messages = set()

# Discord 인텐트 설정 (메시지 내용 읽기 권한 포함)
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True

# Discord 봇 설정
bot = commands.Bot(command_prefix='!', intents=intents)

# ActionProcessor 인스턴스 생성
processor = ActionProcessor()

@bot.event
async def on_ready():
    logger.info(f'🤖 {bot.user}가 로그인되었습니다!')
    logger.info(f'🔗 연결된 서버: {len(bot.guilds)}개')
    
    # 서버와 채널 정보 출력
    for guild in bot.guilds:
        logger.info(f'📍 서버: {guild.name} (ID: {guild.id})')
        for channel in guild.text_channels[:5]:  # 처음 5개 채널만
            logger.info(f'   💬 채널: #{channel.name} (ID: {channel.id})')

@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 무시
    if message.author == bot.user:
        return
    
    # 특정 채널에서의 모든 메시지를 처리
    target_channel_id = os.getenv('DISCORD_CHANNEL_ID')
    if target_channel_id and str(message.channel.id) != target_channel_id:
        return
    
    try:
        # 이미 처리된 메시지는 건너뛰기 (수정됨!)
        if message.id in processed_messages:
            return
            
        # 메시지 처리 시작 로깅
        logger.info(f"📨 메시지 수신: {message.content[:50]}... by {message.author.name}")
        logger.info(f"   💬 채널: #{message.channel.name} (ID: {message.channel.id})")
        
        # 처리된 메시지로 표시 (수정됨!)
        processed_messages.add(message.id)
        
        # 진행 중 이모지 추가
        await message.add_reaction('🤖')
        
        # ActionProcessor로 메시지 처리
        result = await processor.process_message(message)
        
        # 진행 중 이모지 제거
        await message.remove_reaction('🤖', bot.user)
            
        if result.get('success'):
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
                        value=str(value)[:1024],  # Discord 필드 길이 제한
                        inline=True
                    )
            
            # 분석 정보 추가
            if result.get('confidence'):
                embed.set_footer(
                    text=f"분석 신뢰도: {result['confidence']:.0%} | 액션: {result.get('action_type', 'unknown')}"
                )
            
            await message.reply(embed=embed)
            logger.info(f"✅ 처리 성공: {result.get('action_type')}")
            
        else:
            # 실패 이모지 추가
            await message.add_reaction('❌')
            
            # 오류 메시지 전송
            error_embed = discord.Embed(
                title="❌ 처리 실패",
                description=f"**오류**: {result.get('error', '알 수 없는 오류')}",
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
                    value=solution_text[:1024],
                    inline=False
                )
            
            # 오류 코드가 있으면 추가
            if result.get('error_code'):
                error_embed.set_footer(text=f"오류 코드: {result['error_code']}")
            
            await message.reply(embed=error_embed)
            logger.error(f"❌ 처리 실패: {result.get('error')}")
        
    except Exception as e:
        # 예상치 못한 오류 처리
        try:
            await message.remove_reaction('🤖', bot.user)
            await message.add_reaction('💥')
            
            error_embed = discord.Embed(
                title="💥 시스템 오류",
                description=f"예상치 못한 오류가 발생했습니다: {str(e)[:500]}",
                color=0xff0000
            )
            
            await message.reply(embed=error_embed)
        except:
            pass  # 에러 메시지 전송도 실패하면 조용히 넘어감
            
        logger.error(f"💥 예상치 못한 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
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
    
    # 현재 설정 정보 추가
    embed.add_field(
        name="🔧 설정 정보",
        value=f"채널 ID: {os.getenv('DISCORD_CHANNEL_ID', '설정 안됨')}\n"
              f"Gemini API: {'✅' if os.getenv('GEMINI_API_KEY') else '❌'}\n"
              f"Notion API: {'✅' if os.getenv('NOTION_API_KEY') else '❌'}",
        inline=False
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
        value="• Google Cloud Console에서 OAuth2 설정\n• credentials.json 파일 추가\n• google_token.pickle 생성",
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
    
    embed.add_field(
        name="📧 이메일 설정",
        value="• EMAIL_ADDRESS 설정\n• EMAIL_PASSWORD (앱 비밀번호) 설정",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command(name='debug_calendar')
async def debug_calendar(ctx):
    """Google Calendar 연결 상태 디버깅"""
    embed = discord.Embed(title="🔍 Google Calendar 디버깅", color=0xff9900)
    
    try:
        # 1. 서비스 설정 확인
        if hasattr(processor, 'calendar_service') and processor.calendar_service:
            embed.add_field(
                name="✅ Calendar 서비스",
                value="서비스 객체가 존재합니다",
                inline=False
            )
            
            # 2. 캘린더 목록 조회 테스트
            try:
                calendars = processor.calendar_service.calendarList().list().execute()
                calendar_items = calendars.get('items', [])
                
                if calendar_items:
                    calendar_info = []
                    for cal in calendar_items[:3]:  # 처음 3개만 표시
                        cal_id = cal.get('id', 'Unknown')
                        cal_summary = cal.get('summary', 'Unknown')
                        cal_access = cal.get('accessRole', 'Unknown')
                        calendar_info.append(f"• {cal_summary}\n  권한: {cal_access}")
                    
                    embed.add_field(
                        name="📅 접근 가능한 캘린더",
                        value="\n\n".join(calendar_info),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="❌ 캘린더 목록",
                        value="접근 가능한 캘린더가 없습니다",
                        inline=False
                    )
                    
            except Exception as e:
                embed.add_field(
                    name="❌ 캘린더 목록 조회 실패",
                    value=f"오류: {str(e)[:200]}...",
                    inline=False
                )
                
        else:
            embed.add_field(
                name="❌ Calendar 서비스",
                value="서비스가 초기화되지 않았습니다",
                inline=False
            )
            
    except Exception as e:
        embed.add_field(
            name="💥 디버깅 중 오류",
            value=f"오류: {str(e)[:200]}...",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='test_event')
async def test_calendar_event(ctx):
    """테스트 이벤트 생성"""
    embed = discord.Embed(title="🧪 테스트 이벤트 생성", color=0x0099ff)
    
    try:
        if not hasattr(processor, 'calendar_service') or not processor.calendar_service:
            embed.add_field(
                name="❌ 실패",
                value="Calendar 서비스가 설정되지 않았습니다",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # 테스트 이벤트 데이터
        now = datetime.now()
        start_time = (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')
        end_time = (now + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S')
        
        test_event = {
            'summary': '🧪 Discord 봇 테스트 이벤트',
            'description': f'Discord 봇에서 생성한 테스트 이벤트입니다.\n생성자: {ctx.author.name}',
            'start': {
                'dateTime': start_time,
                'timeZone': 'Asia/Seoul',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Asia/Seoul',
            },
        }
        
        # 이벤트 생성 시도
        created_event = processor.calendar_service.events().insert(
            calendarId='primary',
            body=test_event
        ).execute()
        
        # 이벤트 ID 및 URL 생성
        event_id = created_event.get('id', 'Unknown')
        event_url = f"https://calendar.google.com/calendar/u/0/event?eid={event_id}"
        
        embed.add_field(
            name="✅ 성공",
            value=f"**제목**: {test_event['summary']}\n**시작**: {start_time}\n**이벤트 ID**: {event_id[:20]}...\n**링크**: [Google Calendar에서 보기]({event_url})",
            inline=False
        )
        
        logger.info(f"✅ 테스트 이벤트 생성 성공: {event_id}")
        
    except Exception as e:
        embed.add_field(
            name="❌ 실패",
            value=f"오류: {str(e)[:300]}...",
            inline=False
        )
        logger.error(f"❌ 테스트 이벤트 생성 실패: {e}")
    
    await ctx.send(embed=embed)

@bot.command(name='list_events')
async def list_recent_events(ctx):
    """최근 이벤트 목록 조회"""
    embed = discord.Embed(title="📋 최근 이벤트 목록", color=0x00ff99)
    
    try:
        if not hasattr(processor, 'calendar_service') or not processor.calendar_service:
            embed.add_field(
                name="❌ 실패",
                value="Calendar 서비스가 설정되지 않았습니다",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # 최근 이벤트 조회
        now = datetime.now()
        time_min = (now - timedelta(days=1)).isoformat() + 'Z'
        time_max = (now + timedelta(days=7)).isoformat() + 'Z'
        
        events_result = processor.calendar_service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if events:
            event_info = []
            for event in events:
                summary = event.get('summary', '제목 없음')
                start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'Unknown'))
                if 'T' in start:
                    start = start[:16].replace('T', ' ')
                event_info.append(f"• **{summary}**\n  📅 {start}")
            
            embed.add_field(
                name="📅 다가오는 이벤트",
                value="\n\n".join(event_info),
                inline=False
            )
        else:
            embed.add_field(
                name="📅 이벤트 목록",
                value="다가오는 이벤트가 없습니다",
                inline=False
            )
            
    except Exception as e:
        embed.add_field(
            name="❌ 이벤트 목록 조회 실패",
            value=f"오류: {str(e)[:200]}...",
            inline=False
        )
    
    await ctx.send(embed=embed)

# 봇 실행
def main():
    discord_token = os.getenv('DISCORD_BOT_TOKEN')
    if not discord_token:
        logger.error("❌ DISCORD_BOT_TOKEN이 설정되지 않았습니다!")
        return
    
    logger.info("🚀 Discord 봇 시작...")
    logger.info(f"🎯 대상 채널 ID: {os.getenv('DISCORD_CHANNEL_ID', '설정 안됨')}")
    
    try:
        bot.run(discord_token)
    except Exception as e:
        logger.error(f"❌ 봇 실행 실패: {e}")

if __name__ == "__main__":
    main()
