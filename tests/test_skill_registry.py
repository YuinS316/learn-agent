import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from pathlib import Path
from learn_agent.skill_registry import (
    SkillRegistry, SkillInfo, _parse_frontmatter, registry,
)


# ── _parse_frontmatter unit tests ────────────────────────

class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        text = """---
name: test-skill
description: A test skill for testing
---
# Body

Some content."""
        fm, body = _parse_frontmatter(text)
        assert fm["name"] == "test-skill"
        assert fm["description"] == "A test skill for testing"
        assert "# Body" in body

    def test_missing_opening_dashes(self):
        with pytest.raises(ValueError, match="Missing opening"):
            _parse_frontmatter("name: test\n---\nbody")

    def test_missing_closing_dashes(self):
        with pytest.raises(ValueError, match="Missing closing"):
            _parse_frontmatter("---\nname: test\ndescription: desc\nbody")

    def test_missing_name(self):
        with pytest.raises(ValueError, match="Missing name"):
            _parse_frontmatter("---\ndescription: desc\n---\nbody")

    def test_missing_description(self):
        with pytest.raises(ValueError, match="Missing"):
            _parse_frontmatter("---\nname: test\n---\nbody")

    def test_empty_frontmatter(self):
        with pytest.raises(ValueError, match="Missing name"):
            _parse_frontmatter("---\n---\nbody")

    def test_body_preserves_markdown(self):
        text = """---
name: md-test
description: Tests markdown
---
# Title

## Section

- item 1
- item 2

```python
print("hello")
```"""
        fm, body = _parse_frontmatter(text)
        assert "## Section" in body
        assert "```python" in body
        assert 'print("hello")' in body

    def test_single_line_frontmatter(self):
        text = """---
name: s
description: d
---
body"""
        fm, body = _parse_frontmatter(text)
        assert fm["name"] == "s"
        assert fm["description"] == "d"
        assert body.strip() == "body"


# ── SkillRegistry discovery tests ────────────────────────

class TestSkillRegistryDiscovery:
    def test_empty_dir_returns_zero(self, tmp_path):
        r = SkillRegistry(skills_root=str(tmp_path))
        n = r.discover()
        assert n == 0
        assert r.skills == []

    def test_single_valid_skill(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: Does something useful
---
# My Skill

Step by step instructions.""")
        r = SkillRegistry(skills_root=str(tmp_path))
        n = r.discover()
        assert n == 1
        assert r.skills[0].name == "my-skill"
        assert r.skills[0].description == "Does something useful"
        assert "Step by step" in r.skills[0].body
        assert r.skills[0].dir_path == str(skill_dir.resolve())

    def test_multiple_skills(self, tmp_path):
        for name in ["skill-a", "skill-b", "skill-c"]:
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"""---
name: {name}
description: Description for {name}
---
Body for {name}.""")
        r = SkillRegistry(skills_root=str(tmp_path))
        n = r.discover()
        assert n == 3

    def test_skips_invalid_skill(self, tmp_path):
        d = tmp_path / "broken"
        d.mkdir()
        (d / "SKILL.md").write_text("No frontmatter at all")
        r = SkillRegistry(skills_root=str(tmp_path))
        n = r.discover()
        assert n == 0

    def test_mixed_valid_and_invalid(self, tmp_path):
        (tmp_path / "good").mkdir()
        (tmp_path / "good" / "SKILL.md").write_text("""---
name: good
description: valid
---
Content.""")
        (tmp_path / "bad").mkdir()
        (tmp_path / "bad" / "SKILL.md").write_text("garbage")
        r = SkillRegistry(skills_root=str(tmp_path))
        n = r.discover()
        assert n == 1
        assert r.skills[0].name == "good"

    def test_subdir_without_skillmd_ignored(self, tmp_path):
        (tmp_path / "empty-dir").mkdir()
        r = SkillRegistry(skills_root=str(tmp_path))
        n = r.discover()
        assert n == 0

    def test_skill_dir_path_is_absolute(self, tmp_path):
        d = tmp_path / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text("""---
name: skill
description: desc
---
body""")
        r = SkillRegistry(skills_root=str(tmp_path))
        r.discover()
        assert os.path.isabs(r.skills[0].dir_path)

    def test_unicode_in_skill(self, tmp_path):
        d = tmp_path / "unicode"
        d.mkdir()
        (d / "SKILL.md").write_text("""---
name: unicode
description: 中文描述
---
# 标题
内容""")
        r = SkillRegistry(skills_root=str(tmp_path))
        r.discover()
        assert "中文描述" in r.skills[0].description


# ── SkillRegistry operations ─────────────────────────────

class TestSkillRegistryOps:
    @pytest.fixture
    def populated_registry(self, tmp_path):
        for name, desc in [("a", "first"), ("b", "second")]:
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"""---
name: {name}
description: {desc}
---
Body of {name}.""")
        r = SkillRegistry(skills_root=str(tmp_path))
        r.discover()
        return r

    def test_build_skills_prompt(self, populated_registry):
        prompt = populated_registry.build_skills_prompt()
        assert "a" in prompt
        assert "first" in prompt
        assert "b" in prompt
        assert "second" in prompt
        assert "Available Skills" in prompt

    def test_build_skills_prompt_empty(self, tmp_path):
        r = SkillRegistry(skills_root=str(tmp_path))
        r.discover()
        assert r.build_skills_prompt() == ""

    def test_load_skill_found(self, populated_registry):
        body = populated_registry.load_skill("a")
        assert body is not None
        assert "Body of a" in body

    def test_load_skill_not_found(self, populated_registry):
        body = populated_registry.load_skill("nonexistent")
        assert body is None

    def test_list_names(self, populated_registry):
        names = populated_registry.list_names()
        assert names == ["a", "b"]

    def test_discover_overwrites_previous(self, populated_registry, tmp_path):
        # Clear the dir and re-discover
        import shutil
        shutil.rmtree(tmp_path / "a")
        shutil.rmtree(tmp_path / "b")
        n = populated_registry.discover()
        assert n == 0
        assert populated_registry.skills == []


# ── Real skills directory integration ─────────────────────

class TestRealSkills:
    def test_real_skills_discovered(self):
        """Verify the real .agents/skills/ directory has at least 3 skills."""
        r = SkillRegistry()  # default ".agents/skills"
        n = r.discover()
        assert n >= 3
        names = r.list_names()
        assert "test-driven-development" in names
        assert "systematic-debugging" in names

    def test_every_real_skill_loadable(self):
        """Every discovered skill should return non-empty body."""
        r = SkillRegistry()
        r.discover()
        for s in r.skills:
            body = r.load_skill(s.name)
            assert body is not None, f"Skill {s.name} not loadable"
            assert len(body) > 0, f"Skill {s.name} has empty body"

    def test_real_skills_have_description(self):
        r = SkillRegistry()
        r.discover()
        for s in r.skills:
            assert len(s.description) > 0, f"Skill {s.name} has empty description"
