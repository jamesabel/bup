"""
Tests for the widgets of the GUI's Preferences tab that are bound to a preference (bup/gui/preferences_widget.py).
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

from unittest.mock import MagicMock

import pytest

from bup.gui import preferences_widget
from bup.gui.preferences_widget import PreferencesLineEdit


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def gui_preferences(monkeypatch):
    """
    Stand-in for the GUI's preferences, so no test reads or writes the real ones.
    """
    preferences = MagicMock()
    monkeypatch.setattr(preferences_widget, "get_gui_preferences", lambda: preferences)
    return preferences


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_bound_line_edit_loads_and_saves_its_preference(qapp, gui_preferences):
    gui_preferences.aws_profile = "my-profile"
    line_edit = PreferencesLineEdit("aws_profile")

    line_edit.load(gui_preferences)
    assert line_edit.text() == "my-profile"

    line_edit.setText("  another-profile ")  # every edit is saved, without the whitespace around it
    assert gui_preferences.aws_profile == "another-profile"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_unbound_line_edit_has_no_preference_to_load_or_save(qapp, gui_preferences):
    line_edit = PreferencesLineEdit()
    line_edit.setText("typed")

    line_edit.load(gui_preferences)
    line_edit.save()

    assert line_edit.text() == "typed"
    assert gui_preferences.mock_calls == []  # nothing was read from or written to the preferences
