from learn_agent.tools.run_bash import run_bash
from learn_agent.tools.run_read import run_read
from learn_agent.tools.run_write import run_write
from learn_agent.tools.run_edit import run_edit
from learn_agent.tools.run_glob import run_glob
from learn_agent.tools.run_create_plan import run_create_plan
from learn_agent.tools.run_update_plan_status import run_update_plan_status

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
]

# ── Tool name → handler function ──────────────────────────────
# State-modifying tools: create_plan, update_plan_status
# These handlers receive (state, **tool_input) instead of (**tool_input)
STATE_TOOLS = {"create_plan", "update_plan_status"}

TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
    "create_plan": run_create_plan,
    "update_plan_status": run_update_plan_status,
}
