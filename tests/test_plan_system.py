import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import MagicMock, patch
from learn_agent.loop_state import LoopState, Plan


# ── _compute_correct_plans tests ─────────────────────────

class TestComputeCorrectPlans:
    def test_all_pending_stays_pending(self):
        from learn_agent.agent_loop import _compute_correct_plans
        plans = [
            Plan("a", "pending", "desc a"),
            Plan("b", "pending", "desc b"),
        ]
        result = _compute_correct_plans(plans)
        assert result == ["pending", "pending"]

    def test_done_pending_ordering(self):
        from learn_agent.agent_loop import _compute_correct_plans
        plans = [
            Plan("a", "done", "desc a"),
            Plan("b", "pending", "desc b"),
        ]
        result = _compute_correct_plans(plans)
        assert result == ["done", "pending"]

    def test_done_doing_pending_correct(self):
        from learn_agent.agent_loop import _compute_correct_plans
        plans = [
            Plan("a", "done", "desc a"),
            Plan("b", "doing", "desc b"),
            Plan("c", "pending", "desc c"),
        ]
        result = _compute_correct_plans(plans)
        assert result == ["done", "doing", "pending"]

    def test_interleaved_done_after_doing_corrected(self):
        """done → doing → done → pending: should correct the interleaving."""
        from learn_agent.agent_loop import _compute_correct_plans
        plans = [
            Plan("a", "done", "desc a"),
            Plan("b", "doing", "desc b"),
            Plan("c", "done", "desc c"),  # interleaved violation
            Plan("d", "pending", "desc d"),
        ]
        result = _compute_correct_plans(plans)
        assert result == ["done", "doing", "pending", "pending"]

    def test_two_doings_corrected(self):
        from learn_agent.agent_loop import _compute_correct_plans
        plans = [
            Plan("a", "done", "desc a"),
            Plan("b", "doing", "desc b"),
            Plan("c", "doing", "desc c"),  # multiple doing
        ]
        result = _compute_correct_plans(plans)
        assert result == ["done", "doing", "pending"]

    def test_pending_before_done_corrected(self):
        """pending → done: invalid ordering, correct it."""
        from learn_agent.agent_loop import _compute_correct_plans
        plans = [
            Plan("a", "pending", "desc a"),
            Plan("b", "done", "desc b"),
        ]
        result = _compute_correct_plans(plans)
        assert result == ["pending", "pending"]

    def test_all_done_stays_done(self):
        from learn_agent.agent_loop import _compute_correct_plans
        plans = [
            Plan("a", "done", "desc a"),
            Plan("b", "done", "desc b"),
            Plan("c", "done", "desc c"),
        ]
        result = _compute_correct_plans(plans)
        # All done is a valid terminal state — all steps completed.
        # The algorithm scans: all "done", not doing_found → last_done = n-1
        # Then correction sets [0..n-1] as "done". No violation.
        assert result == ["done", "done", "done"]

    def test_doing_first_without_done_prefix(self):
        """No done prefix, just doing → pending... → valid start."""
        from learn_agent.agent_loop import _compute_correct_plans
        plans = [
            Plan("a", "doing", "desc a"),
            Plan("b", "pending", "desc b"),
        ]
        result = _compute_correct_plans(plans)
        # The first plan set as 'doing' is valid (starts the prefix)
        assert result == ["doing", "pending"]


# ── validate_plan_progress tests ─────────────────────────

