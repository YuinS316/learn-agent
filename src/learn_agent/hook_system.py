"""Global hook system for agent lifecycle interception.

Six hook stages (see docs/2026-06-21-hooks.md):
- USER_PROMPT_SUBMIT — user submits prompt, before agent loop
- PRE_TOOL_USE      — before tool handler executes
- POST_TOOL_USE     — after tool handler returns + L1 compaction
- SUBAGENT_START    — subagent dispatched, before its agent loop
- SUBAGENT_STOP     — subagent returns, after its agent loop
- STOP              — agent loop exiting (unified exit point)

Hooks are global: they fire for both parent and subagent.
Use ctx.config.role to distinguish ("parent" | "subagent").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from learn_agent.agent_config import AgentConfig
from learn_agent.loop_state import LoopState


# ── Stage enum ─────────────────────────────────────────────────

class HookStage(Enum):
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    STOP = "stop"


# ── Hook context ───────────────────────────────────────────────

@dataclass
class HookContext:
    """Context passed to every hook. Hooks may read and modify `data`."""
    stage: HookStage
    state: LoopState
    config: AgentConfig
    data: dict = field(default_factory=dict)


# ── Hook function type ─────────────────────────────────────────
#
# Return values:
#   None         — continue, context unchanged
#   HookContext  — modified context (data was changed)
#   False        — abort / intercept (only meaningful for PRE_TOOL_USE)

HookFunc = Callable[[HookContext], HookContext | None | bool]


# ── Hook entry (internal) ──────────────────────────────────────

@dataclass
class _HookEntry:
    priority: int
    func: HookFunc
    critical: bool


# ── Registry ───────────────────────────────────────────────────

class HookRegistry:
    """Global singleton registry for hook functions.

    Usage:
        from learn_agent.hook_system import HookStage, hook_registry

        hook_registry.register(HookStage.POST_TOOL_USE, my_hook, priority=50)
    """

    _instance: HookRegistry | None = None

    def __init__(self) -> None:
        self._hooks: dict[HookStage, list[_HookEntry]] = {
            stage: [] for stage in HookStage
        }

    @classmethod
    def get(cls) -> HookRegistry:
        """Return the global singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Registration ───────────────────────────────────────

    def register(
        self,
        stage: HookStage,
        func: HookFunc,
        priority: int = 100,
        critical: bool = False,
    ) -> None:
        """Register a hook function for a lifecycle stage.

        Args:
            stage: Which lifecycle stage to hook into.
            func: The hook function. See HookFunc for return semantics.
            priority: Execution order (lower = earlier). Default 100.
            critical: If True, exceptions bubble up instead of being swallowed.
        """
        entry = _HookEntry(priority=priority, func=func, critical=critical)
        self._hooks[stage].append(entry)
        self._hooks[stage].sort(key=lambda e: e.priority)

    # ── Fire ───────────────────────────────────────────────

    def fire(self, stage: HookStage, ctx: HookContext) -> HookContext | bool:
        """Fire all hooks registered for *stage* in priority order.

        Returns:
            HookContext — the (possibly modified) context to continue with.
            False       — a PRE_TOOL_USE hook aborted the tool.
        """
        for entry in self._hooks[stage]:
            try:
                result = entry.func(ctx)
            except Exception as exc:
                print(
                    f"\033[35m[Hook]\033[0m {stage.value} error "
                    f"(priority={entry.priority}): {exc}"
                )
                if entry.critical:
                    raise
                continue

            if result is False:
                return False
            if isinstance(result, HookContext):
                ctx = result

        return ctx

    # ── Introspection ──────────────────────────────────────

    def count(self, stage: HookStage | None = None) -> int:
        """Return the total number of registered hooks (optionally for a stage)."""
        if stage is not None:
            return len(self._hooks[stage])
        return sum(len(v) for v in self._hooks.values())

    # ── Clear ──────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all hooks. Useful for testing."""
        for stage in HookStage:
            self._hooks[stage].clear()


# ── Global singleton ───────────────────────────────────────────

hook_registry = HookRegistry.get()
