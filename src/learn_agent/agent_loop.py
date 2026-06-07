import os
import subprocess
import json

from openai import OpenAI
from dotenv import load_dotenv

from learn_agent.config.settings import settings
from learn_agent.loop_state import LoopState

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


def execute_tool_calls(tool_calls) -> list[dict]:
    results = []

    for tool_call in tool_calls:
        function_name = tool_call.function.name
        if function_name != "bash":
            continue

        arguments = json.loads(tool_call.function.arguments)
        command = arguments.get("command", "")

        print(f"\033[33m$ {command}\033[0m")
        output = run_bash(command)
        print(output[:5000])
        results.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": output,
        })

    return results

def run_one_turn(state: LoopState) -> bool:
    """Run one turn of the agent loop. Returns True if should continue."""

    messages = state.messages

    # Add system message at the beginning if not present
    if not any(m.get("role") == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": SYSTEM})

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        max_tokens=8000,
    )

    message = response.choices[0].message

    #  It doesn't need to execute tools — save final response and stop
    if not message.tool_calls:
        state.messages.append({
            "role": "assistant",
            "content": message.content or "",
        })
        state.transition_reason = None
        return False

    # Convert assistant message to dict for storage
    assistant_dict = {
        "role": "assistant",
        "content": message.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            }
            for tc in message.tool_calls
        ]
    }

    state.messages.append(assistant_dict)

    # Execute tool calls
    results = execute_tool_calls(message.tool_calls)

    if not results:
        state.transition_reason = None
        return False

    state.messages.extend(results)
    state.turn_count += 1
    state.transition_reason = "tool_result"
    return True


def agent_loop(state: LoopState) -> None:
    while run_one_turn(state):
        pass