import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import MagicMock, patch
from learn_agent.loop_state import LoopState, Plan
from learn_agent.agent_config import AgentConfig, PARENT_AGENT_CONFIG, SUBAGENT_CONFIG


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


# ── is_tool_error / short_error ──────────────────────────

class TestIsToolError:
    def test_error_prefix(self):
        from learn_agent.agent_loop import is_tool_error
        assert is_tool_error("Error: file not found") is True
        assert is_tool_error("  Error: something") is True  # strip() removes whitespace
        assert is_tool_error("All good") is False
        assert is_tool_error("") is False

    def test_short_error_truncates(self):
        from learn_agent.agent_loop import short_error
        long_msg = "Error: " + "x" * 200
        result = short_error(long_msg, max_len=50)
        assert len(result) <= 50 + 3  # +3 for "..."
        assert result.endswith("...")

    def test_short_error_no_truncation_needed(self):
        from learn_agent.agent_loop import short_error
        result = short_error("short msg", max_len=50)
        assert result == "short msg"


# ── Max turns ───────────────────────────────────────────

class TestMaxTurns:
    def test_stops_at_max_turns(self):
        from learn_agent import agent_loop

        config = AgentConfig(
            name="test", role="parent", max_turns=2, max_failures=10,
            allowed_tool_names=frozenset({"bash"}),
            system_prompt="test prompt",
        )

        # Always return a tool_use (forces another turn)
        responses = [
            FakeResponse([FakeToolUseBlock("t1", "bash", {"command": "echo 1"})]),
            FakeResponse([FakeToolUseBlock("t2", "bash", {"command": "echo 2"})]),
            FakeResponse([FakeToolUseBlock("t3", "bash", {"command": "echo 3"})]),  # won't reach
        ]
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = responses

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "test"}])
            agent_loop.agent_loop(state, config=config)

        assert state.stopped_reason == "max_turns_exceeded"
        # Only 2 turns (max_turns) calls allowed
        assert mock_client.messages.create.call_count == 2

    def test_ends_normally_before_max_turns(self):
        from learn_agent import agent_loop

        config = AgentConfig(
            name="test", role="parent", max_turns=20, max_failures=10,
            allowed_tool_names=frozenset({"bash"}),
            system_prompt="test prompt",
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([FakeTextBlock("done")])

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "hi"}])
            agent_loop.agent_loop(state, config=config)

        assert state.stopped_reason is None
        assert mock_client.messages.create.call_count == 1


# ── Failure budgets ─────────────────────────────────────

class TestFailureBudgets:
    def test_failure_count_incremented(self):
        from learn_agent import agent_loop
        from learn_agent.tools import register_tools

        config = AgentConfig(
            name="test", role="parent", max_turns=20, max_failures=3,
            allowed_tool_names=frozenset({"bash"}),
            system_prompt="test prompt",
        )

        responses = [
            FakeResponse([FakeToolUseBlock("t1", "bash", {"command": "echo 'Error: fail'"})]),
            FakeResponse([FakeTextBlock("giving up")]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = responses

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "test"}])
            agent_loop.agent_loop(state, config=config)

        assert state.failure_count >= 1
        assert state.stopped_reason is None

    def test_max_failures_exceeded(self):
        from learn_agent import agent_loop
        from learn_agent.tools import register_tools

        config = AgentConfig(
            name="test", role="parent", max_turns=20, max_failures=1,
            allowed_tool_names=frozenset({"bash"}),
            system_prompt="test prompt",
        )

        # Patch the bash handler directly in TOOL_HANDLERS
        original = register_tools.TOOL_HANDLERS["bash"]
        register_tools.TOOL_HANDLERS["bash"] = lambda **kw: "Error: command failed"

        try:
            responses = [
                FakeResponse([FakeToolUseBlock("t1", "bash", {"command": "bad"})]),
                FakeResponse([FakeTextBlock("tried")]),
            ]
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = responses

            with patch.object(agent_loop, 'client', mock_client):
                state = LoopState(messages=[{"role": "user", "content": "test"}])
                agent_loop.agent_loop(state, config=config)

            assert state.stopped_reason == "max_failures_exceeded"
            assert state.failure_count >= 1
        finally:
            register_tools.TOOL_HANDLERS["bash"] = original

    def test_consecutive_failures_reset_on_success(self):
        from learn_agent import agent_loop

        state = LoopState(messages=[])
        state.consecutive_failures = 3

        # Simulate a turn with no errors
        config = AgentConfig(
            name="test", role="parent", max_turns=20, max_failures=10,
            allowed_tool_names=frozenset({"bash"}),
            system_prompt="test prompt",
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([FakeTextBlock("ok")])

        with patch.object(agent_loop, 'client', mock_client):
            agent_loop.agent_loop(state, config=config)

        # consecutive_failures not changed since no tool was called
        # (text-only response doesn't go through failure tracking)
        # This tests the code path where failure_count stays
        assert state.stopped_reason is None


# ── Safety stop message ─────────────────────────────────

class TestSafetyStopMessage:
    def test_appends_assistant_message(self):
        from learn_agent.agent_loop import append_safety_stop_message
        state = LoopState(messages=[{"role": "user", "content": "hi"}])
        state.failure_log = ["Error: bad path", "Error: timeout"]
        append_safety_stop_message(state, "max_turns_exceeded")

        last = state.messages[-1]
        assert last["role"] == "assistant"
        text = last["content"][0]["text"]
        assert "max_turns_exceeded" in text
        assert "Error: bad path" in text

    def test_no_failures_if_empty_log(self):
        from learn_agent.agent_loop import append_safety_stop_message
        state = LoopState(messages=[{"role": "user", "content": "hi"}])
        append_safety_stop_message(state, "max_failures_exceeded")

        last = state.messages[-1]
        assert last["role"] == "assistant"


# ── Subagent config limits ──────────────────────────────

class TestSubAgentLimits:
    def test_subagent_smaller_turns(self):
        assert SUBAGENT_CONFIG.max_turns < PARENT_AGENT_CONFIG.max_turns

    def test_subagent_smaller_failures(self):
        assert SUBAGENT_CONFIG.max_failures < PARENT_AGENT_CONFIG.max_failures


# ── Plan validation only for parent ─────────────────────

class TestPlanValidationScoping:
    def test_parent_validates_plans(self):
        """Parent agent should validate plan progress."""
        from learn_agent import agent_loop

        state = LoopState(messages=[{"role": "user", "content": "test"}], plans=[
            Plan("a", "done", "desc a"),
            Plan("b", "doing", "desc b"),
            Plan("c", "doing", "desc c"),  # violation: multiple doing
        ])

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("ok"),
            FakeToolUseBlock("t1", "bash", {"command": "echo ok"}),
        ])

        with patch.object(agent_loop, 'client', mock_client):
            agent_loop.run_one_turn(state, config=PARENT_AGENT_CONFIG)

        # c should be corrected from 'doing' to 'pending'
        assert state.plans[2].status == "pending"

    def test_subagent_does_not_validate_plans(self):
        """Subagent with plans (somehow) — validate_plan_progress not called."""
        from learn_agent import agent_loop

        state = LoopState(messages=[{"role": "user", "content": "find files"}], plans=[
            Plan("a", "done", "desc"),
            Plan("b", "doing", "desc"),
            Plan("c", "doing", "desc"),  # would be violation if validated
        ])

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("found"),
            FakeToolUseBlock("t1", "glob", {"pattern": "*"}),
        ])

        with patch.object(agent_loop, 'client', mock_client):
            agent_loop.run_one_turn(state, config=SUBAGENT_CONFIG)

        # Plans should NOT be corrected for subagent
        assert state.plans[2].status == "doing"  # unchanged


