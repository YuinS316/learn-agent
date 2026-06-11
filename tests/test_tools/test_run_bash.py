import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pytest
from learn_agent.tools.run_bash import run_bash


class TestRunBash:
    def test_echo(self):
        result = run_bash("echo hello")
        assert "hello" in result

    def test_pwd(self):
        result = run_bash("pwd")
        assert result  # should output current directory

    def test_dangerous_rm_rf_blocked(self):
        result = run_bash("rm -rf /tmp/test")
        assert "Dangerous command blocked" in result

    def test_dangerous_sudo_blocked(self):
        result = run_bash("sudo rm something")
        assert "Dangerous command blocked" in result

    def test_dangerous_shutdown_blocked(self):
        result = run_bash("shutdown -h now")
        assert "Dangerous command blocked" in result

    def test_nonexistent_command(self):
        result = run_bash("nonexistent_command_xyz_123")
        assert "Error:" in result or result  # should not crash

    def test_multiline_output(self):
        result = run_bash("printf 'line1\\nline2\\nline3'")
        assert "line1" in result
        assert "line3" in result

    def test_empty_output(self):
        result = run_bash("true")  # 'true' produces no output
        assert result == "(no output)"
