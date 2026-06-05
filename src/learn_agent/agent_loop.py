import os
import subprocess
import json
from openai import OpenAI
from dotenv import load_dotenv

from learn_agent.config.settings import settings

try:
    import readline
    # macOS 的 libedit 在处理中文输入时有退格问题，这四行修复它
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass

load_dotenv(".env")

CWD = os.getcwd()

SYSTEM = f"You are a coding agent at {CWD}. Use bash to solve tasks. Act, don't explain."

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)

# ── Tool definition: just bash (OpenAI format) ────────────────────────────
TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                }
            },
            "required": ["command"],
        },
    }
}]


# ── Tool execution ────────────────────────────────────────
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=CWD,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

def agent_loop(messages: list):
    # Prepend system message if not already present
    if not any(m.get("role") == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": SYSTEM})

    while True:
        response = client.chat.completions.create(
            tools=TOOLS,
            tool_choice="auto",  # 让模型自动决定是否调用工具
            messages=messages,
            max_tokens=8000,
            model=settings.openai_model,
        )

        message = response.choices[0].message

        # Append assistant turn
        messages.append(message.model_dump())

        # If the model didn't call a tool, we're done
        if not message.tool_calls:
            return

        # Execute each tool call, collect results
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            if function_name == "bash":
                command = arguments.get("command", "")
                print(f"\033[33m$ {command}\033[0m")
                output = run_bash(command)
                print(output[:200])

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": output,
                })

        # Loop continues, model will see tool results