from unittest.mock import patch, MagicMock

from PyQt5.QtWidgets import QLineEdit

from bup.gui.preferences_widget import PreferencesWidget, PreferencesLineEdit


def _make_mock_prefs(**overrides):
    defaults = dict(
        backup_directory="/tmp/backup",
        aws_profile="default",
        aws_access_key_id="AKID",
        aws_secret_access_key="SECRET",
        aws_region="us-east-1",
        github_token="ghp_token",
        verbose=False,
        dry_run=False,
        automatic_backup=False,
        backup_period=None,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_creation(mock_get, qapp):
    mock_get.return_value = _make_mock_prefs()
    w = PreferencesWidget()
    assert w.backup_directory_line_edit is not None
    assert w.aws_profile_line_edit is not None
    assert w.github_token_line_edit is not None
    assert w.dry_run_check_box is not None
    assert w.verbose_check_box is not None


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_loads_from_preferences(mock_get, qapp):
    mock_get.return_value = _make_mock_prefs()
    w = PreferencesWidget()
    assert w.backup_directory_line_edit.text() == "/tmp/backup"
    assert w.aws_profile_line_edit.text() == "default"
    assert w.aws_access_key_id_line_edit.text() == "AKID"
    assert w.aws_secret_access_key_line_edit.text() == "SECRET"
    assert w.aws_region_line_edit.text() == "us-east-1"
    assert w.github_token_line_edit.text() == "ghp_token"


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_backup_directory_changed(mock_get, qapp):
    prefs = _make_mock_prefs()
    mock_get.return_value = prefs
    w = PreferencesWidget()
    w.backup_directory_line_edit.setText("/new/path")
    assert prefs.backup_directory == "/new/path"


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_aws_fields_changed(mock_get, qapp):
    prefs = _make_mock_prefs()
    mock_get.return_value = prefs
    w = PreferencesWidget()
    w.aws_profile_line_edit.setText("prod")
    assert prefs.aws_profile == "prod"
    w.aws_access_key_id_line_edit.setText("NEWAKID")
    assert prefs.aws_access_key_id == "NEWAKID"
    w.aws_secret_access_key_line_edit.setText("NEWSECRET")
    assert prefs.aws_secret_access_key == "NEWSECRET"
    w.aws_region_line_edit.setText("eu-west-1")
    assert prefs.aws_region == "eu-west-1"


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_github_token_changed(mock_get, qapp):
    prefs = _make_mock_prefs()
    mock_get.return_value = prefs
    w = PreferencesWidget()
    w.github_token_line_edit.setText("ghp_new")
    assert prefs.github_token == "ghp_new"


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_checkbox_verbose_dry_run(mock_get, qapp):
    prefs = _make_mock_prefs()
    mock_get.return_value = prefs
    w = PreferencesWidget()
    w.verbose_check_box.setChecked(True)
    w.verbose_check_box.click()  # triggers clicked signal
    assert prefs.verbose == w.verbose_check_box.isChecked()
    w.dry_run_check_box.setChecked(True)
    w.dry_run_check_box.click()
    assert prefs.dry_run == w.dry_run_check_box.isChecked()


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_aws_secret_show_hide(mock_get, qapp):
    mock_get.return_value = _make_mock_prefs()
    w = PreferencesWidget()
    assert w.aws_secret_access_key_line_edit.echoMode() == QLineEdit.Password
    w.aws_show_button.click()
    assert w.aws_secret_access_key_line_edit.echoMode() == QLineEdit.Normal
    assert w.aws_show_button.text() == "Hide"
    w.aws_show_button.click()
    assert w.aws_secret_access_key_line_edit.echoMode() == QLineEdit.Password
    assert w.aws_show_button.text() == "Show"


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_dry_run_loaded_true(mock_get, qapp):
    mock_get.return_value = _make_mock_prefs(dry_run=True)
    w = PreferencesWidget()
    assert w.dry_run_check_box.isChecked()


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_dry_run_loaded_false(mock_get, qapp):
    mock_get.return_value = _make_mock_prefs(dry_run=False)
    w = PreferencesWidget()
    assert not w.dry_run_check_box.isChecked()


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_backup_period_minimum_is_1(mock_get, qapp):
    mock_get.return_value = _make_mock_prefs()
    w = PreferencesWidget()
    assert w.automatic_backup_period.minimum() == 1


@patch("bup.gui.preferences_widget.get_gui_preferences")
def test_github_show_hide(mock_get, qapp):
    mock_get.return_value = _make_mock_prefs()
    w = PreferencesWidget()
    assert w.github_token_line_edit.echoMode() == QLineEdit.Password
    w.github_show_button.click()
    assert w.github_token_line_edit.echoMode() == QLineEdit.Normal
    assert w.github_show_button.text() == "Hide"
    w.github_show_button.click()
    assert w.github_token_line_edit.echoMode() == QLineEdit.Password
    assert w.github_show_button.text() == "Show"
