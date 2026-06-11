from learn_agent.tools.run_bash import run_bash
from learn_agent.tools.run_read import run_read
from learn_agent.tools.run_write import run_write
from learn_agent.tools.run_edit import run_edit
from learn_agent.tools.run_glob import run_glob

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
]

# ── Tool name → handler function ──────────────────────────────
TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}
