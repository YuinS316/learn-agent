from learn_agent.tools.run_bash import run_bash
from learn_agent.tools.run_read import run_read
from learn_agent.tools.run_write import run_write
from learn_agent.tools.run_edit import run_edit
from learn_agent.tools.run_glob import run_glob
from learn_agent.tools.run_create_plan import run_create_plan
from learn_agent.tools.run_update_plan_status import run_update_plan_status
from learn_agent.tools.run_delegate_task import run_delegate_task
from learn_agent.tools.run_load_skill import run_load_skill

# ── Tool definitions (Anthropic format) ────────────────────────
TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the workspace. Returns the file contents as text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read (relative to workspace root)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional max number of lines to return",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write (relative to workspace root)",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace the first occurrence of old_text with new_text in a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit (relative to workspace root)",
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace",
                },
                "new_text": {
                    "type": "string",
                    "description": "The replacement text",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "glob",
        "description": "Find files matching a glob pattern in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern, e.g. 'src/**/*.py' or '*.md'",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "create_plan",
        "description": (
            "Create a structured execution plan before starting complex multi-step tasks. "
            "Use this when a task requires more than 1-2 steps. "
            "Do NOT use for simple tasks like 'what files are in src'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The overall goal of the plan, in one sentence",
                },
                "plans": {
                    "type": "array",
                    "description": "Ordered list of plan items. Maximum 10 items.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Short name of this step",
                            },
                            "description": {
                                "type": "string",
                                "description": "Detailed description of what to do in this step",
                            },
                        },
                        "required": ["content", "description"],
                    },
                },
            },
            "required": ["goal", "plans"],
        },
    },
    {
        "name": "update_plan_status",
        "description": (
            "Update the status of a plan item. "
            "Only ONE plan can be 'doing' at a time. "
            "Always mark the current step 'done' before starting the next one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_index": {
                    "type": "integer",
                    "description": "Index of the plan item to update (0-based)",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "doing", "done"],
                    "description": "New status: 'done' when finished, 'doing' to start the next step",
                },
            },
            "required": ["plan_index", "status"],
        },
    },
    {
        "name": "delegate_task",
        "description": (
            "Delegate a read-only information-gathering task to a restricted subagent. "
            "Use this for focused investigation tasks that can be isolated. "
            "The subagent can only read files and glob — it cannot write, edit, execute "
            "commands, or delegate further. "
            "Summarize all necessary context in the task input; the subagent cannot see "
            "the parent conversation history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The specific information-gathering task for the subagent",
                },
                "context": {
                    "type": "string",
                    "description": "Minimal relevant context summarized by the parent. "
                                   "Do not pass full conversation history.",
                },
                "relevant_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional paths or glob hints the subagent should inspect first",
                },
                "output_format": {
                    "type": "string",
                    "description": "Expected output format, e.g. bullet summary, file list, "
                                   "findings with evidence",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "load_skill",
        "description": (
            "Load a skill's full documentation. Skills provide domain-specific "
            "guidance for tasks like debugging, testing, using git worktrees, etc. "
            "Use this when the task matches a skill's description — the skill will "
            "give you a step-by-step process to follow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the skill to load",
                },
            },
            "required": ["name"],
        },
    },
]

# ── Tool filtering ────────────────────────────────────────────

def filter_tools(allowed: frozenset[str]) -> list[dict]:
    """Return tool definitions for only the allowed tool names."""
    return [t for t in TOOLS if t["name"] in allowed]


# ── Tool name → handler function ──────────────────────────────
# State-modifying tools: create_plan, update_plan_status, delegate_task, load_skill
# These handlers receive (state, **tool_input) instead of (**tool_input)
STATE_TOOLS = {"create_plan", "update_plan_status", "delegate_task", "load_skill"}

TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
    "create_plan": run_create_plan,
    "update_plan_status": run_update_plan_status,
    "delegate_task": run_delegate_task,
    "load_skill": run_load_skill,
}
