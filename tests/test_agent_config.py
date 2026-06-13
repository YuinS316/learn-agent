import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from learn_agent.agent_config import (
    AgentConfig, PARENT_AGENT_CONFIG, SUBAGENT_CONFIG,
    PARENT_SYSTEM_PROMPT, SUBAGENT_SYSTEM_PROMPT,
)
from learn_agent.tools.register_tools import filter_tools


class TestAgentConfig:
    def test_parent_config_role(self):
        assert PARENT_AGENT_CONFIG.role == "parent"
        assert PARENT_AGENT_CONFIG.can_delegate is True

    def test_subagent_config_role(self):
        assert SUBAGENT_CONFIG.role == "subagent"
        assert SUBAGENT_CONFIG.can_delegate is False

    def test_parent_has_all_tools(self):
        assert "bash" in PARENT_AGENT_CONFIG.allowed_tool_names
        assert "delegate_task" in PARENT_AGENT_CONFIG.allowed_tool_names
        assert "create_plan" in PARENT_AGENT_CONFIG.allowed_tool_names

    def test_subagent_only_readonly_tools(self):
        assert SUBAGENT_CONFIG.allowed_tool_names == frozenset({"glob", "read_file"})
        assert "write_file" not in SUBAGENT_CONFIG.allowed_tool_names
        assert "delegate_task" not in SUBAGENT_CONFIG.allowed_tool_names

    def test_parent_turns_greater_than_subagent(self):
        assert PARENT_AGENT_CONFIG.max_turns > SUBAGENT_CONFIG.max_turns

    def test_frozen_prevents_assignment(self):
        with pytest.raises(Exception):
            SUBAGENT_CONFIG.max_turns = 100

    def test_frozenset_prevents_mutation(self):
        with pytest.raises(AttributeError):
            SUBAGENT_CONFIG.allowed_tool_names.add("bash")  # type: ignore

    def test_system_prompts_not_empty(self):
        assert len(PARENT_SYSTEM_PROMPT) > 0
        assert len(SUBAGENT_SYSTEM_PROMPT) > 0
        assert "coding agent" in PARENT_SYSTEM_PROMPT
        assert "read-only" in SUBAGENT_SYSTEM_PROMPT


class TestFilterTools:
    def test_filter_parent_tools(self):
        tools = filter_tools(PARENT_AGENT_CONFIG.allowed_tool_names)
        names = {t["name"] for t in tools}
        assert "bash" in names
        assert "delegate_task" in names
        assert len(tools) == len(PARENT_AGENT_CONFIG.allowed_tool_names)

    def test_filter_subagent_tools(self):
        tools = filter_tools(SUBAGENT_CONFIG.allowed_tool_names)
        names = {t["name"] for t in tools}
        assert names == {"glob", "read_file"}

    def test_filter_empty_set(self):
        tools = filter_tools(frozenset())
        assert tools == []

    def test_filter_unknown_tool(self):
        tools = filter_tools(frozenset({"nonexistent_tool"}))
        assert tools == []
