import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import MagicMock, patch, call
from learn_agent.loop_state import LoopState


# ── Helpers to simulate Anthropic response blocks ─────────

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


# ── execute_tool_use_blocks tests ────────────────────────

class TestExecuteToolUseBlocks:
    def test_executes_known_tool(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "call_1", "name": "bash",
             "input": {"command": "echo hello"}},
        ]
        results = execute_tool_use_blocks(blocks, state)
        assert len(results) == 1
        assert results[0]["type"] == "tool_result"
        assert results[0]["tool_use_id"] == "call_1"
        assert "hello" in results[0]["content"]

    def test_unknown_tool_returns_error(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "call_x", "name": "nonexistent_tool",
             "input": {}},
        ]
        results = execute_tool_use_blocks(blocks, state)
        assert len(results) == 1
        assert "unknown tool" in results[0]["content"].lower()

    def test_multiple_tools_executed(self):
        from learn_agent.agent_loop import execute_tool_use_blocks

        state = LoopState(messages=[])
        blocks = [
            {"type": "tool_use", "id": "c1", "name": "bash",
             "input": {"command": "echo a"}},
            {"type": "tool_use", "id": "c2", "name": "bash",
             "input": {"command": "echo b"}},
        ]
        results = execute_tool_use_blocks(blocks, state)
        assert len(results) == 2
        assert results[0]["tool_use_id"] == "c1"
        assert results[1]["tool_use_id"] == "c2"


# ── run_one_turn tests (mocked Anthropic client) ─────────

class TestRunOneTurn:
    def test_text_only_ends_loop(self):
        """When model returns only text (no tool_use), should return False."""
        from learn_agent import agent_loop

        fake_response = FakeResponse([FakeTextBlock("Here is the answer.")])
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "hello"}])
            result = agent_loop.run_one_turn(state)

        assert result is False
        # Should have stored the assistant message
        last_msg = state.messages[-1]
        assert last_msg["role"] == "assistant"
        assert last_msg["content"][0]["type"] == "text"
        assert last_msg["content"][0]["text"] == "Here is the answer."

    def test_tool_use_continues_loop(self):
        """When model returns tool_use blocks, should return True."""
        from learn_agent import agent_loop

        fake_response = FakeResponse([
            FakeTextBlock("Let me check..."),
            FakeToolUseBlock("call_1", "bash", {"command": "echo test"}),
        ])
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "run a command"}])
            result = agent_loop.run_one_turn(state)

        assert result is True
        assert state.turn_count == 2  # incremented
        assert state.transition_reason == "tool_result"

        # Check assistant message was stored
        assistant = state.messages[-2]  # second to last (last is tool result user msg)
        assert assistant["role"] == "assistant"
        assert any(b["type"] == "tool_use" for b in assistant["content"])

        # Check tool result was stored as user message
        tool_result_msg = state.messages[-1]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"

    def test_tool_use_only_no_text(self):
        """Model returns only tool_use blocks (no text prefix)."""
        from learn_agent import agent_loop

        fake_response = FakeResponse([
            FakeToolUseBlock("call_2", "bash", {"command": "ls"}),
        ])
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "list files"}])
            result = agent_loop.run_one_turn(state)

        assert result is True
        assistant = state.messages[-2]
        # Content should have the tool_use block
        assert len(assistant["content"]) == 1
        assert assistant["content"][0]["type"] == "tool_use"

    def test_api_call_uses_correct_parameters(self):
        """Verify the Anthropic API is called with the right arguments."""
        from learn_agent import agent_loop

        fake_response = FakeResponse([FakeTextBlock("ok")])
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "hi"}])
            agent_loop.run_one_turn(state)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "model" in call_kwargs
        assert call_kwargs["max_tokens"] == 8000
        # System prompt is dynamically built; verify BASE_SYSTEM content is in there
        system_prompt = call_kwargs["system"]
        assert "coding agent" in system_prompt
        assert "create_plan" in system_prompt
        # Messages passed to API are normalize_messages(state.messages),
        # which is a cleaned copy — just verify the user query is in there
        assert call_kwargs["messages"][0]["role"] == "user"
        assert call_kwargs["messages"][0]["content"] == "hi"
        assert call_kwargs["tools"] is not None


# ── agent_loop integration tests ─────────────────────────

class TestAgentLoop:
    def test_single_turn_ends(self):
        """agent_loop should run one turn and exit when model has no tool calls."""
        from learn_agent import agent_loop

        fake_response = FakeResponse([FakeTextBlock("done")])
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "hello"}])
            agent_loop.agent_loop(state)

        # Should have made exactly 1 API call
        assert mock_client.messages.create.call_count == 1

    def test_multi_turn_ends(self):
        """agent_loop runs tool_use → tool_result → text → exit."""
        from learn_agent import agent_loop

        # First response: tool_use (continues)
        # Second response: text only (ends)
        responses = [
            FakeResponse([
                FakeTextBlock("Checking..."),
                FakeToolUseBlock("t1", "bash", {"command": "echo ok"}),
            ]),
            FakeResponse([FakeTextBlock("Command completed successfully.")]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = responses

        with patch.object(agent_loop, 'client', mock_client):
            state = LoopState(messages=[{"role": "user", "content": "run echo"}])
            agent_loop.agent_loop(state)

        assert mock_client.messages.create.call_count == 2
        # Final message should be the assistant's text response
        assert state.messages[-1]["role"] == "assistant"
        assert state.messages[-1]["content"][0]["text"] == "Command completed successfully."
