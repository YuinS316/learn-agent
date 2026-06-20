import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import MagicMock, patch

from learn_agent.loop_state import LoopState
from learn_agent.agent_config import PARENT_AGENT_CONFIG, SUBAGENT_CONFIG
from learn_agent.hook_system import HookStage, HookContext, hook_registry


# ── Helpers ───────────────────────────────────────────────────

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


# ── Teardown after every test ──────────────────────────────────

@pytest.fixture(autouse=True)
def clear_hooks():
    hook_registry.clear()
    yield
    hook_registry.clear()


# ═══════════════════════════════════════════════════════════════
# HookRegistry unit tests
# ═══════════════════════════════════════════════════════════════

class TestHookRegistry:
    """Tests for the singleton HookRegistry: register, fire, priority, errors."""

    def test_register_and_fire_in_priority_order(self):
        calls = []

        def first(ctx): calls.append(1); return None
        def second(ctx): calls.append(2); return None

        hook_registry.register(HookStage.POST_TOOL_USE, second, priority=20)
        hook_registry.register(HookStage.POST_TOOL_USE, first, priority=10)

        state = LoopState(messages=[])
        ctx = HookContext(stage=HookStage.POST_TOOL_USE, state=state,
                          config=PARENT_AGENT_CONFIG, data={})
        hook_registry.fire(HookStage.POST_TOOL_USE, ctx)

        assert calls == [1, 2], f"Expected [1, 2] (priority order), got {calls}"

    def test_context_modification_propagates(self):
        def modifier(ctx):
            ctx.data["step_a"] = True
            return ctx

        def reader(ctx):
            assert ctx.data.get("step_a") is True
            ctx.data["step_b"] = True
            return ctx

        hook_registry.register(HookStage.POST_TOOL_USE, modifier, priority=10)
        hook_registry.register(HookStage.POST_TOOL_USE, reader, priority=20)

        state = LoopState(messages=[])
        ctx = HookContext(stage=HookStage.POST_TOOL_USE, state=state,
                          config=PARENT_AGENT_CONFIG, data={})
        result = hook_registry.fire(HookStage.POST_TOOL_USE, ctx)
        assert isinstance(result, HookContext)
        assert result.data.get("step_a") is True
        assert result.data.get("step_b") is True

    def test_pre_tool_use_abort_returns_false(self):
        def blocker(ctx):
            return False

        hook_registry.register(HookStage.PRE_TOOL_USE, blocker)

        state = LoopState(messages=[])
        ctx = HookContext(stage=HookStage.PRE_TOOL_USE, state=state,
                          config=PARENT_AGENT_CONFIG, data={})
        result = hook_registry.fire(HookStage.PRE_TOOL_USE, ctx)
        assert result is False

    def test_hook_exception_is_swallowed_non_critical(self):
        def broken(ctx):
            raise RuntimeError("boom")

        hook_registry.register(HookStage.STOP, broken, critical=False)

        state = LoopState(messages=[])
        ctx = HookContext(stage=HookStage.STOP, state=state,
                          config=PARENT_AGENT_CONFIG, data={"reason": "test"})
        result = hook_registry.fire(HookStage.STOP, ctx)
        # Should not raise; should return the context unchanged
        assert isinstance(result, HookContext)

    def test_critical_hook_exception_propagates(self):
        def broken(ctx):
            raise RuntimeError("critical boom")

        hook_registry.register(HookStage.STOP, broken, critical=True)

        state = LoopState(messages=[])
        ctx = HookContext(stage=HookStage.STOP, state=state,
                          config=PARENT_AGENT_CONFIG, data={"reason": "test"})
        with pytest.raises(RuntimeError, match="critical boom"):
            hook_registry.fire(HookStage.STOP, ctx)

    def test_hook_after_critical_does_not_run(self):
        calls = []

        def broken(ctx):
            raise RuntimeError("fail")

        def after(ctx):
            calls.append("after")
            return None

        hook_registry.register(HookStage.STOP, broken, priority=10, critical=True)
        hook_registry.register(HookStage.STOP, after, priority=20)

        state = LoopState(messages=[])
        ctx = HookContext(stage=HookStage.STOP, state=state,
                          config=PARENT_AGENT_CONFIG, data={"reason": "test"})
        with pytest.raises(RuntimeError):
            hook_registry.fire(HookStage.STOP, ctx)
        assert calls == [], "hooks after a critical failure should not run"

    def test_count_by_stage_and_total(self):
        def noop(ctx): return None

        hook_registry.register(HookStage.PRE_TOOL_USE, noop)
        hook_registry.register(HookStage.POST_TOOL_USE, noop)
        hook_registry.register(HookStage.POST_TOOL_USE, noop, priority=200)
        hook_registry.register(HookStage.STOP, noop)

        assert hook_registry.count(HookStage.PRE_TOOL_USE) == 1
        assert hook_registry.count(HookStage.POST_TOOL_USE) == 2
        assert hook_registry.count(HookStage.STOP) == 1
        assert hook_registry.count(HookStage.SUBAGENT_START) == 0
        assert hook_registry.count() == 4

    def test_clear_removes_all(self):
        def noop(ctx): return None
        hook_registry.register(HookStage.PRE_TOOL_USE, noop)
        hook_registry.register(HookStage.STOP, noop)
        assert hook_registry.count() == 2

        hook_registry.clear()
        assert hook_registry.count() == 0

    def test_singleton_same_instance(self):
        from learn_agent.hook_system import hook_registry as hr2
        from learn_agent.hook_system import HookRegistry
        hr3 = HookRegistry.get()
        assert hook_registry is hr2 is hr3


