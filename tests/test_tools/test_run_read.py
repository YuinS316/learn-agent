import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pytest
from learn_agent.tools.run_read import run_read


class TestRunRead:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3")
        # Change workdir for safe_path to work
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            assert run_read("hello.txt") == "line1\nline2\nline3"
        finally:
            sp.WORKDIR = old_cwd

    def test_read_with_limit(self, tmp_path):
        f = tmp_path / "data.txt"
        lines = [f"line{i}" for i in range(10)]
        f.write_text("\n".join(lines))
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_read("data.txt", limit=3)
            assert "line0" in result
            assert "line2" in result
            assert "(7 more lines)" in result
            assert "line9" not in result
        finally:
            sp.WORKDIR = old_cwd

    def test_read_nonexistent_file(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_read("nonexistent.txt")
            assert result.startswith("Error:")
        finally:
            sp.WORKDIR = old_cwd

    def test_read_path_escape_blocked(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_read("../../../etc/passwd")
            assert result.startswith("Error:")
        finally:
            sp.WORKDIR = old_cwd