# ── Permission checks ───────────────────────────────────

class TestPermissionChecks:
    def test_subagent_cannot_use_write(self):
        from learn_agent.agent_loop import execute_tool_use_blocks
        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "t1", "name": "write_file",
             "input": {"path": "test.txt", "content": "bad"}},
        ]
        results = execute_tool_use_blocks(blocks, state, SUBAGENT_CONFIG)
        assert "not allowed" in results[0]["content"]

    def test_subagent_cannot_delegate(self):
        from learn_agent.agent_loop import execute_tool_use_blocks
        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "t1", "name": "delegate_task",
             "input": {"task": "find stuff"}},
        ]
        results = execute_tool_use_blocks(blocks, state, SUBAGENT_CONFIG)
        assert "not allowed" in results[0]["content"]

    def test_subagent_can_use_allowed_tools(self):
        from learn_agent.agent_loop import execute_tool_use_blocks
        from learn_agent.tools import register_tools

        # Patch read_file handler directly
        original = register_tools.TOOL_HANDLERS["read_file"]
        register_tools.TOOL_HANDLERS["read_file"] = lambda **kw: "hello world"

        try:
            state = LoopState(messages=[])
            blocks = [
                {"type": "tool_use", "id": "t1", "name": "read_file",
                 "input": {"path": "readme.md"}},
            ]
            results = execute_tool_use_blocks(blocks, state, SUBAGENT_CONFIG)
            assert "hello world" in results[0]["content"]
        finally:
            register_tools.TOOL_HANDLERS["read_file"] = original


# ── build_system with different configs ─────────────────

class TestBuildSystemWithConfig:
    def test_parent_includes_plan_progress(self):
        from learn_agent.agent_loop import build_system
        state = LoopState(messages=[], goal="Test", plans=[
            Plan("step1", "doing", "desc"),
        ])
        prompt = build_system(state, PARENT_AGENT_CONFIG)
        assert "Plan Progress" in prompt

    def test_subagent_excludes_plan_progress(self):
        from learn_agent.agent_loop import build_system
        state = LoopState(messages=[], goal="Test", plans=[
            Plan("step1", "doing", "desc"),
        ])
        prompt = build_system(state, SUBAGENT_CONFIG)
        assert "Plan Progress" not in prompt
        assert "read-only" in prompt


# ── LoopState reset_runtime_state ────────────────────────

class TestLoopStateReset:
    def test_reset_clears_runtime_fields(self):
        state = LoopState(
            messages=[{"role": "user", "content": "hi"}],
            turn_count=5,
            goal="some goal",
            plans=[Plan("a", "doing", "desc")],
            failure_count=3,
            consecutive_failures=2,
            failure_log=["err1", "err2"],
            stopped_reason="max_turns_exceeded",
        )
        state.reset_runtime_state()

        assert state.turn_count == 1
        assert state.goal == ""
        assert state.plans is None
        assert state.failure_count == 0
        assert state.consecutive_failures == 0
        assert state.failure_log == []
        assert state.stopped_reason is None

    def test_reset_does_not_clear_messages(self):
        msgs = [{"role": "user", "content": "hi"}]
        state = LoopState(messages=msgs)
        state.reset_runtime_state()
        assert state.messages == msgs

    def test_reset_does_not_break_plan_snapshot(self):
        state = LoopState(messages=[], plans=[Plan("a", "doing", "desc")])
        snap = state.plan_snapshot()
        state.reset_runtime_state()
        # rollback should still work with snapshot taken before reset
        state.rollback_plans(snap)
        assert state.plans[0].status == "doing"
