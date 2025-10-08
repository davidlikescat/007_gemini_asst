import logging
import os
from typing import Dict, Any

from notion_client import Client

from ..agents.base_agent import BaseAgent
from ..state.models import WorkflowState, ExecutionResult, TaskStatus


logger = logging.getLogger(__name__)


class NotionAgent(BaseAgent):
    """Discord 입력을 Notion 데이터베이스에 메모로 저장하는 에이전트"""

    def __init__(self):
        super().__init__("notion_agent")
        self.client = Client(auth=os.getenv("NOTION_API_KEY"))
        self.database_id = os.getenv("NOTION_DATABASE_ID")
        self.properties_schema: Dict[str, Dict[str, Any]] = {}
        self.title_property = "Title"
        self.status_property = None
        self.priority_property = None
        self.channel_property = None
        self._load_property_schema()

    def _load_property_schema(self):
        try:
            if not self.database_id:
                logger.warning("NOTION_DATABASE_ID가 설정되지 않았습니다.")
                return
            database = self.client.databases.retrieve(self.database_id)
            self.properties_schema = database.get("properties", {})

            # 제목 필드(auto-detect)
            for name, meta in self.properties_schema.items():
                if meta.get("type") == "title":
                    self.title_property = name
                    break

            # 상태/우선순위/채널 필드도 자동 감지
            for name, meta in self.properties_schema.items():
                prop_type = meta.get("type")
                lower_name = name.lower()
                if prop_type == "select" and lower_name.startswith("status"):
                    self.status_property = name
                if prop_type == "select" and "priority" in lower_name:
                    self.priority_property = name
                if "channel" in lower_name:
                    self.channel_property = name

            logger.info(
                "Notion DB 속성 로딩: title=%s status=%s priority=%s channel=%s",
                self.title_property,
                self.status_property,
                self.priority_property,
                self.channel_property,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Notion DB 속성 조회 실패: %s", exc)
            self.properties_schema = {}

    async def execute(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        try:
            action = task_params.get("action", "create_task")

            if action == "create_task":
                result = await self._create_task(task_params)
            elif action == "create_page":
                result = await self._create_page(task_params)
            elif action == "update_task":
                result = await self._update_task(task_params)
            else:
                raise ValueError(f"Unknown action: {action}")

            return ExecutionResult(
                task_id=task_params.get("task_id", "notion_task"),
                status=TaskStatus.COMPLETED,
                result=result
            )

        except Exception as e:
            return ExecutionResult(
                task_id=task_params.get("task_id", "notion_task"),
                status=TaskStatus.FAILED,
                error=str(e)
            )

    async def _create_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        title = params.get("title", "새 메모")
        description = params.get("description", "")
        status = params.get("status", "To Do")
        priority = params.get("priority", "Medium")
        channel_name = params.get("channel", "")

        properties = {
            self.title_property: {"title": [{"text": {"content": title}}]}
        }

        if status and self.status_property:
            properties[self.status_property] = {"select": {"name": status}}

        if self.priority_property and priority:
            properties[self.priority_property] = {"select": {"name": priority}}

        if self.channel_property and channel_name:
            channel_meta = self.properties_schema.get(self.channel_property, {})
            prop_type = channel_meta.get("type")
            if prop_type == "rich_text":
                properties[self.channel_property] = {
                    "rich_text": [{"text": {"content": channel_name}}]
                }
            elif prop_type == "title":
                properties[self.channel_property] = {
                    "title": [{"text": {"content": channel_name}}]
                }
            elif prop_type == "select":
                properties[self.channel_property] = {"select": {"name": channel_name}}
            elif prop_type == "multi_select":
                properties[self.channel_property] = {
                    "multi_select": [{"name": channel_name}]
                }

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
        }

        children = params.get("children")
        if children:
            payload["children"] = children

        response = self.client.pages.create(**payload)

        return {
            "page_id": response["id"],
            "url": response["url"],
            "title": title,
            "status": status
        }

    async def _update_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        page_id = params.get("page_id")
        if not page_id:
            raise ValueError("page_id is required for update")

        properties = {}

        if "status" in params and self.status_property:
            properties[self.status_property] = {"select": {"name": params["status"]}}

        if "title" in params:
            properties[self.title_property] = {
                "title": [{"text": {"content": params["title"]}}]
            }

        response = self.client.pages.update(
            page_id=page_id,
            properties=properties
        )

        return {
            "page_id": response["id"],
            "updated": True
        }

    async def _create_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        title = params.get("title", "새 페이지")
        content = params.get("content", "")

        children = []
        if content:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            })

        response = self.client.pages.create(
            parent={"database_id": self.database_id},
            properties={
                self.title_property: {"title": [{"text": {"content": title}}]}
            },
            children=children
        )

        return {
            "page_id": response["id"],
            "url": response["url"],
            "title": title
        }
