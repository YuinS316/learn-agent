import os
import json

from anthropic import Anthropic
from dotenv import load_dotenv

from learn_agent.config.settings import settings
from learn_agent.loop_state import LoopState

from learn_agent.tools.register_tools import TOOLS, TOOL_HANDLERS
from learn_agent.utils.normalize_messages import normalize_messages

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

SYSTEM = f"You are a coding agent at {CWD}. Use tools to solve tasks. Act, don't explain."

client = Anthropic(
    api_key=settings.ANTHROPIC_API_KEY,
    base_url=settings.ANTHROPIC_BASE_URL,
)


def execute_tool_use_blocks(tool_use_blocks: list[dict]) -> list[dict]:
    """Execute tool_use blocks and return tool_result blocks."""
    results = []

    for tu in tool_use_blocks:
        name = tu["name"]
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            print(f"\033[33m Unknown tool: {name} \033[0m")
            results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": f"Error: unknown tool '{name}'",
            })
            continue

        tool_input = tu["input"]
        print(f"\033[33m> {name}({json.dumps(tool_input, ensure_ascii=False)})\033[0m")

        output = handler(**tool_input)
        print(output[:5000])
        results.append({
            "type": "tool_result",
            "tool_use_id": tu["id"],
            "content": output,
        })

    return results


def run_one_turn(state: LoopState) -> bool:
    """Run one turn of the agent loop. Returns True if should continue."""

    response = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=8000,
        system=SYSTEM,
        messages=normalize_messages(state.messages),
        tools=TOOLS,
    )

    # Separate text blocks and tool_use blocks from the response
    text_blocks = []
    tool_use_blocks = []
    for block in response.content:
        if block.type == "text":
            text_blocks.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            tool_use_blocks.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })

    # Build and store the assistant message (Anthropic format)
    assistant_msg = {
        "role": "assistant",
        "content": text_blocks + tool_use_blocks,
    }
    state.messages.append(assistant_msg)

    # If the model didn't call any tools, we're done
    if not tool_use_blocks:
        state.transition_reason = None
        return False

    # Execute tool calls and collect results
    tool_results = execute_tool_use_blocks(tool_use_blocks)

    if not tool_results:
        state.transition_reason = None
        return False

    # Append tool results as a user message (Anthropic convention)
    state.messages.append({"role": "user", "content": tool_results})
    state.turn_count += 1
    state.transition_reason = "tool_result"
    return True


def agent_loop(state: LoopState) -> None:
    while run_one_turn(state):
        pass
