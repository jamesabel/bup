"""
Tests for the About tab. All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import platform
from unittest.mock import patch

import pytest

from bup import __version__
from bup.gui.about import BupAbout

_aws_cli_version_text = "1.2.3 (latest: 1.2.4)"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def about_text(qapp) -> str:
    # the AWS CLI lookup runs a subprocess and queries PyPI, so replace it
    with patch("bup.gui.about.get_aws_cli_version_text", return_value=_aws_cli_version_text):
        about_widget = BupAbout()
    return about_widget.about_text_widget.toPlainText()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_about_shows_bup_and_aws_cli_versions(about_text):
    assert f"BUP ({__version__})" in about_text
    assert f"AWS CLI version: {_aws_cli_version_text}" in about_text


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_about_shows_running_python_version(about_text):
    assert f"Python version: {platform.python_version()}" in about_text
