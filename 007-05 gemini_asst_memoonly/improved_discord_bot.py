#!/usr/bin/env python3
"""
간소화된 Discord → Notion 메모 봇
- Discord 메시지를 받아 Notion에 원문 + Gemini 정제본을 저장
- LangChain을 활용해 Gemini가 메시지를 정리한 결과를 함께 제공
"""
import asyncio
import logging
import os
import sys
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

# 패키지 경로 추가
CURRENT_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(CURRENT_DIR, "langgraph_agents"))

# 환경 변수 로드 (.env 위치는 langgraph_agents/.env 로 통일)
env_path = os.path.join(CURRENT_DIR, "langgraph_agents", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
else:
    logger.warning("환경 변수 파일을 찾을 수 없습니다: %s", env_path)

from langgraph_agents.agents import agent_executor  # noqa: E402
from langgraph_agents.services import MemoRefiner, NotionAgent  # noqa: E402
from langgraph_agents.state import state_manager, TaskStatus  # noqa: E402

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("memo_discord_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

logger.info("📝 Discord → Notion 메모 봇 시작")

# Discord 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 채널 필터
TARGET_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
BLOCKED_CHANNEL_ID = int(os.getenv("BLOCKED_CHANNEL_ID", "1425020218182467665"))

# 에이전트 등록 여부 플래그
_notion_agent_registered = False
memo_refiner: Optional[MemoRefiner] = None


async def ensure_notion_registered():
    """Notion 에이전트가 한 번만 등록되도록 보장"""
    global _notion_agent_registered
    if not _notion_agent_registered:
        agent_executor.register_agent(NotionAgent())
        _notion_agent_registered = True
        logger.info("📝 NotionAgent 등록 완료")


def truncate(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cutoff = max(limit - 3, 0)
    return text[:cutoff] + "..."


def _heading_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": text},
                }
            ]
        },
    }


def _paragraph_block(text: str, link: Optional[str] = None) -> dict:
    rich_text = {
        "type": "text",
        "text": {"content": text},
    }
    if link:
        rich_text["text"]["link"] = {"url": link}

    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [rich_text],
        },
    }


def _chunk_text(text: str, chunk_size: int = 1800) -> list:
    """Notion 블록 길이를 초과하지 않도록 텍스트를 분할"""
    chunks = []
    text = text or ""
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i : i + chunk_size])
    return chunks or [""]


def build_task_params(
    message: discord.Message,
    original_text: str,
    analysis: dict,
) -> Optional[dict]:
    original = (original_text or "").strip()
    refined = (analysis.get("refined_summary") or "").strip()

    if not original and not refined:
        return None

    title_source = refined or original
    first_line = title_source.splitlines()[0].strip() if title_source else ""
    title = first_line[:100] if first_line else "새 메모"

    category = analysis.get("category") or "미분류"
    priority = analysis.get("priority") or os.getenv("NOTION_DEFAULT_PRIORITY", "Medium")
    tags = analysis.get("tags") or []
    action_required = analysis.get("action_required", False)
    notes = analysis.get("notes") or ""

    description_parts = [
        "[Discord 메시지]",
        message.jump_url or "(링크 없음)",
        "",
        f"요약: {refined or '(생성되지 않음)'}",
        f"카테고리: {category}",
        f"우선순위: {priority}",
        f"태그: {', '.join(tags) if tags else '없음'}",
        f"후속 작업 필요: {'예' if action_required else '아니오'}",
    ]
    if notes:
        description_parts.append(f"추가 메모: {notes}")
    description_parts.extend(
        [
            "",
            "원문:",
            original or "(내용 없음)",
        ]
    )
    description = "\n".join(description_parts)

    children = []
    if message.jump_url:
        children.append(_paragraph_block("🔗 Discord 메시지 링크", link=message.jump_url))

    children.append(_heading_block("🤖 AI 분석 결과"))
    analysis_lines = [
        f"카테고리: {category}",
        f"우선순위: {priority}",
        f"요약: {refined or '(생성되지 않음)'}",
        f"태그: {', '.join(tags) if tags else '없음'}",
        f"후속 작업 필요: {'예' if action_required else '아니오'}",
    ]
    if notes:
        analysis_lines.append(f"추가 메모: {notes}")
    analysis_text = "\n".join(analysis_lines)
    for chunk in _chunk_text(analysis_text):
        children.append(_paragraph_block(chunk))

    if refined:
        children.append(_heading_block("📝 정제본"))
        for chunk in _chunk_text(refined):
            children.append(_paragraph_block(chunk))

    if original:
        children.append(_heading_block("📥 원문"))
        for chunk in _chunk_text(original):
            children.append(_paragraph_block(chunk))

    return {
        "task_id": f"memo_{message.id}",
        "action": "create_task",
        "title": title,
        "description": description,
        "status": os.getenv("NOTION_DEFAULT_STATUS", "To Do"),
        "priority": priority,
        "channel": message.channel.name,
        "children": children,
    }


