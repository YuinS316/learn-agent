import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from learn_agent.loop_state import LoopState


class TestLoopState:
    def test_default_values(self):
        state = LoopState(messages=[])
        assert state.messages == []
        assert state.turn_count == 1
        assert state.transition_reason is None

    def test_custom_values(self):
        msgs = [{"role": "user", "content": "hello"}]
        state = LoopState(messages=msgs, turn_count=5, transition_reason="tool_result")
        assert state.messages == msgs
        assert state.turn_count == 5
        assert state.transition_reason == "tool_result"

    def test_messages_are_mutable(self):
        """The messages list should be the same object (mutable reference)."""
        msgs = []
        state = LoopState(messages=msgs)
        msgs.append({"role": "user", "content": "hi"})
        assert state.messages == [{"role": "user", "content": "hi"}]

    def test_turn_count_increment(self):
        state = LoopState(messages=[])
        state.turn_count += 1
        assert state.turn_count == 2
