import os
import json

from anthropic import Anthropic
from dotenv import load_dotenv

from learn_agent.config.settings import settings
from learn_agent.loop_state import LoopState
from learn_agent.agent_config import AgentConfig, PARENT_AGENT_CONFIG

from learn_agent.tools.register_tools import TOOLS, TOOL_HANDLERS, STATE_TOOLS, filter_tools
from learn_agent.utils.normalize_messages import normalize_messages
from learn_agent.skill_registry import registry
from learn_agent.compaction import (
    estimate_context_tokens,
    transcript_turn,
)
from learn_agent.hook_system import HookContext, HookStage, hook_registry

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

client = Anthropic(
    api_key=settings.ANTHROPIC_API_KEY,
    base_url=settings.ANTHROPIC_BASE_URL,
)


# ── Dynamic system prompt ───────────────────────────────────

def build_system(state: LoopState, config: AgentConfig) -> str:
    """Build the system prompt from config.system_prompt, injecting goal/plan progress."""
    prompt = config.system_prompt

    # Only parent agent gets plan progress + skills injection
    if config.role == "parent":
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

        # Inject available skills summary
        prompt += registry.build_skills_prompt()

    # ── Compaction status ──────────────────────
    if state.compaction_log:
        recent = state.compaction_log[-3:]
        prompt += "\n\n## Context Compaction Status\n"
        for entry in recent:
            prompt += (
                f"- L{entry['layer']} at turn {entry['turn']}: "
                f"saved {entry['saved_tokens']} tokens "
                f"({entry['before_tokens']} → {entry['after_tokens']})\n"
            )
        prompt += (
            f"Full transcript: .agents/transcripts/{state.session_id}.jsonl\n"
            f"Cached tool results: use read_file to access.\n"
            f"Do NOT expose internal cache paths to the user."
        )

    return prompt

# ── Plan progress validation ────────────────────────────────

def _compute_correct_plans(plans: list) -> list:
    """Compute the correct status for each plan based on the ordering rules.
    Returns a list of corrected status strings (same length as plans)."""
    n = len(plans)
    corrected = ["pending"] * n

    last_done = -1
    doing_found = False
    for i, p in enumerate(plans):
        if p.status == "done" and not doing_found:
            last_done = i
        elif p.status == "doing" and not doing_found:
            doing_found = True
        else:
            break

    for i in range(n):
        if i <= last_done:
            corrected[i] = "done"
        elif i == last_done + 1:
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
    """Validate plan status ordering. Returns violation message if any."""
    if not state.plans:
        return None

    plans = state.plans
    corrected_statuses = _compute_correct_plans(plans)

    violations = []
    for i, p in enumerate(plans):
        if p.status != corrected_statuses[i]:
            violations.append(f"plan[{i}] was '{p.status}', corrected to '{corrected_statuses[i]}'")

    if not violations:
        return None

    for i, p in enumerate(plans):
        p.status = corrected_statuses[i]

    return (
        "Plan progress violation detected:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\nRemember: work through plans in order. "
        "Only ONE plan 'doing' at a time. "
        "Mark current 'done' before starting the next."
    )


# ── Failure tracking ────────────────────────────────────────

def is_tool_error(content: str) -> bool:
    """Check if a tool result indicates an error."""
    return content.strip().startswith("Error:")


def short_error(content: str, max_len: int = 120) -> str:
    """Truncate an error message for logging."""
    return content[:max_len] + ("..." if len(content) > max_len else "")


# ── Safety stop ─────────────────────────────────────────────

def append_safety_stop_message(state: LoopState, reason: str) -> None:
    """Append a safety-stop assistant message to the state."""
    lines = [f"Stopped safely: {reason}.", ""]
    if state.failure_log:
        lines.append("Recent failures:")
        for f in state.failure_log[-5:]:
            lines.append(f"- {f}")
    state.messages.append({
        "role": "assistant",
        "content": [{"type": "text", "text": "\n".join(lines)}],
    })


# ── Tool execution ──────────────────────────────────────────

