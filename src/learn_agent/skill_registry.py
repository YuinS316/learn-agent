import glob as _g
import os
from dataclasses import dataclass


@dataclass
class SkillInfo:
    name: str
    description: str
    body: str
    dir_path: str   # absolute path of the skill directory


class SkillRegistry:
    def __init__(self, skills_root: str = ".agents/skills") -> None:
        self._root = skills_root
        self.skills: list[SkillInfo] = []

    # ── Discovery ─────────────────────────────────────────────

    def discover(self) -> int:
        """Scan the skills directory, parse all SKILL.md files.
        Returns the number of successfully loaded skills."""
        self.skills.clear()
        pattern = os.path.join(self._root, "*", "SKILL.md")
        for path in _g.glob(pattern):
            skill = self._load_one(path)
            if skill:
                self.skills.append(skill)
        return len(self.skills)

    def _load_one(self, path: str) -> SkillInfo | None:
        """Parse a single SKILL.md. Returns None on failure."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"\033[33m ⚠ Failed to read {path}: {e}\033[0m")
            return None

        try:
            frontmatter, body = _parse_frontmatter(text)
        except ValueError as e:
            print(f"\033[33m ⚠ Skipping {path}: {e}\033[0m")
            return None

        return SkillInfo(
            name=frontmatter["name"],
            description=frontmatter["description"],
            body=body.strip(),
            dir_path=os.path.abspath(os.path.dirname(path)),
        )

    # ── Prompt building ───────────────────────────────────────

    def build_skills_prompt(self) -> str:
        """Return a string listing available skills for injection into system prompt."""
        if not self.skills:
            return ""
        lines = ["\n\nAvailable Skills", "─────────────────"]
        for s in self.skills:
            lines.append(f"• {s.name} — {s.description}")
        return "\n".join(lines)

    # ── Skill loading ─────────────────────────────────────────

    def load_skill(self, name: str) -> str | None:
        """Return the body of a skill by name, or None if not found."""
        for s in self.skills:
            if s.name == name:
                return s.body
        return None

    def list_names(self) -> list[str]:
        return [s.name for s in self.skills]


# ── Frontmatter parsing ─────────────────────────────────────

# ── Global registry instance ─────────────────────────────────

registry = SkillRegistry()


# ── Frontmatter parsing ─────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter delimited by ---.
    Returns ({name, description}, body_after_frontmatter).
    Raises ValueError on malformed input."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("Missing opening ---")

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("Missing closing ---")

    frontmatter: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()

    if "name" not in frontmatter or "description" not in frontmatter:
        raise ValueError("Missing name or description in frontmatter")

    body = "\n".join(lines[end_idx + 1:])
    return frontmatter, body
