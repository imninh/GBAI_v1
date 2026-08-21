import uuid
from typing import Literal, TypedDict

from langchain.agents import AgentState as BaseAgentState
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command


class Todo(TypedDict):
    id: str
    title: str
    description: str
    emoji: str
    status: Literal["pending", "completed"]


class AgentState(BaseAgentState):
    todos: list[Todo]


@tool
def manage_todos(todos: list[Todo], runtime: ToolRuntime) -> Command:
    """
    Manage the current todos.
    """
    # Ensure all todos have IDs that are unique
    for todo in todos:
        if "id" not in todo or not todo["id"]:
            todo["id"] = str(uuid.uuid4())

    # Update the state
    return Command(
        update={
            "todos": todos,
            "messages": [
                ToolMessage(
                    content="Successfully updated todos",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool
def get_todos(runtime: ToolRuntime):
    """
    Get the current todos.
    """
    return runtime.state.get("todos", [])


todo_tools = [
    manage_todos,
    get_todos,
]
