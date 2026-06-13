import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import MagicMock, patch
from learn_agent.loop_state import LoopState
from learn_agent.agent_config import SUBAGENT_CONFIG


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


class TestRunDelegateTask:
    def test_empty_task_rejected(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        state = LoopState(messages=[])
        result = run_delegate_task(state, task="   ")
        assert "Error" in result

    def test_subagent_runs_and_returns_findings(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        # Mock the Anthropic client so subagent returns text
        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("Found 3 files: a.py, b.py, c.py"),
        ])

        state = LoopState(messages=[])
        with patch.object(agent_loop, 'client', mock_client):
            result = run_delegate_task(
                state,
                task="Find all Python files",
                context="Looking for source code",
                relevant_paths=["src/"],
                output_format="bullet list",
            )

        assert "Found 3 files" in result

    def test_subagent_stopped_reason_returned(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop
        from learn_agent.tools import register_tools

        # Simulate max_turns exceeded by making model always return tool_use.
        # SUBAGENT_CONFIG.max_turns == 6, so provide 6 tool_use responses then a text.
        many_responses = [
            FakeResponse([FakeToolUseBlock(f"t{i}", "glob", {"pattern": "*.py"})])
            for i in range(6)
        ] + [FakeResponse([FakeTextBlock("final")])]
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = many_responses

        # Patch glob to return success (not an error)
        original = register_tools.TOOL_HANDLERS["glob"]
        register_tools.TOOL_HANDLERS["glob"] = lambda **kw: "a.py\nb.py"

        try:
            state = LoopState(messages=[])
            with patch.object(agent_loop, 'client', mock_client):
                result = run_delegate_task(
                    state,
                    task="Search exhaustively",
                )

            assert "Subagent stopped" in result or "max_turns" in str(result).lower()
        finally:
            register_tools.TOOL_HANDLERS["glob"] = original

    def test_passes_context_to_subagent(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("analysis result"),
        ])

        state = LoopState(messages=[])
        with patch.object(agent_loop, 'client', mock_client):
            run_delegate_task(
                state,
                task="Analyze code",
                context="This project uses Flask",
                relevant_paths=["app.py"],
                output_format="summary",
            )

        # Check the subagent received proper context
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        user_content = messages[0]["content"]
        assert "Analyze code" in user_content
        assert "Flask" in user_content
        assert "app.py" in user_content
        assert "summary" in user_content

    def test_default_context_shows_none(self):
        from learn_agent.tools.run_delegate_task import run_delegate_task
        from learn_agent import agent_loop

        mock_client = MagicMock()
        mock_client.messages.create.return_value = FakeResponse([
            FakeTextBlock("ok"),
        ])

        state = LoopState(messages=[])
        with patch.object(agent_loop, 'client', mock_client):
            run_delegate_task(state, task="Do research")

        messages = mock_client.messages.create.call_args.kwargs["messages"]
        assert "(none)" in messages[0]["content"]  # default context
        assert "(none)" in messages[0]["content"]  # default paths