class TestValidatePlanProgress:
    def test_no_plans_returns_none(self):
        from learn_agent.agent_loop import validate_plan_progress
        state = LoopState(messages=[], plans=None)
        assert validate_plan_progress(state) is None

    def test_valid_sequence_no_violation(self):
        from learn_agent.agent_loop import validate_plan_progress
        state = LoopState(messages=[], plans=[
            Plan("a", "done", "desc a"),
            Plan("b", "doing", "desc b"),
            Plan("c", "pending", "desc c"),
        ])
        assert validate_plan_progress(state) is None
        # Statuses should remain unchanged
        assert state.plans[0].status == "done"
        assert state.plans[1].status == "doing"
        assert state.plans[2].status == "pending"

    def test_two_doings_violation_corrected(self):
        from learn_agent.agent_loop import validate_plan_progress
        state = LoopState(messages=[], plans=[
            Plan("a", "done", "desc a"),
            Plan("b", "doing", "desc b"),
            Plan("c", "doing", "desc c"),
        ])
        msg = validate_plan_progress(state)
        assert msg is not None
        assert "violation" in msg.lower()
        # Should be corrected
        assert state.plans[2].status == "pending"

    def test_done_after_doing_violation(self):
        from learn_agent.agent_loop import validate_plan_progress
        state = LoopState(messages=[], plans=[
            Plan("a", "done", "desc a"),
            Plan("b", "doing", "desc b"),
            Plan("c", "done", "desc c"),  # violation
            Plan("d", "pending", "desc d"),
        ])
        msg = validate_plan_progress(state)
        assert msg is not None
        assert state.plans[2].status == "pending"
        assert state.plans[3].status == "pending"

    def test_pending_then_done_violation(self):
        from learn_agent.agent_loop import validate_plan_progress
        state = LoopState(messages=[], plans=[
            Plan("a", "pending", "desc a"),
            Plan("b", "done", "desc b"),
        ])
        msg = validate_plan_progress(state)
        assert msg is not None
        # All should be reset to pending
        assert state.plans[1].status == "pending"


# ── build_system tests ───────────────────────────────────

class TestBuildSystem:
    def test_base_without_goal_or_plans(self):
        from learn_agent.agent_loop import build_system
        state = LoopState(messages=[])
        prompt = build_system(state)
        assert "coding agent" in prompt
        assert "Goal" not in prompt
        assert "Plan Progress" not in prompt

    def test_with_goal(self):
        from learn_agent.agent_loop import build_system
        state = LoopState(messages=[], goal="Build a web app")
        prompt = build_system(state)
        assert "Build a web app" in prompt

    def test_with_plans(self):
        from learn_agent.agent_loop import build_system
        state = LoopState(messages=[], plans=[
            Plan("Step one", "done", "First step description"),
            Plan("Step two", "doing", "Second step description"),
            Plan("Step three", "pending", "Third step description"),
        ])
        prompt = build_system(state)
        assert "Plan Progress" in prompt
        assert "Step one" in prompt
        assert "Step two" in prompt
        assert "Step three" in prompt
        assert "done" in prompt
        assert "doing" in prompt
        assert "pending" in prompt
        assert "only one plan" in prompt.lower()

    def test_unknown_status_uses_fallback_icon(self):
        from learn_agent.agent_loop import build_system
        state = LoopState(messages=[], plans=[
            Plan("bad", "unknown_status", "desc"),
        ])
        prompt = build_system(state)
        assert "❓" in prompt


# ── run_create_plan tests ────────────────────────────────

class TestRunCreatePlan:
    def test_create_valid_plan(self):
        from learn_agent.tools.run_create_plan import run_create_plan
        state = LoopState(messages=[])
        result = run_create_plan(state, goal="Test goal", plans=[
            {"content": "Step 1", "description": "First step"},
            {"content": "Step 2", "description": "Second step"},
        ])
        assert "Plan created" in result
        assert state.goal == "Test goal"
        assert len(state.plans) == 2
        assert state.plans[0].content == "Step 1"
        assert state.plans[0].status == "doing"  # first auto-activated
        assert state.plans[1].status == "pending"

    def test_empty_goal(self):
        from learn_agent.tools.run_create_plan import run_create_plan
        state = LoopState(messages=[])
        result = run_create_plan(state, goal="   ", plans=[
            {"content": "Step", "description": "Desc"},
        ])
        assert "Error" in result
        assert state.goal == ""

    def test_empty_plans(self):
        from learn_agent.tools.run_create_plan import run_create_plan
        state = LoopState(messages=[])
        result = run_create_plan(state, goal="Goal", plans=[])
        assert "Error" in result

    def test_too_many_plans(self):
        from learn_agent.tools.run_create_plan import run_create_plan
        state = LoopState(messages=[])
        many = [{"content": f"Step {i}", "description": f"Desc {i}"} for i in range(11)]
        result = run_create_plan(state, goal="Goal", plans=many)
        assert "too many" in result.lower()

    def test_missing_content_field(self):
        from learn_agent.tools.run_create_plan import run_create_plan
        state = LoopState(messages=[])
        result = run_create_plan(state, goal="Goal", plans=[
            {"description": "Missing content"},
        ])
        assert "missing 'content'" in result.lower()

    def test_missing_description_field(self):
        from learn_agent.tools.run_create_plan import run_create_plan
        state = LoopState(messages=[])
        result = run_create_plan(state, goal="Goal", plans=[
            {"content": "Missing desc"},
        ])
        assert "missing 'description'" in result.lower()

    def test_replaces_existing_plans(self):
        from learn_agent.tools.run_create_plan import run_create_plan
        state = LoopState(messages=[], plans=[
            Plan("old", "doing", "old plan"),
        ])
        run_create_plan(state, goal="New goal", plans=[
            {"content": "New", "description": "new plan"},
        ])
        assert len(state.plans) == 1
        assert state.plans[0].content == "New"


