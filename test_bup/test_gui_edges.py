"""
Tests for parts of the GUI that had none: the About tab without its license files, and the exclusions of the Backup tab being
written to the preferences.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from bup import BackupTypes
from bup.gui.about import BupAbout
from bup.gui.run_backup_widget import BackupWidget, DisplayTypes


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_about_says_so_when_there_is_no_license_file(qapp):
    with patch.object(Path, "rglob", return_value=iter([])):
        about_widget = BupAbout()

    assert about_widget.about_text_widget.toPlainText().startswith('License file not found at "None" ("None"), license_file_parent_dir="')


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_about_says_so_when_there_is_no_gpl_file(qapp, tmp_path):
    license_path = tmp_path / "LICENSE"
    license_path.write_text("the license of bup")

    with patch.object(Path, "rglob", return_value=iter([license_path])):
        about_widget = BupAbout()

    about_text = about_widget.about_text_widget.toPlainText()
    assert "the license of bup" in about_text
    assert "GPL license file not found at" in about_text


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def backup_widget(qapp):
    """
    The S3 box of the Backup tab, with a stand-in for the exclusion preferences (as .exclusion_preferences), which has two entries.
    """
    exclusion_preferences = MagicMock()
    exclusion_preferences.get.return_value = ["bucket-a", "bucket-b  # a note"]
    with patch("bup.gui.run_backup_widget.ExclusionPreferences", return_value=exclusion_preferences) as exclusion_preferences_class:
        widget = BackupWidget(BackupTypes.S3)
        widget.exclusion_preferences = exclusion_preferences
        widget.exclusion_preferences_class = exclusion_preferences_class
        yield widget


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_exclusions_are_shown_as_they_are_saved(backup_widget):
    backup_widget.exclusion_preferences_class.assert_called_with("S3")
    assert backup_widget.display_boxes[DisplayTypes.exclusions].text_box.toPlainText() == "bucket-a\nbucket-b  # a note"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_edited_exclusions_are_written_without_blank_lines_and_surrounding_whitespace(backup_widget):
    backup_widget.display_boxes[DisplayTypes.exclusions].text_box.setText("  bucket-a \n\n   \nbucket-c  # kept as typed\n")
    assert backup_widget.exclusions_save_timer.isActive()  # written a moment after the last keystroke, not on every one
    backup_widget.exclusion_preferences.set.assert_not_called()

    backup_widget.flush_exclusions()

    backup_widget.exclusion_preferences.set.assert_called_once_with(["bucket-a", "bucket-c  # kept as typed"])
    assert not backup_widget.exclusions_save_timer.isActive()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_flush_writes_nothing_when_the_exclusions_were_not_edited(backup_widget):
    backup_widget.flush_exclusions()

    backup_widget.exclusion_preferences.set.assert_not_called()
