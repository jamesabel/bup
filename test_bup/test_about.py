"""
Tests for the About tab. All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import platform

import pytest

from bup import __version__
from bup.gui.about import BupAbout


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def about_text(qapp) -> str:
    about_widget = BupAbout()
    return about_widget.about_text_widget.toPlainText()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_about_shows_bup_version_and_no_aws_cli_version(about_text):
    assert f"BUP ({__version__})" in about_text
    assert "AWS CLI" not in about_text  # bup no longer uses the AWS CLI


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_about_shows_running_python_version(about_text):
    assert f"Python version: {platform.python_version()}" in about_text