# ── run_update_plan_status tests ─────────────────────────

class TestRunUpdatePlanStatus:
    def test_update_to_done(self):
        from learn_agent.tools.run_update_plan_status import run_update_plan_status
        state = LoopState(messages=[], plans=[
            Plan("a", "doing", "desc a"),
            Plan("b", "pending", "desc b"),
        ])
        result = run_update_plan_status(state, plan_index=0, status="done")
        assert "doing" in result and "done" in result  # old → new: doing → done
        assert state.plans[0].status == "done"

    def test_update_to_doing(self):
        from learn_agent.tools.run_update_plan_status import run_update_plan_status
        state = LoopState(messages=[], plans=[
            Plan("a", "done", "desc a"),
            Plan("b", "pending", "desc b"),
        ])
        result = run_update_plan_status(state, plan_index=1, status="doing")
        assert state.plans[1].status == "doing"

    def test_no_plans_error(self):
        from learn_agent.tools.run_update_plan_status import run_update_plan_status
        state = LoopState(messages=[], plans=None)
        result = run_update_plan_status(state, plan_index=0, status="done")
        assert "no plans exist" in result.lower()

    def test_out_of_range(self):
        from learn_agent.tools.run_update_plan_status import run_update_plan_status
        state = LoopState(messages=[], plans=[
            Plan("a", "doing", "desc a"),
        ])
        result = run_update_plan_status(state, plan_index=5, status="done")
        assert "out of range" in result.lower()

    def test_invalid_status(self):
        from learn_agent.tools.run_update_plan_status import run_update_plan_status
        state = LoopState(messages=[], plans=[
            Plan("a", "doing", "desc a"),
        ])
        result = run_update_plan_status(state, plan_index=0, status="cancelled")
        assert "invalid status" in result.lower()
        # Status should be unchanged
        assert state.plans[0].status == "doing"

    def test_negative_index(self):
        from learn_agent.tools.run_update_plan_status import run_update_plan_status
        state = LoopState(messages=[], plans=[
            Plan("a", "doing", "desc a"),
        ])
        result = run_update_plan_status(state, plan_index=-1, status="done")
        assert "out of range" in result.lower()


# ── LoopState plan helpers ───────────────────────────────

class TestLoopStatePlanHelpers:
    def test_plan_snapshot_deep_copy(self):
        state = LoopState(messages=[], plans=[
            Plan("a", "doing", "desc a"),
        ])
        snapshot = state.plan_snapshot()
        snapshot[0].status = "done"
        # Original should be unchanged
        assert state.plans[0].status == "doing"

    def test_rollback_plans(self):
        state = LoopState(messages=[], plans=[
            Plan("a", "doing", "desc a"),
        ])
        snapshot = state.plan_snapshot()
        state.plans[0].status = "done"
        state.rollback_plans(snapshot)
        assert state.plans[0].status == "doing"

    def test_plan_snapshot_none_plans(self):
        state = LoopState(messages=[], plans=None)
        assert state.plan_snapshot() is None

    def test_rollback_none_plans(self):
        state = LoopState(messages=[], plans=[
            Plan("a", "doing", "desc a"),
        ])
        state.rollback_plans(None)
        # rollback_plans with None should keep existing plans unchanged
        # since `copy.deepcopy(None) if snapshot else None` → None, no change
        assert state.plans is not None  # unchanged because snapshot is None → no-op