def execute_tool_use_blocks(tool_use_blocks: list[dict],
                            state: LoopState,
                            config: AgentConfig) -> list[dict]:
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

        # Permission check
        if name not in config.allowed_tool_names:
            print(f"\033[33m Blocked tool: {name} (not allowed for {config.role}) \033[0m")
            results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": f"Error: tool '{name}' is not allowed for {config.role}",
            })
            continue

        tool_input = tu["input"]
        if not isinstance(tool_input, dict):
            tool_input = {}

        # ── PRE_TOOL_USE hook ──────────────────────────
        pre_ctx = HookContext(
            stage=HookStage.PRE_TOOL_USE,
            state=state,
            config=config,
            data={"tool_name": name, "tool_input": dict(tool_input)},
        )
        pre_result = hook_registry.fire(HookStage.PRE_TOOL_USE, pre_ctx)
        if pre_result is False:
            results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": (
                    f"Error: tool '{name}' was blocked by PreToolUse hook. "
                    f"A hook returned False to prevent execution. "
                    f"Try a different approach or ask the user for guidance."
                ),
            })
            continue
        if isinstance(pre_result, HookContext):
            tool_input = pre_result.data.get("tool_input", tool_input)

        print(f"\033[33m> {name}({json.dumps(tool_input, ensure_ascii=False)})\033[0m")

        # State-modifying tools receive state as first argument
        try:
            if name in STATE_TOOLS:
                output = handler(state, **tool_input)
            else:
                output = handler(**tool_input)
        except TypeError as e:
            output = f"Error: tool '{name}' received invalid arguments: {e}"

        # ── POST_TOOL_USE hook (includes L1 compaction) ─
        post_ctx = HookContext(
            stage=HookStage.POST_TOOL_USE,
            state=state,
            config=config,
            data={"tool_name": name, "tool_input": tool_input, "result": output},
        )
        post_result = hook_registry.fire(HookStage.POST_TOOL_USE, post_ctx)
        if isinstance(post_result, HookContext):
            output = post_result.data.get("result", output)
            l1_applied = post_result.data.get("l1_compacted", False)
        else:
            l1_applied = False

        results.append({
            "type": "tool_result",
            "tool_use_id": tu["id"],
            "content": output,
            "_l1_compacted": l1_applied,
        })

    return results


# ── Agent loop core ─────────────────────────────────────────

def run_one_turn(state: LoopState, config: AgentConfig = PARENT_AGENT_CONFIG) -> bool:
    """Run one turn of the agent loop. Returns True if should continue."""

    system = build_system(state, config)

    # ── Normalize + PRE_API_CALL hook (includes L2 compaction) ──
    messages = normalize_messages(state.messages)

    pre_api_ctx = HookContext(
        stage=HookStage.PRE_API_CALL,
        state=state,
        config=config,
        data={"messages": messages, "system": system},
    )
    pre_api_result = hook_registry.fire(HookStage.PRE_API_CALL, pre_api_ctx)
    if isinstance(pre_api_result, HookContext):
        messages = pre_api_result.data.get("messages", messages)

    response = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=8000,
        system=system,
        messages=messages,
        tools=filter_tools(config.allowed_tool_names),
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

    # Build and store the assistant message
    assistant_msg = {
        "role": "assistant",
        "content": text_blocks + tool_use_blocks,
    }
    state.messages.append(assistant_msg)

    # ── Transcript: record assistant message ────────
    transcript_turn(state, assistant_msg)

    # If the model didn't call any tools, we're done
    if not tool_use_blocks:
        state.transition_reason = None
        return False

    # Execute tool calls and collect results
    tool_results = execute_tool_use_blocks(tool_use_blocks, state, config)

    if not tool_results:
        state.transition_reason = None
        return False

    # ── Failure tracking ────────────────────────────────
    failed_results = [r for r in tool_results if is_tool_error(r.get("content", ""))]

    if failed_results:
        state.failure_count += len(failed_results)
        state.consecutive_failures += len(failed_results)
        for r in failed_results:
            state.failure_log.append(short_error(r["content"]))
    else:
        state.consecutive_failures = 0

    # ── Max failures check ──────────────────────────────
    if state.failure_count >= config.max_failures:
        state.stopped_reason = "max_failures_exceeded"
        append_safety_stop_message(state, "max_failures_exceeded")
        return False

    # Append tool results as a user message
    state.messages.append({"role": "user", "content": tool_results})
    state.turn_count += 1
    state.transition_reason = "tool_result"

    # ── Transcript: record tool_result message ─────────
    transcript_turn(state, {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": r.get("tool_use_id", ""),
         "content": r.get("content", "")[:500]}
        for r in tool_results
    ]})

    # ── Update token estimate ─────────────────────────
    try:
        state.estimated_tokens = estimate_context_tokens(
            normalize_messages(state.messages), build_system(state, config), client)
    except Exception:
        state.estimated_tokens = state.estimated_tokens + 4000  # rough fallback

    # ── Plan progress validation (parent only) ─────────
    if config.role == "parent":
        violation = validate_plan_progress(state)
        if violation:
            state.messages.append({"role": "user", "content": violation})

    return True


def agent_loop(state: LoopState, config: AgentConfig = PARENT_AGENT_CONFIG) -> None:
    while state.turn_count <= config.max_turns:
        should_continue = run_one_turn(state, config)
        if not should_continue:
            break

    # Handle max_turns if that's why we exited
    if state.turn_count > config.max_turns and not state.stopped_reason:
        state.stopped_reason = "max_turns_exceeded"
        append_safety_stop_message(state, "max_turns_exceeded")

    # ── STOP hook (unified exit point) ────────────────
    reason = state.stopped_reason or "normal"
    stop_ctx = HookContext(
        stage=HookStage.STOP,
        state=state,
        config=config,
        data={"reason": reason},
    )
    hook_registry.fire(HookStage.STOP, stop_ctx)
