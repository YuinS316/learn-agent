import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from learn_agent.utils.extract_text import extract_text


class TestExtractText:
    def test_string_content(self):
        assert extract_text("hello world") == "hello world"

    def test_empty_string(self):
        assert extract_text("") == ""

    def test_list_with_text_blocks(self):
        content = [
            {"type": "text", "text": "line one"},
            {"type": "text", "text": "line two"},
        ]
        assert extract_text(content) == "line one\nline two"

    def test_list_with_mixed_blocks(self):
        content = [
            {"type": "text", "text": "I'll check files"},
            {"type": "tool_use", "id": "call_1", "name": "bash", "input": {"command": "ls"}},
            {"type": "text", "text": "Done"},
        ]
        assert extract_text(content) == "I'll check files\nDone"

    def test_list_with_only_tool_use(self):
        content = [
            {"type": "tool_use", "id": "call_1", "name": "bash", "input": {"command": "ls"}},
        ]
        assert extract_text(content) == ""

    def test_empty_list(self):
        assert extract_text([]) == ""

    def test_none_content(self):
        """Should handle None gracefully (return empty string)."""
        assert extract_text(None) == ""

    def test_dict_without_type_key(self):
        content = [{"foo": "bar"}]
        result = extract_text(content)
        assert result == ""

    def test_non_string_non_list(self):
        assert extract_text(42) == ""
