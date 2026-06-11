import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from pathlib import Path
from learn_agent.utils.safe_path import safe_path, WORKDIR


class TestSafePath:
    def test_relative_path(self):
        p = safe_path("src/main.py")
        assert p == (WORKDIR / "src/main.py").resolve()

    def test_current_dir(self):
        p = safe_path(".")
        assert p == WORKDIR.resolve()

    def test_subdir_file(self):
        p = safe_path("tests/test_file.py")
        assert p == (WORKDIR / "tests/test_file.py").resolve()

    def test_path_escape_with_dotdot(self):
        with pytest.raises(ValueError, match="escapes"):
            safe_path("../../etc/passwd")

    def test_path_escape_with_absolute(self):
        with pytest.raises(ValueError, match="escapes"):
            safe_path("/etc/passwd")

    def test_path_escape_symlink_attempt(self):
        """Even relative symlink-like paths outside workdir should be blocked."""
        with pytest.raises(ValueError, match="escapes"):
            safe_path("src/../../../etc/passwd")

    def test_nested_normal_path(self):
        p = safe_path("a/b/c/d.txt")
        assert p == (WORKDIR / "a/b/c/d.txt").resolve()
