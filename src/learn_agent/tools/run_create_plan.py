from learn_agent.config.settings import settings
from learn_agent.loop_state import LoopState, Plan


def run_create_plan(state: LoopState, goal: str, plans: list[dict]) -> str:
    """Create a structured execution plan. Called by the agent via tool use."""
    max_items = settings.MAX_PLAN_ITEMS

    if not goal.strip():
        return "Error: goal must not be empty"

    if not plans:
        return "Error: plans must contain at least one item"

    if len(plans) > max_items:
        return f"Error: too many plan items ({len(plans)}). Maximum is {max_items}"

    parsed = []
    for i, p in enumerate(plans):
        content = p.get("content", "").strip()
        description = p.get("description", "").strip()
        if not content:
            return f"Error: plan[{i}] missing 'content' field"
        if not description:
            return f"Error: plan[{i}] missing 'description' field"
        parsed.append(Plan(content=content, status="pending", description=description))

    state.goal = goal.strip()
    # First plan starts as doing
    if parsed:
        parsed[0].status = "doing"
    state.plans = parsed

    plan_lines = [
        f"✅ Plan created with {len(parsed)} items:",
        f"Goal: {state.goal}",
    ]
    for i, p in enumerate(parsed):
        plan_lines.append(f"  [{i}] ({p.status}) {p.content}: {p.description}")

    return "\n".join(plan_lines)
