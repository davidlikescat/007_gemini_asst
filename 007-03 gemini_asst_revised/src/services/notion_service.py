import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from notion_client import Client

from config.settings import settings
from models.task_models import MessageData, ProcessedTask, TaskResult

logger = logging.getLogger(__name__)

class NotionService:
    """Notion Task 관리 서비스"""

    def __init__(self):
        self._setup_notion()

    def _setup_notion(self):
        """Notion 클라이언트 설정"""
        if not settings.NOTION_API_KEY:
            raise ValueError("NOTION_API_KEY가 설정되지 않았습니다!")

        self.client = Client(auth=settings.NOTION_API_KEY)
        self.database_id = settings.TASK_TRACKER_DATABASE_ID
        logger.info("Notion 클라이언트 설정 완료")

    async def create_task(self, message_data: MessageData, processed_task: ProcessedTask) -> TaskResult:
        """Notion에 새 Task 생성"""
        try:
            kst = timezone(timedelta(hours=9))
            current_time = datetime.now(kst)

            # Task 페이지 데이터 준비
            task_properties = self._build_task_properties(processed_task)
            task_content = self._build_task_content(message_data, processed_task)

            new_task = {
                "parent": {"database_id": self.database_id},
                "properties": task_properties,
                "children": task_content
            }

            logger.info(f"Task 생성 시도: {processed_task.title}")
            response = self.client.pages.create(**new_task)

            task_id = response['id']
            task_url = response['url']

            logger.info(f"Task 생성 성공: {task_id}")

            success_message = (
                f"✅ **Task 생성 완료!**\n"
                f"📋 **제목**: {processed_task.title}\n"
                f"📊 **상태**: To Do\n"
                f"👤 **작성자**: {message_data.author}\n"
                f"📝 **요약**: {processed_task.summary[:50]}{'...' if len(processed_task.summary) > 50 else ''}\n"
                f"🔗 **[Task Tracker에서 보기]({task_url})**"
            )

            return TaskResult(
                success=True,
                message=success_message,
                notion_task_id=task_id,
                notion_url=task_url,
                details={
                    'title': processed_task.title,
                    'status': 'To Do',
                    'author': message_data.author,
                    'summary': processed_task.summary,
                    'category': processed_task.category,
                    'priority': processed_task.priority,
                    'tags': processed_task.tags,
                    'created_at': current_time.isoformat()
                }
            )

        except Exception as e:
            logger.error(f"Task 생성 실패: {str(e)}")
            return TaskResult(
                success=False,
                message=f"Task 생성 실패: {str(e)}",
                error=str(e)
            )

    def _build_task_properties(self, processed_task: ProcessedTask) -> dict:
        """Task 속성 데이터 구성"""
        return {
            "Projects": {
                "title": [
                    {
                        "text": {
                            "content": processed_task.title
                        }
                    }
                ]
            },
            "Status": {
                "select": {
                    "name": "To Do"
                }
            }
        }

    def _build_task_content(self, message_data: MessageData, processed_task: ProcessedTask) -> list:
        """Task 내용 블록 구성"""
        children_blocks = []

        # 원본 데이터 섹션
        children_blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📥 원본 데이터"}}]
            }
        })

        children_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": (
                                f"작성자: {message_data.author}\n"
                                f"채널: {message_data.channel}\n"
                                f"시간: {message_data.timestamp.isoformat()}\n\n"
                                f"원본 메시지:\n{message_data.content}"
                            )
                        }
                    }
                ]
            }
        })

        # AI 분석 결과 섹션
        children_blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "🤖 AI 분석 결과"}}]
            }
        })

        analysis_text = (
            f"카테고리: {processed_task.category}\n"
            f"우선순위: {processed_task.priority}\n"
            f"요약: {processed_task.summary}\n"
            f"태그: {', '.join(processed_task.tags) if processed_task.tags else 'N/A'}\n"
            f"후속 작업 필요: {'예' if processed_task.action_required else '아니오'}\n"
        )

        if processed_task.notes:
            analysis_text += f"\n추가 메모: {processed_task.notes}"

        children_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": analysis_text
                        }
                    }
                ]
            }
        })

        return children_blocks