@bot.event
async def on_ready():
    global memo_refiner

    logger.info(f"✅ 봇 로그인: {bot.user}")
    logger.info(f"🎯 타겟 채널: {TARGET_CHANNEL_ID or '전체 허용'}")
    logger.info(f"🚫 차단 채널: {BLOCKED_CHANNEL_ID}")

    for guild in bot.guilds:
        logger.info(f"📋 서버: {guild.name} (ID: {guild.id})")
        for channel in guild.text_channels:
            logger.info(f"   📢 #{channel.name} (ID: {channel.id})")

    await state_manager.start()
    await ensure_notion_registered()

    try:
        memo_refiner = MemoRefiner()
        logger.info("✨ MemoRefiner 초기화 완료")
    except Exception as exc:  # pylint: disable=broad-except
        memo_refiner = None
        logger.error("❌ MemoRefiner 초기화 실패: %s", exc)


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if message.channel.id == BLOCKED_CHANNEL_ID:
        logger.info("🚫 차단된 채널에서 수신된 메시지, 무시합니다.")
        return

    if TARGET_CHANNEL_ID and message.channel.id != TARGET_CHANNEL_ID:
        return

    logger.info("🔍 메시지 수신: %s | %s: %s", message.id, message.author, message.content)

    if memo_refiner is None:
        await message.reply("❌ Gemini API 설정이 없어 메모 정제를 진행할 수 없습니다.")
        return

    original_text = message.content.strip()

    try:
        analysis = await memo_refiner.analyze(message.content)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Gemini 분석 실패")
        analysis = MemoRefiner._fallback(original=original_text)  # type: ignore[attr-defined]

    analysis_success = analysis.get("analysis_success", True)
    refined_text = analysis.get("refined_summary", original_text)

    logger.info(
        "🧾 분석 결과 summary=%s | category=%s | priority=%s | action_required=%s | tags=%s | notes=%s | success=%s",
        truncate(refined_text, 120),
        analysis.get("category"),
        analysis.get("priority"),
        analysis.get("action_required"),
        ", ".join(analysis.get("tags", [])) if analysis.get("tags") else "",
        analysis.get("notes"),
        analysis_success,
    )

    params = build_task_params(message, original_text, analysis)
    if not params:
        await message.reply("❌ 메모로 저장할 텍스트를 찾을 수 없습니다.")
        return

    session_id = await state_manager.create_session(
        user_input=message.content,
        original_message=str(message.author),
    )
    state = await state_manager.get_session(session_id)
    assert state is not None

    status_message = await message.reply("📝 노션에 메모를 저장합니다...")

    try:
        await ensure_notion_registered()

        result = await agent_executor.execute_agent("notion_agent", state, params)
        await state_manager.add_execution_result(session_id, params["task_id"], result)

        if result.status == TaskStatus.COMPLETED:
            notion_url = result.result.get("url") if result.result else None
            lines = ["✅ 노션 메모 저장 완료!"]
            if notion_url:
                lines.append(f"🔗 {notion_url}")
            lines.append(f"카테고리: {analysis.get('category', '미분류')} | 우선순위: {analysis.get('priority', 'Medium')}")
            if analysis.get("tags"):
                lines.append(f"태그: {', '.join(analysis['tags'])}")
            if not analysis_success:
                lines.append("⚠️ Gemini 분석에 실패하여 기본값을 사용했습니다.")
            elif analysis.get("notes"):
                lines.append(f"메모: {analysis['notes']}")
            lines.append("")
            lines.append("**요약**")
            lines.append(truncate(refined_text))
            lines.append("")
            lines.append("**원문**")
            lines.append(truncate(original_text))

            await status_message.edit(content="\n".join(lines))
        else:
            await status_message.edit(content=f"❌ 노션 저장 실패: {result.error}")

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("노션 메모 저장 중 오류 발생")
        await status_message.edit(content=f"❌ 처리 중 오류가 발생했습니다: {exc}")
    finally:
        await state_manager.close_session(session_id)


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN 환경 변수가 필요합니다.")
        return

    try:
        logger.info("🚀 Discord 봇 실행")
        await bot.start(token)
    finally:
        await state_manager.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 봇 종료")
