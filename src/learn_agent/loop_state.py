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

    def plan_snapshot(self) -> list[Plan] | None:
        """Return a deep copy of plans for rollback purposes."""
        return copy.deepcopy(self.plans) if self.plans else None

    def rollback_plans(self, snapshot: list[Plan] | None) -> None:
        """Restore plans from a snapshot. None means keep current plans."""
        if snapshot is not None:
            self.plans = copy.deepcopy(snapshot)
