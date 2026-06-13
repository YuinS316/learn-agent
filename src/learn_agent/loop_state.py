import copy
from dataclasses import dataclass, field


@dataclass
class Plan:
    content: str       # e.g. "Read existing code"
    status: str        # "pending" | "doing" | "done"
    description: str   # e.g. "Use glob to find .py files and read key modules"


@dataclass
class LoopState:
    messages: list
    turn_count: int = 1
    transition_reason: str | None = None
    goal: str = ""
    plans: list[Plan] | None = None

    failure_count: int = 0
    consecutive_failures: int = 0
    failure_log: list[str] = field(default_factory=list)
    stopped_reason: str | None = None

    def plan_snapshot(self) -> list[Plan] | None:
        """Return a deep copy of plans for rollback purposes."""
        return copy.deepcopy(self.plans) if self.plans else None

    def rollback_plans(self, snapshot: list[Plan] | None) -> None:
        """Restore plans from a snapshot. None means keep current plans."""
        if snapshot is not None:
            self.plans = copy.deepcopy(snapshot)

    def reset_runtime_state(self) -> None:
        """Reset request-scoped runtime fields without touching messages.

        Used when reusing a LoopState across retry attempts or when
        failure-recovery requires a clean slate.
        Does NOT clear messages (the conversation history).
        """
        self.turn_count = 1
        self.transition_reason = None
        self.goal = ""
        self.plans = None
        self.failure_count = 0
        self.consecutive_failures = 0
        self.failure_log.clear()
        self.stopped_reason = None
