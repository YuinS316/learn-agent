import os
import json

from anthropic import Anthropic
from dotenv import load_dotenv

from learn_agent.config.settings import settings
from learn_agent.loop_state import LoopState

from learn_agent.tools.register_tools import TOOLS, TOOL_HANDLERS, STATE_TOOLS
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

BASE_SYSTEM = (
    f"You are a coding agent at {CWD}. "
    "Use tools to solve tasks. Act, don't explain. "
    "For complex multi-step tasks, use create_plan first, then work through each step "
    "by updating plan statuses with update_plan_status. "
    "Always mark the current step 'done' BEFORE starting the next one. "
    "Only ONE plan item can be 'doing' at a time."
)

client = Anthropic(
    api_key=settings.ANTHROPIC_API_KEY,
    base_url=settings.ANTHROPIC_BASE_URL,
)


# ── Dynamic system prompt ───────────────────────────────────

def build_system(state: LoopState) -> str:
    """Build the system prompt, injecting current goal and plan progress."""
    prompt = BASE_SYSTEM

    if state.goal:
        prompt += f"\n\n## Goal\n{state.goal}"

    if state.plans:
        prompt += "\n\n## Plan Progress\n"
        icon_map = {"pending": "⬜", "doing": "🟡", "done": "✅"}
        for i, p in enumerate(state.plans):
            icon = icon_map.get(p.status, "❓")
            prompt += f"{icon} [{i}] ({p.status}) {p.content}: {p.description}\n"
        prompt += (
            "\nWork through plans in order. "
            "Only ONE plan 'doing' at a time. "
            "Mark current plan 'done' before starting the next."
        )

    return prompt


# ── Plan progress validation ────────────────────────────────

def _compute_correct_plans(plans: list) -> list:
    """Compute the correct status for each plan based on the ordering rules.
    Returns a list of corrected status strings (same length as plans)."""
    n = len(plans)
    corrected = ["pending"] * n

    # Find the last index that was actually 'done' (the valid prefix)
    # Scan forward: everything up to the first non-done/non-sequential item
    last_done = -1
    doing_found = False
    for i, p in enumerate(plans):
        if p.status == "done" and not doing_found:
            last_done = i
        elif p.status == "doing" and not doing_found:
            doing_found = True
            # This 'doing' is valid — it directly follows the 'done' prefix
        else:
            # First 'pending' or out-of-order item — stop scanning
            break

    # Apply corrections
    for i in range(n):
        if i <= last_done:
            corrected[i] = "done"
        elif i == last_done + 1:
            # The plan right after the done zone: keep as 'doing' if model set it,
            # or 'pending' if model didn't reach it yet
            if not doing_found and plans[i].status == "doing":
                corrected[i] = "doing"
            elif doing_found:
                corrected[i] = "doing"
            else:
                corrected[i] = "pending"
        else:
            corrected[i] = "pending"

    return corrected


def validate_plan_progress(state: LoopState) -> str | None:
    """Validate plan status ordering.

    Rules:
    1. At most one plan 'doing' at a time.
    2. Plans must be in order: done(s) → doing(0/1) → pending(s).
    3. No interleaving (e.g. done → pending → doing).

    If violated, rolls back to the correct state and returns an error message
    to feed back to the model.
    """
    if not state.plans:
        return None

    plans = state.plans
    corrected_statuses = _compute_correct_plans(plans)

    # Check for violations
    violations = []
    for i, p in enumerate(plans):
        if p.status != corrected_statuses[i]:
            violations.append(f"plan[{i}] was '{p.status}', corrected to '{corrected_statuses[i]}'")

    if not violations:
        return None

    # Apply corrections
    for i, p in enumerate(plans):
        p.status = corrected_statuses[i]

    return (
        "Plan progress violation detected:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\nRemember: work through plans in order. "
        "Only ONE plan 'doing' at a time. "
        "Mark current 'done' before starting the next."
    )


# ── Tool execution ──────────────────────────────────────────

def execute_tool_use_blocks(tool_use_blocks: list[dict],
                            state: LoopState) -> list[dict]:
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

        # State-modifying tools receive state as first argument
        if name in STATE_TOOLS:
            output = handler(state, **tool_input)
        else:
            output = handler(**tool_input)

        print(output[:5000])
        results.append({
            "type": "tool_result",
            "tool_use_id": tu["id"],
            "content": output,
        })

    return results


# ── Agent loop core ─────────────────────────────────────────

def run_one_turn(state: LoopState) -> bool:
    """Run one turn of the agent loop. Returns True if should continue."""

    system = build_system(state)

    response = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=8000,
        system=system,
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
    tool_results = execute_tool_use_blocks(tool_use_blocks, state)

    if not tool_results:
        state.transition_reason = None
        return False

    # ── Validate plan progress after tool execution ───────
    violation = validate_plan_progress(state)
    if violation:
        # Append violation message as an extra tool_result to inform the model
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": "plan_validator",
            "content": violation,
        })

    # Append tool results as a user message (Anthropic convention)
    state.messages.append({"role": "user", "content": tool_results})
    state.turn_count += 1
    state.transition_reason = "tool_result"
    return True


def agent_loop(state: LoopState) -> None:
    while run_one_turn(state):
        pass
