from learn_agent.loop_state import LoopState


def run_update_plan_status(state: LoopState, plan_index: int, status: str) -> str:
    """Update the status of a plan item. Called by the agent via tool use."""
    if state.plans is None:
        return "Error: no plans exist. Use create_plan first."

    if not (0 <= plan_index < len(state.plans)):
        return f"Error: plan_index {plan_index} out of range (0–{len(state.plans) - 1})"

    if status not in ("pending", "doing", "done"):
        return f"Error: invalid status '{status}'. Must be one of: pending, doing, done"

    plan = state.plans[plan_index]
    old_status = plan.status
    plan.status = status

    return (
        f"Updated plan[{plan_index}] status: {old_status} → {status}\n"
        f"  Content: {plan.content}"
    )