# ═══════════════════════════════════════════════════════════════
# Hook integration: PRE_TOOL_USE / POST_TOOL_USE in agent loop
# ═══════════════════════════════════════════════════════════════

class TestPreToolUseHook:
    """PRE_TOOL_USE fires before tool handler and can abort or modify input."""

    def test_pre_tool_use_fires_before_handler(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        trace = []

        def tracer(ctx):
            trace.append(("pre", ctx.data["tool_name"]))
            return None

        hook_registry.register(HookStage.PRE_TOOL_USE, tracer, priority=10)

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "c1", "name": "bash",
             "input": {"command": "echo hello"}},
        ]
        execute_tool_use_blocks(blocks, state, PARENT_AGENT_CONFIG)

        assert ("pre", "bash") in trace

    def test_pre_tool_use_block_returns_error_result(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        def blocker(ctx):
            return False

        hook_registry.register(HookStage.PRE_TOOL_USE, blocker)

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "c1", "name": "bash",
             "input": {"command": "echo hello"}},
        ]
        results = execute_tool_use_blocks(blocks, state, PARENT_AGENT_CONFIG)
        assert len(results) == 1
        assert results[0]["type"] == "tool_result"
        assert "PreToolUse hook" in results[0]["content"]
        assert "blocked" in results[0]["content"].lower()

    def test_pre_tool_use_modifies_input(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        def modifier(ctx):
            ctx.data["tool_input"]["command"] = "echo modified"
            return ctx

        hook_registry.register(HookStage.PRE_TOOL_USE, modifier)

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "c1", "name": "bash",
             "input": {"command": "echo original"}},
        ]
        results = execute_tool_use_blocks(blocks, state, PARENT_AGENT_CONFIG)
        assert "modified" in results[0]["content"]
        assert "original" not in results[0]["content"]

    def test_pre_tool_use_sees_config_role(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        seen_roles = []

        def role_tracer(ctx):
            seen_roles.append(ctx.config.role)
            return None

        hook_registry.register(HookStage.PRE_TOOL_USE, role_tracer)

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "c1", "name": "glob",
             "input": {"pattern": "*.py"}},
        ]
        execute_tool_use_blocks(blocks, state, SUBAGENT_CONFIG)
        assert seen_roles == ["subagent"]


