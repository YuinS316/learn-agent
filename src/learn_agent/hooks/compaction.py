"""Compaction hooks — L1 via POST_TOOL_USE, L2 via PRE_API_CALL.

Register these hooks at startup to replace hardcoded compaction logic.
"""

from learn_agent.hook_system import HookContext, HookStage, hook_registry
from learn_agent.compaction import (
    apply_l1_compaction,
    apply_l2_compaction,
    estimate_context_tokens,
    resolve_context_window,
)
from learn_agent.config.settings import settings


def _l1_post_tool_use(ctx: HookContext) -> HookContext | None:
    """L1 compaction: cache large tool results to disk.

    Registered on POST_TOOL_USE. Only runs when the agent config enables L1.
    """
    if not settings.COMPACTION_ENABLED or not settings.L1_ENABLED:
        return None
    if not ctx.config.has_compaction_layer("L1"):
        return None

    result = ctx.data.get("result", "")
    tool_name = ctx.data.get("tool_name", "")
    tool_input = ctx.data.get("tool_input", {})

    new_result, l1_applied = apply_l1_compaction(
        result, tool_name, tool_input, ctx.state,
    )

    ctx.data["result"] = new_result
    ctx.data["l1_compacted"] = l1_applied
    return ctx


# ── L2 hook for PRE_API_CALL ───────────────────────────────────

def _l2_pre_api_call(ctx: HookContext) -> HookContext | None:
    """L2 compaction: trim old tool_result messages when context is high.

    Registered on PRE_API_CALL. Requires the messages list in ctx.data.
    """
    if not settings.COMPACTION_ENABLED or not settings.L2_ENABLED:
        return None
    if not ctx.config.has_compaction_layer("L2"):
        return None

    messages = ctx.data.get("messages", [])

    # Update token estimate if needed
    if ctx.state.estimated_tokens == 0:
        try:
            from learn_agent.agent_loop import client
            system = ctx.data.get("system", "")
            ctx.state.estimated_tokens = estimate_context_tokens(messages, system, client)
        except Exception:
            ctx.state.estimated_tokens = sum(len(str(m)) // 3 for m in messages) + 1000

    compacted = apply_l2_compaction(messages, ctx.state)
    ctx.data["messages"] = compacted
    return ctx


# ── Registration ───────────────────────────────────────────────

def register_compaction_hooks() -> None:
    """Register L1 and L2 compaction as hooks. Call once at startup."""
    hook_registry.register(HookStage.POST_TOOL_USE, _l1_post_tool_use, priority=90)
    hook_registry.register(HookStage.PRE_API_CALL, _l2_pre_api_call, priority=90)
