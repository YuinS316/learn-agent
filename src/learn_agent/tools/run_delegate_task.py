from learn_agent.loop_state import LoopState
from learn_agent.agent_config import SUBAGENT_CONFIG
from learn_agent.hook_system import HookContext, HookStage, hook_registry


def run_delegate_task(
    state: LoopState,
    task: str,
    context: str = "",
    relevant_paths: list[str] | None = None,
    output_format: str = "",
) -> str:
    """Delegate a read-only information-gathering task to a subagent.

    Called by the parent agent via tool use. Creates a child LoopState with
    isolated messages and runs a restricted agent loop.
    """
    if not task.strip():
        return "Error: task must not be empty"

    # ── Build subagent initial user message ────────────
    parts = [
        "You are a read-only research subagent.",
        "",
        f"Task:\n{task.strip()}",
    ]

    ctx = context.strip() if context else "(none)"
    parts.append(f"\nRelevant context from parent:\n{ctx}")

    paths = "\n".join(f"- {p}" for p in (relevant_paths or [])) if relevant_paths else "(none)"
    parts.append(f"\nSuggested paths:\n{paths}")

    fmt = output_format.strip() if output_format else "evidence-based summary with file paths and key findings"
    parts.append(f"\nExpected output format:\n{fmt}")

    user_message = {"role": "user", "content": "\n".join(parts)}

    # ── Run isolated subagent loop ─────────────────────
    from learn_agent.agent_loop import agent_loop  # lazy import to avoid circular dep

    # ── SUBAGENT_START hook ────────────────────────────
    start_ctx = HookContext(
        stage=HookStage.SUBAGENT_START,
        state=state,  # parent state
        config=SUBAGENT_CONFIG,
        data={
            "task": task.strip(),
            "context": ctx,
            "relevant_paths": relevant_paths or [],
        },
    )
    start_result = hook_registry.fire(HookStage.SUBAGENT_START, start_ctx)
    if isinstance(start_result, HookContext):
        task = start_result.data.get("task", task)
        relevant_paths = start_result.data.get("relevant_paths", relevant_paths)
        # Rebuild user_message with potentially modified task / paths
        paths = "\n".join(f"- {p}" for p in (relevant_paths or [])) if relevant_paths else "(none)"
        user_message["content"] = "\n".join([
            "You are a read-only research subagent.",
            "",
            f"Task:\n{task.strip()}",
            f"\nRelevant context from parent:\n{ctx}",
            f"\nSuggested paths:\n{paths}",
            f"\nExpected output format:\n{fmt}",
        ])

    child_state = LoopState(messages=[user_message])
    agent_loop(child_state, config=SUBAGENT_CONFIG)

    # ── Compose result ─────────────────────────────────
    child_result = _extract_final_text(child_state) or "(subagent returned no findings)"

    # ── SUBAGENT_STOP hook ─────────────────────────────
    stop_ctx = HookContext(
        stage=HookStage.SUBAGENT_STOP,
        state=state,  # parent state
        config=SUBAGENT_CONFIG,
        data={
            "result": child_result,
            "child_state": child_state,
        },
    )
    stop_result = hook_registry.fire(HookStage.SUBAGENT_STOP, stop_ctx)
    if isinstance(stop_result, HookContext):
        child_result = stop_result.data.get("result", child_result)

    if child_state.stopped_reason:
        failures = "\n".join(f"- {e}" for e in child_state.failure_log[-5:]) or "(none)"
        return (
            f"Subagent stopped: {child_state.stopped_reason}.\n"
            f"Recent failures:\n{failures}\n"
            f"Partial findings:\n{child_result}"
        )

    return child_result


def _extract_final_text(state: LoopState) -> str:
    """Extract text from the last assistant message in the child state."""
    for msg in reversed(state.messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"]
            return "\n".join(texts).strip()
    return ""