class TestPostToolUseHook:
    """POST_TOOL_USE fires after tool handler + L1, can modify result."""

    def test_post_tool_use_fires_after_handler(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        trace = []

        def tracer(ctx):
            trace.append(("post", ctx.data["tool_name"]))
            return None

        hook_registry.register(HookStage.POST_TOOL_USE, tracer)

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "c1", "name": "bash",
             "input": {"command": "echo hello"}},
        ]
        execute_tool_use_blocks(blocks, state, PARENT_AGENT_CONFIG)

        assert ("post", "bash") in trace

    def test_post_tool_use_modifies_result(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        def modifier(ctx):
            ctx.data["result"] = "[HOOK MODIFIED] " + ctx.data["result"]
            return ctx

        hook_registry.register(HookStage.POST_TOOL_USE, modifier)

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "c1", "name": "bash",
             "input": {"command": "echo hello"}},
        ]
        results = execute_tool_use_blocks(blocks, state, PARENT_AGENT_CONFIG)
        assert results[0]["content"].startswith("[HOOK MODIFIED]")

    def test_post_tool_use_sees_actual_result(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        seen = []

        def checker(ctx):
            seen.append(ctx.data.get("result", ""))
            return None

        hook_registry.register(HookStage.POST_TOOL_USE, checker)

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "c1", "name": "bash",
             "input": {"command": "echo hello"}},
        ]
        execute_tool_use_blocks(blocks, state, PARENT_AGENT_CONFIG)
        assert len(seen) == 1
        assert "hello" in seen[0]

    def test_post_tool_use_execution_order_pre_post(self):
        """Verify PRE fires before POST for the same tool call."""
        from learn_agent.agent_loop import execute_tool_use_blocks

        order = []

        def pre(ctx):
            order.append(("pre", ctx.data["tool_name"]))
            return None

        def post(ctx):
            order.append(("post", ctx.data["tool_name"]))
            return None

        hook_registry.register(HookStage.PRE_TOOL_USE, pre, priority=10)
        hook_registry.register(HookStage.POST_TOOL_USE, post, priority=10)

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "t1", "name": "bash",
             "input": {"command": "echo a"}},
            {"type": "tool_use", "id": "t2", "name": "bash",
             "input": {"command": "echo b"}},
        ]
        execute_tool_use_blocks(blocks, state, PARENT_AGENT_CONFIG)

        assert order == [
            ("pre", "bash"), ("post", "bash"),
            ("pre", "bash"), ("post", "bash"),
        ]


# ═══════════════════════════════════════════════════════════════
# STOP hook: unified exit point
# ═══════════════════════════════════════════════════════════════

class TestStopHook:
    """STOP hook fires on all exit paths (normal, max_turns, max_failures)."""

    def test_stop_normal_exit(self):
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("done"),
        ])

        stop_data = []

        def stop_hook(ctx):
            stop_data.append(ctx.data["reason"])
            return None

        hook_registry.register(HookStage.STOP, stop_hook)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "hello"}])
            agent_loop.agent_loop(state)

        assert stop_data == ["normal"]

    def test_stop_max_turns_exceeded(self):
        from learn_agent import agent_loop
        from learn_agent.config.settings import settings

        # Always return tool_use so loop never exits normally. Provide one
        # more response than max_turns so run_one_turn never starves.
        n = settings.PARENT_MAX_TURNS + 5
        responses = [
            FakeResponse([FakeToolUseBlock(f"t{i}", "bash", {"command": "echo ok"})])
            for i in range(n)
        ]
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = responses

        stop_data = []

        def stop_hook(ctx):
            stop_data.append(ctx.data["reason"])
            return None

        hook_registry.register(HookStage.STOP, stop_hook)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "task"}])
            agent_loop.agent_loop(state)

        assert "max_turns" in stop_data[0]

    def test_stop_max_failures_exceeded(self):
        from learn_agent import agent_loop

        # Model tries to use an unknown tool repeatedly to trigger failures
        responses = [
            FakeResponse([FakeToolUseBlock(f"t{i}", "nonexistent_tool", {})])
            for i in range(10)
        ]
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = responses

        stop_data = []

        def stop_hook(ctx):
            stop_data.append(ctx.data["reason"])
            return None

        hook_registry.register(HookStage.STOP, stop_hook)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "task"}])
            agent_loop.agent_loop(state)

        assert "max_failures" in stop_data[0]

    def test_stop_hook_can_read_state(self):
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("done"),
        ])

        captured_turns = []

        def stop_hook(ctx):
            captured_turns.append(ctx.state.turn_count)
            return None

        hook_registry.register(HookStage.STOP, stop_hook)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "hello"}])
            agent_loop.agent_loop(state)

        assert captured_turns[0] >= 1


# ═══════════════════════════════════════════════════════════════
# SUBAGENT_START / SUBAGENT_STOP hooks
# ═══════════════════════════════════════════════════════════════

