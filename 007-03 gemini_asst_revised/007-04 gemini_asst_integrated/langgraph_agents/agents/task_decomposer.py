from typing import Dict, Any, List, Tuple
from .base_agent import BaseAgent
from ..state.models import WorkflowState, ExecutionResult, TaskStatus, TaskIntent, Priority

class TaskDecomposerAgent(BaseAgent):
    def __init__(self):
        super().__init__("task_decomposer")

    async def execute(self, state: WorkflowState, task_params: Dict[str, Any]) -> ExecutionResult:
        try:
            # 의존성 그래프 생성
            dependency_graph = self._build_dependency_graph(state.intents)

            # 실행 순서 결정
            execution_plan = self._create_execution_plan(dependency_graph, state.intents)

            # 병렬 실행 그룹 생성
            parallel_groups = self._create_parallel_groups(execution_plan)

            return ExecutionResult(
                task_id=task_params.get("task_id", "task_decomposition"),
                status=TaskStatus.COMPLETED,
                result={
                    "dependency_graph": dependency_graph,
                    "execution_plan": execution_plan,
                    "parallel_groups": parallel_groups,
                    "total_groups": len(parallel_groups)
                }
            )

        except Exception as e:
            return ExecutionResult(
                task_id=task_params.get("task_id", "task_decomposition"),
                status=TaskStatus.FAILED,
                error=str(e)
            )

    def _build_dependency_graph(self, intents: List[TaskIntent]) -> Dict[str, List[str]]:
        graph = {}

        for intent in intents:
            task_id = intent.parameters.get("task_id")
            if task_id:
                graph[task_id] = intent.dependencies.copy()

        # 순환 의존성 검사
        if self._has_circular_dependency(graph):
            self.logger.warning("Circular dependency detected, removing problematic edges")
            graph = self._resolve_circular_dependency(graph)

        return graph

    def _has_circular_dependency(self, graph: Dict[str, List[str]]) -> bool:
        def dfs(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        visited = set()
        for node in graph:
            if node not in visited:
                if dfs(node, visited, set()):
                    return True
        return False

    def _resolve_circular_dependency(self, graph: Dict[str, List[str]]) -> Dict[str, List[str]]:
        resolved_graph = {}
        for task_id, deps in graph.items():
            resolved_graph[task_id] = [dep for dep in deps if dep in graph]
        return resolved_graph

    def _create_execution_plan(self, dependency_graph: Dict[str, List[str]],
                              intents: List[TaskIntent]) -> List[str]:
        in_degree = {task_id: 0 for task_id in dependency_graph}

        # 진입 차수 계산
        for task_id, dependencies in dependency_graph.items():
            for dep in dependencies:
                if dep in in_degree:
                    in_degree[task_id] += 1

        # 우선순위별 정렬
        intent_map = {intent.parameters.get("task_id"): intent for intent in intents}

        # 위상 정렬 + 우선순위 고려
        queue = []
        execution_order = []

        # 진입 차수가 0인 노드들을 우선순위 순으로 정렬
        for task_id, degree in in_degree.items():
            if degree == 0:
                priority_value = self._get_priority_value(intent_map.get(task_id))
                queue.append((priority_value, task_id))

        queue.sort()  # 우선순위 순 정렬

        while queue:
            _, current_task = queue.pop(0)
            execution_order.append(current_task)

            # 현재 작업에 의존하는 작업들의 진입 차수 감소
            for task_id, dependencies in dependency_graph.items():
                if current_task in dependencies:
                    in_degree[task_id] -= 1
                    if in_degree[task_id] == 0:
                        priority_value = self._get_priority_value(intent_map.get(task_id))
                        queue.append((priority_value, task_id))
                        queue.sort()

        return execution_order

    def _get_priority_value(self, intent: TaskIntent) -> int:
        if not intent:
            return 2
        priority_map = {
            Priority.URGENT: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3
        }
        return priority_map.get(intent.priority, 2)

    def _create_parallel_groups(self, execution_plan: List[str]) -> List[List[Dict[str, Any]]]:
        groups = []
        current_group = []

        for task_id in execution_plan:
            # 의존성이 없거나 이미 처리된 경우 현재 그룹에 추가
            can_run_parallel = True

            # 현재 그룹의 다른 작업들과 병렬 실행 가능한지 확인
            for existing_task in current_group:
                if self._has_conflict(task_id, existing_task["task_id"]):
                    can_run_parallel = False
                    break

            if can_run_parallel and len(current_group) < 3:  # 최대 3개씩 병렬 실행
                current_group.append({
                    "task_id": task_id,
                    "agent": self._get_agent_name(task_id)
                })
            else:
                # 현재 그룹을 완료하고 새 그룹 시작
                if current_group:
                    groups.append(current_group)
                current_group = [{
                    "task_id": task_id,
                    "agent": self._get_agent_name(task_id)
                }]

        # 마지막 그룹 추가
        if current_group:
            groups.append(current_group)

        return groups

    def _has_conflict(self, task1_id: str, task2_id: str) -> bool:
        # 동일한 서비스를 사용하는 작업들은 순차 실행
        task1_service = task1_id.split("_")[0]
        task2_service = task2_id.split("_")[0]

        # Gmail과 Calendar는 동시에 실행해도 안전
        safe_combinations = [
            {"gmail", "calendar"},
            {"notion", "discord"},
            {"gmail", "discord"}
        ]

        service_pair = {task1_service, task2_service}
        return service_pair not in safe_combinations and task1_service == task2_service

    def _get_agent_name(self, task_id: str) -> str:
        service = task_id.split("_")[0]
        agent_map = {
            "notion": "notion_agent",
            "calendar": "calendar_agent",
            "gmail": "gmail_agent",
            "discord": "discord_agent"
        }
        return agent_map.get(service, "unknown_agent")

    async def validate_params(self, params: Dict[str, Any]) -> bool:
        return True