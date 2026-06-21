"""Skill discovery hook — runs once at AGENT_STARTUP."""

from learn_agent.hook_system import HookContext, HookStage, hook_registry
from learn_agent.skill_registry import registry


def _discover_skills(ctx: HookContext) -> HookContext | None:
    """Discover and print available skills at agent startup."""
    n = registry.discover()
    if n == 0:
        return None

    names = registry.list_names()
    display = "\n".join(names[:3])
    if len(names) > 3:
        display += "\n..."

    print(
        f"\033[1;36m📦 Found {n} skills:\n"
        f"{display}"
        f"\033[0m\n"
    )

    return None


def register_skills_hook() -> None:
    """Register skill discovery as an AGENT_STARTUP hook. Call once at startup."""
    hook_registry.register(HookStage.AGENT_STARTUP, _discover_skills, priority=100)
