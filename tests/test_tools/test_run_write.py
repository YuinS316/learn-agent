import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pytest
from learn_agent.tools.run_write import run_write


class TestRunWrite:
    def test_write_new_file(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_write("output.txt", "hello world")
            assert "Wrote" in result
            assert (tmp_path / "output.txt").read_text() == "hello world"
        finally:
            sp.WORKDIR = old_cwd

    def test_overwrite_existing_file(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("old content")
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            run_write("existing.txt", "new content")
            assert f.read_text() == "new content"
        finally:
            sp.WORKDIR = old_cwd

    def test_creates_parent_directories(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_write("a/b/c/deep.txt", "deep content")
            assert "Wrote" in result
            assert (tmp_path / "a/b/c/deep.txt").read_text() == "deep content"
        finally:
            sp.WORKDIR = old_cwd

    def test_path_escape_blocked(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_write("../../../etc/hacked.txt", "bad")
            assert result.startswith("Error:")
        finally:
            sp.WORKDIR = old_cwd

    def test_empty_content(self, tmp_path):
        import learn_agent.utils.safe_path as sp
        old_cwd = sp.WORKDIR
        sp.WORKDIR = tmp_path
        try:
            result = run_write("empty.txt", "")
            assert "Wrote 0 bytes" in result
        finally:
            sp.WORKDIR = old_cwd