class TestSubagentHooks:
    """SUBAGENT_START / STOP fire around delegate_task subagent dispatch."""

    def test_subagent_start_fires_before_loop(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("subagent findings"),
        ])

        start_calls = []

        def start_hook(ctx):
            start_calls.append(ctx.data.get("task"))
            return None

        hook_registry.register(HookStage.SUBAGENT_START, start_hook)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[])
            run_delegate_task(state, task="Find all Python files")

        assert len(start_calls) == 1
        assert "Find all Python files" in start_calls[0]

    def test_subagent_start_can_modify_task(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("findings for modified task"),
        ])

        def modifier(ctx):
            ctx.data["task"] = "MODIFIED: " + ctx.data["task"]
            return ctx

        hook_registry.register(HookStage.SUBAGENT_START, modifier)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[])
            result = run_delegate_task(state, task="original task")

        # The subagent message should contain the modified task
        assert "findings for modified task" in result.lower()

    def test_subagent_stop_fires_after_loop(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("result text"),
        ])

        stop_calls = []

        def stop_hook(ctx):
            stop_calls.append(ctx.data.get("result"))
            return None

        hook_registry.register(HookStage.SUBAGENT_STOP, stop_hook)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[])
            run_delegate_task(state, task="Do research")

        assert len(stop_calls) == 1
        assert "result text" in stop_calls[0]

    def test_subagent_stop_can_modify_result(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("original result"),
        ])

        def modifier(ctx):
            ctx.data["result"] = "[AUDITED] " + ctx.data.get("result", "")
            return ctx

        hook_registry.register(HookStage.SUBAGENT_STOP, modifier)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[])
            result = run_delegate_task(state, task="Research")

        assert result.startswith("[AUDITED]")

    def test_subagent_start_sees_parent_state(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("findings"),
        ])

        captured_parent_msgs = []

        def start_hook(ctx):
            captured_parent_msgs.append(len(ctx.state.messages))
            return None

        hook_registry.register(HookStage.SUBAGENT_START, start_hook)

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[
                {"role": "user", "content": "parent task"},
                {"role": "assistant", "content": "let me delegate"},
            ])
            run_delegate_task(state, task="Research")

        # The parent state at SUBAGENT_START should have the parent's messages
        assert captured_parent_msgs[0] >= 2


# ═══════════════════════════════════════════════════════════════
# Global / cross-agent hook behavior
# ═══════════════════════════════════════════════════════════════

class TestGlobalHooks:
    """Hooks are global: they fire for both parent AND subagent."""

    def test_pre_tool_use_fires_for_subagent_too(self):
        """When a subagent runs, PRE_TOOL_USE hooks registered globally should fire."""
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        pre_calls = []

        def global_pre(ctx):
            pre_calls.append(ctx.config.role)
            return None

        hook_registry.register(HookStage.PRE_TOOL_USE, global_pre)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeToolUseBlock("t1", "glob", {"pattern": "*.py"}),
        ])

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[])
            run_delegate_task(state, task="Find files")

        assert "subagent" in pre_calls

    def test_stop_fires_for_subagent_too(self):
        """When a subagent exits, STOP hook should also fire."""
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        stop_roles = []

        def global_stop(ctx):
            stop_roles.append(ctx.config.role)
            return None

        hook_registry.register(HookStage.STOP, global_stop)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("done"),
        ])

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[])
            run_delegate_task(state, task="Query")

        assert "subagent" in stop_roles

    def test_config_role_correct_for_parent_vs_subagent(self):
        """Verify ctx.config.role is 'parent' in main loop and 'subagent' in delegate."""
        from learn_agent import agent_loop
        from learn_agent.tools.run_delegate_task import run_delegate_task

        pre_roles = []

        def role_tracker(ctx):
            pre_roles.append(ctx.config.role)
            return None

        hook_registry.register(HookStage.PRE_TOOL_USE, role_tracker)

        # Run parent agent: should produce "parent" roles
        mock_client_p = MagicMock()
        mock_client_p.messages.create.return_value = FakeResponse([
            FakeToolUseBlock("t1", "bash", {"command": "echo p"}),
        ])

        with patch.object(agent_loop, 'client', mock_client_p):
            parent_state = LoopState(messages=[{"role": "user", "content": "parent task"}])
            agent_loop.agent_loop(parent_state, config=PARENT_AGENT_CONFIG)

        assert "parent" in pre_roles

        # Run subagent via delegate_task: should also produce "subagent" roles
        sub_roles_before = len(pre_roles)

        mock_client_s = MagicMock()
        mock_client_s.messages.create.return_value = FakeResponse([
            FakeToolUseBlock("t1", "glob", {"pattern": "*.py"}),
        ])

        with patch.object(agent_loop, 'client', mock_client_s):
            state = LoopState(messages=[])
            run_delegate_task(state, task="Sub research")

        assert "subagent" in pre_roles[sub_roles_before:]
