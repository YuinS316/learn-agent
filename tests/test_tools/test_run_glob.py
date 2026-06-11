import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pytest
from learn_agent.tools.run_glob import run_glob


class TestRunGlob:
    def test_match_files(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.py").touch()
        (tmp_path / "c.txt").touch()
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_glob("*.py")
            assert "a.py" in result
            assert "b.py" in result
            assert "c.txt" not in result
        finally:
            sp.WORKDIR = old_cwd

    def test_match_in_subdirs(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src/main.py").touch()
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests/test_main.py").touch()
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_glob("**/*.py")
            assert "src/main.py" in result
            assert "tests/test_main.py" in result
        finally:
            sp.WORKDIR = old_cwd

    def test_no_matches(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_glob("*.nonexistent")
            assert result == "(no matches)"
        finally:
            sp.WORKDIR = old_cwd

    def test_empty_workdir(self, tmp_path):
        """Empty directory should return (no matches)."""
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_glob("*")
            assert result == "(no matches)"
        finally:
            sp.WORKDIR = old_cwd
