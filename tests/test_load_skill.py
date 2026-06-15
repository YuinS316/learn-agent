import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import MagicMock, patch
from learn_agent.loop_state import LoopState
from learn_agent.agent_config import PARENT_AGENT_CONFIG, SUBAGENT_CONFIG
from learn_agent.skill_registry import SkillRegistry


# ── Helpers ──────────────────────────────────────────────

class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text

class FakeToolUseBlock:
    def __init__(self, id, name, input_data):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input_data

class FakeResponse:
    def __init__(self, content_blocks):
        self.content = content_blocks


# ── run_load_skill tests ─────────────────────────────────

class TestRunLoadSkill:
    def test_loads_known_skill(self, tmp_path):
        from learn_agent.tools.run_load_skill import run_load_skill
        from learn_agent.skill_registry import registry as global_reg

        # Set up a temp skill
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("""---
name: my-skill
description: Test skill
---
# My Skill
Step 1: Do this.
Step 2: Do that.""")

        r = SkillRegistry(skills_root=str(tmp_path))
        r.discover()

        # Patch the global registry
        with patch('learn_agent.tools.run_load_skill.registry', r):
            state = LoopState(messages=[])
            result = run_load_skill(state, "my-skill")
            assert "Step 1" in result
            assert "Step 2" in result

    def test_unknown_skill_returns_error(self, tmp_path):
        from learn_agent.tools.run_load_skill import run_load_skill

        r = SkillRegistry(skills_root=str(tmp_path))
        r.discover()

        with patch('learn_agent.tools.run_load_skill.registry', r):
            state = LoopState(messages=[])
            result = run_load_skill(state, "nonexistent")
            assert "not found" in result.lower()
            assert "Available" in result


# ── Permission check ─────────────────────────────────────

class TestLoadSkillPermissions:
    def test_subagent_cannot_load_skill(self):
        from learn_agent.agent_loop import execute_tool_use_blocks
        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "t1", "name": "load_skill",
             "input": {"name": "anything"}},
        ]
        results = execute_tool_use_blocks(blocks, state, SUBAGENT_CONFIG)
        assert "not allowed" in results[0]["content"]

    def test_parent_can_load_skill(self):
        from learn_agent.agent_loop import execute_tool_use_blocks
        from learn_agent import skill_registry as sr
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp())
        d = tmp / "demo"
        d.mkdir()
        (d / "SKILL.md").write_text("""---
name: demo
description: A demo skill
---
# Demo
This is the demo body.""")

        # Create a local registry with one skill
        local_reg = SkillRegistry(skills_root=str(tmp))
        local_reg.discover()

        # Patch both references to the registry
        with patch('learn_agent.agent_loop.registry', local_reg), \
             patch('learn_agent.tools.run_load_skill.registry', local_reg):
            state = LoopState(messages=[])
            blocks = [
                {"type": "tool_use", "id": "t1", "name": "load_skill",
                 "input": {"name": "demo"}},
            ]
            results = execute_tool_use_blocks(blocks, state, PARENT_AGENT_CONFIG)
            assert "demo body" in results[0]["content"]


# ── build_system integration ─────────────────────────────

class TestBuildSystemSkills:
    def test_system_prompt_contains_skills(self, tmp_path):
        from learn_agent.agent_loop import build_system
        from learn_agent import agent_loop as al

        d = tmp_path / "test-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("""---
name: test-skill
description: For testing things
---
Body.""")

        local_reg = SkillRegistry(skills_root=str(tmp_path))
        local_reg.discover()

        with patch.object(al, 'registry', local_reg):
            state = LoopState(messages=[])
            prompt = build_system(state, PARENT_AGENT_CONFIG)
            assert "test-skill" in prompt
            assert "For testing things" in prompt

    def test_subagent_prompt_excludes_skills(self, tmp_path):
        from learn_agent.agent_loop import build_system
        from learn_agent import agent_loop as al

        d = tmp_path / "test-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("""---
name: test-skill
description: For testing
---
Body.""")

        local_reg = SkillRegistry(skills_root=str(tmp_path))
        local_reg.discover()

        with patch.object(al, 'registry', local_reg):
            state = LoopState(messages=[])
            prompt = build_system(state, SUBAGENT_CONFIG)
            assert "test-skill" not in prompt


# ── Registry global usage ────────────────────────────────

class TestGlobalRegistry:
    def test_global_registry_is_singleton(self):
        from learn_agent.skill_registry import registry as r1
        from learn_agent.skill_registry import registry as r2
        assert r1 is r2

    def test_discover_real_skills_on_global(self):
        from learn_agent.skill_registry import registry
        n = registry.discover()
        assert n >= 3
