import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pytest
from learn_agent.tools.run_edit import run_edit


class TestRunEdit:
    def test_replace_first_occurrence(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello world\nhello again")
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_edit("file.txt", "hello", "hi")
            assert "Edited" in result
            assert f.read_text() == "hi world\nhello again"
        finally:
            sp.WORKDIR = old_cwd

    def test_text_not_found(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("foo bar")
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_edit("file.txt", "nonexistent", "replacement")
            assert "text not found" in result
            assert f.read_text() == "foo bar"  # unchanged
        finally:
            sp.WORKDIR = old_cwd

    def test_file_not_found(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_edit("missing.txt", "old", "new")
            assert result.startswith("Error:")
        finally:
            sp.WORKDIR = old_cwd

    def test_path_escape_blocked(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_edit("../../../etc/passwd", "root", "hacked")
            assert result.startswith("Error:")
        finally:
            sp.WORKDIR = old_cwd

    def test_multiline_text_replacement(self, tmp_path):
        f = tmp_path / "file.py"
        f.write_text("def foo():\n    pass\n\ndef bar():\n    pass")
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_edit("file.py", "def foo():\n    pass", "def foo():\n    return 42")
            assert "Edited" in result
            assert "return 42" in f.read_text()
        finally:
            sp.WORKDIR = old_cwd
