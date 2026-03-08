from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.git_info import detect_language, get_disk_usage, get_git_info, get_readme_headline


def test_get_git_info_no_git(tmp_path: Path):
    """Non-git directory returns None."""
    result = get_git_info(tmp_path)
    assert result is None


def test_get_git_info_with_git(tmp_path: Path):
    """Directory with .git returns GitInfo."""
    (tmp_path / ".git").mkdir()
    with patch("arasul_tui.core.git_info.run_cmd", return_value=""):
        result = get_git_info(tmp_path)
    assert result is not None
    assert result.branch == ""
    assert result.is_dirty is False


def test_get_git_info_dirty(tmp_path: Path):
    """Dirty status is detected."""
    (tmp_path / ".git").mkdir()

    def mock_cmd(cmd, **kwargs):
        if "status --porcelain" in cmd:
            return " M file.py"
        if "symbolic-ref" in cmd:
            return "main"
        return ""

    with patch("arasul_tui.core.git_info.run_cmd", side_effect=mock_cmd):
        result = get_git_info(tmp_path)
    assert result is not None
    assert result.is_dirty is True
    assert result.branch == "main"


def test_detect_language_python(tmp_path: Path):
    """Python files are detected."""
    (tmp_path / "app.py").write_text("print('hello')")
    (tmp_path / "utils.py").write_text("pass")
    (tmp_path / "README.md").write_text("# Test")

    result = detect_language(tmp_path)
    assert "Python" in result


def test_detect_language_mixed(tmp_path: Path):
    """Multiple languages are detected."""
    (tmp_path / "app.py").write_text("pass")
    (tmp_path / "script.sh").write_text("#!/bin/bash")
    (tmp_path / "index.js").write_text("console.log('hi')")

    result = detect_language(tmp_path)
    assert result  # Should contain at least one language


def test_detect_language_empty(tmp_path: Path):
    """Empty directory returns empty string."""
    result = detect_language(tmp_path)
    assert result == ""


def test_get_readme_headline(tmp_path: Path):
    """README headline is extracted."""
    (tmp_path / "README.md").write_text("# My Project\n\nSome description")
    result = get_readme_headline(tmp_path)
    assert result == "My Project"


def test_get_readme_headline_no_readme(tmp_path: Path):
    """Missing README returns empty string."""
    result = get_readme_headline(tmp_path)
    assert result == ""


def test_get_disk_usage(tmp_path: Path):
    """Disk usage returns a size string."""
    (tmp_path / "file.txt").write_text("x" * 1000)
    with patch("arasul_tui.core.git_info.run_cmd", return_value="4.0K"):
        result = get_disk_usage(tmp_path)
    assert result == "4.0K"
