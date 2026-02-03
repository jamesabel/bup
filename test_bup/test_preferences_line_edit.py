from unittest.mock import patch, MagicMock

from bup.gui.preferences_widget import PreferencesLineEdit


@patch("bup.gui.preferences_widget.get_gui_preferences", return_value=MagicMock())
def test_none_tolerance(mock_prefs, qapp):
    widget = PreferencesLineEdit()
    widget.setText(None)
    assert widget.text() == ""


@patch("bup.gui.preferences_widget.get_gui_preferences", return_value=MagicMock())
def test_normal_text(mock_prefs, qapp):
    widget = PreferencesLineEdit()
    widget.setText("hello")
    assert widget.text() == "hello"


@patch("bup.gui.preferences_widget.get_gui_preferences", return_value=MagicMock())
def test_strips_whitespace(mock_prefs, qapp):
    widget = PreferencesLineEdit()
    widget.setText("  val  ")
    assert widget.text() == "val"


@patch("bup.gui.preferences_widget.get_gui_preferences", return_value=MagicMock())
def test_empty_string(mock_prefs, qapp):
    widget = PreferencesLineEdit()
    widget.setText("")
    assert widget.text() == ""
