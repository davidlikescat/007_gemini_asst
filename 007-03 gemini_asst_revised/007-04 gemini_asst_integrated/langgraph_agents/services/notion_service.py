import os
from typing import Dict, Any, Optional
from notion_client import Client
from ..agents.base_agent import BaseAgent
from ..state.models import WorkflowState, ExecutionResult, TaskStatus

class NotionAgent(BaseAgent):
    def __init__(self):
        super().__init__("notion_agent")
        self.client = Client(auth=os.getenv("NOTION_API_KEY"))
        self.database_id = os.getenv("NOTION_DATABASE_ID")

    async def execute(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        try:
            action = task_params.get("action", "create_task")

            if action == "create_task":
                result = await self._create_task(task_params)
            elif action == "update_task":
                result = await self._update_task(task_params)
            elif action == "create_page":
                result = await self._create_page(task_params)
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
        title = params.get("title", "새 작업")
        description = params.get("description", "")
        status = params.get("status", "To Do")
        priority = params.get("priority", "Medium")

        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Status": {"select": {"name": status}},
            "Priority": {"select": {"name": priority}},
        }

        if description:
            properties["Description"] = {
                "rich_text": [{"text": {"content": description}}]
            }

        response = self.client.pages.create(
            parent={"database_id": self.database_id},
            properties=properties
        )

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

        if "status" in params:
            properties["Status"] = {"select": {"name": params["status"]}}

        if "title" in params:
            properties["Name"] = {
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
                "Name": {"title": [{"text": {"content": title}}]}
            },
            children=children
        )

        return {
            "page_id": response["id"],
            "url": response["url"],
            "title": title
        }