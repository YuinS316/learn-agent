from learn_agent.loop_state import LoopState
from learn_agent.skill_registry import registry


def run_load_skill(state: LoopState, name: str) -> str:
    """Load a skill's full documentation. Called by the parent agent via tool use."""
    body = registry.load_skill(name.strip())
    if body is None:
        available = ", ".join(registry.list_names()) or "(none)"
        return f"Error: skill '{name}' not found. Available: {available}"
    return body
