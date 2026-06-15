import os
from dataclasses import dataclass

from learn_agent.config.settings import settings

CWD = os.getcwd()

# ── System prompts ──────────────────────────────────────────

PARENT_SYSTEM_PROMPT = (
    f"You are a coding agent at {CWD}. "
    "Use tools to solve tasks. Act, don't explain. "
    "For complex multi-step tasks, use create_plan first, then work through each step "
    "by updating plan statuses with update_plan_status. "
    "Always mark the current step 'done' BEFORE starting the next one. "
    "Only ONE plan item can be 'doing' at a time. "
    "For focused read-only investigation tasks, use delegate_task. "
    "Delegate only tasks that can be isolated and do not require writing files. "
    "When delegating, summarize all necessary context explicitly in the task input. "
    "Do not assume the subagent can see the parent conversation history. "
    "You remain responsible for final edits, command execution, and user-facing conclusions. "
    "If a tool fails, avoid repeating the exact same failed call; try another approach."
)

SUBAGENT_SYSTEM_PROMPT = (
    "You are a read-only research subagent. "
    "You can only inspect the workspace using allowed tools. "
    "Do not modify files. "
    "Do not call other agents. "
    "Do not attempt write/edit/bash operations. "
    "Return a concise evidence-based summary to the parent agent. "
    "Include file paths and key findings. "
    "If a tool fails, try a different read-only approach. "
    "Stop when the answer is sufficient."
)


@dataclass(frozen=True)
class AgentConfig:
    name: str
    role: str  # "parent" | "subagent"
    max_turns: int
    max_failures: int
    allowed_tool_names: frozenset[str]
    can_delegate: bool = False
    system_prompt: str = ""


# ── Pre-built configs ───────────────────────────────────────

PARENT_AGENT_CONFIG = AgentConfig(
    name="parent",
    role="parent",
    max_turns=settings.PARENT_MAX_TURNS,
    max_failures=settings.PARENT_MAX_FAILURES,
    allowed_tool_names=frozenset({
        "bash",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "create_plan",
        "update_plan_status",
        "delegate_task",
        "load_skill",
    }),
    can_delegate=True,
    system_prompt=PARENT_SYSTEM_PROMPT,
)

SUBAGENT_CONFIG = AgentConfig(
    name="subagent",
    role="subagent",
    max_turns=settings.SUBAGENT_MAX_TURNS,
    max_failures=settings.SUBAGENT_MAX_FAILURES,
    allowed_tool_names=frozenset({"glob", "read_file"}),
    can_delegate=False,
    system_prompt=SUBAGENT_SYSTEM_PROMPT,
)
