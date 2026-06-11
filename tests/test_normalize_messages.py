import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from learn_agent.utils.normalize_messages import normalize_messages


class TestNormalizeMessages:
    # ── Basic normalization ─────────────────────────────

    def test_string_content_passthrough(self):
        messages = [{"role": "user", "content": "plain text"}]
        result = normalize_messages(messages)
        assert result[0]["content"] == "plain text"

    def test_content_array_passthrough(self):
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "image", "source": "img.png"},
            ]
        }]
        result = normalize_messages(messages)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][0]["text"] == "hello"

    def test_none_content_preserved(self):
        """None content stays as-is (key exists with value None)."""
        messages = [{"role": "assistant", "content": None}]
        result = normalize_messages(messages)
        assert result[0]["content"] is None

    # ── Strip internal metadata fields ─────────────────

    def test_strips_underscore_prefixed_fields(self):
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "visible", "_internal": "secret",
                 "_source": "db", "_timestamp": 12345},
            ]
        }]
        result = normalize_messages(messages)
        block = result[0]["content"][0]
        assert block["text"] == "visible"
        assert "_internal" not in block
        assert "_source" not in block
        assert "_timestamp" not in block

    def test_keeps_non_underscore_fields(self):
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}},
            ]
        }]
        result = normalize_messages(messages)
        block = result[0]["content"][0]
        assert "cache_control" in block

    # ── Orphaned tool_use compensation ────────────────

    def test_missing_tool_result_gets_placeholder(self):
        messages = [
            {"role": "assistant", "content": [
                {"type": "text", "text": "Let me check"},
                {"type": "tool_use", "id": "call_abc", "name": "bash",
                 "input": {"command": "ls"}},
            ]},
        ]
        result = normalize_messages(messages)
        # Should have a tool_result user message appended
        tool_msgs = [m for m in result if m["role"] == "user"
                     and any(b.get("type") == "tool_result" for b in m.get("content", []))]
        assert len(tool_msgs) == 1
        tr_block = tool_msgs[0]["content"][0]
        assert tr_block["tool_use_id"] == "call_abc"
        assert tr_block["content"] == "(cancelled)"

    def test_existing_tool_result_not_duplicated(self):
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "call_1", "name": "bash",
                 "input": {"command": "ls"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "file1.py"},
            ]},
        ]
        result = normalize_messages(messages)
        # Should NOT insert a placeholder (result already exists)
        tool_results = []
        for m in result:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if b.get("type") == "tool_result":
                        tool_results.append(b)
        assert len(tool_results) == 1
        assert tool_results[0]["content"] == "file1.py"  # not "(cancelled)"

    def test_multiple_orphaned_tool_uses(self):
        """Multiple orphaned tool_use blocks → multiple placeholders,
        but consecutive same-role messages get merged in step 3.
        So both tool_result placeholders end up in one user message."""
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "bash",
                 "input": {"command": "a"}},
                {"type": "tool_use", "id": "t2", "name": "bash",
                 "input": {"command": "b"}},
            ]},
        ]
        result = normalize_messages(messages)
        # Both placeholders are consecutive user messages → merged into one
        tool_msgs = [m for m in result if m["role"] == "user"
                     and any(b.get("type") == "tool_result" for b in m.get("content", []))]
        assert len(tool_msgs) == 1
        # But it should contain both tool_result blocks
        tr_blocks = [b for b in tool_msgs[0]["content"] if b.get("type") == "tool_result"]
        assert len(tr_blocks) == 2

    # ── Consecutive same-role merging ─────────────────

    def test_merge_consecutive_user_messages(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "user", "content": "world"},
        ]
        result = normalize_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        # Content should be merged into a list
        assert isinstance(result[0]["content"], list)
        texts = [b["text"] for b in result[0]["content"] if b["type"] == "text"]
        assert "hello" in texts
        assert "world" in texts

    def test_merge_consecutive_assistant_messages(self):
        messages = [
            {"role": "assistant", "content": "part one"},
            {"role": "assistant", "content": "part two"},
        ]
        result = normalize_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"

    def test_no_merge_different_roles(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "help"},
        ]
        result = normalize_messages(messages)
        assert len(result) == 3

    def test_merge_with_list_content(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "a"}]},
            {"role": "user", "content": [{"type": "text", "text": "b"}]},
        ]
        result = normalize_messages(messages)
        assert len(result) == 1
        assert len(result[0]["content"]) == 2

    # ── Edge cases ────────────────────────────────────

    def test_single_message(self):
        messages = [{"role": "user", "content": "hello"}]
        result = normalize_messages(messages)
        assert len(result) == 1

    def test_empty_messages(self):
        result = normalize_messages([])
        assert result == []
