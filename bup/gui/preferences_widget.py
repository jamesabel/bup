"""
The GUI's "Preferences" tab, and the widgets it is made of. A change in the tab is written to the preferences right away (there is no
"save" button), which is what the backups read when they run.
"""

import threading
from typing import Callable, Optional

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QPushButton, QLabel, QFileDialog, QLineEdit, QCheckBox, QSpinBox

from bup import get_preferences, UITypes
from bup.credential_check import CredentialCheck, check_dynamodb_credentials, check_github_credentials, check_s3_credentials
from bup.log_routing import set_detailed_file_logging, default_file_size_limit_mb
from bup.gui.gui_util import make_row
from bup.gui.status_line import status_emitter


def get_gui_preferences():
    """
    :return: the preferences of the GUI (the CLI has its own)
    """
    return get_preferences(UITypes.gui)


class PreferencesLineEdit(QLineEdit):
    """
    A line edit for a text preference: it tolerates a preference that is not set (None), and its text is without the whitespace
    around it. Given the name of a preference, it is bound to that preference: load() shows it and every edit writes it.
    """

    def __init__(self, preference_name: Optional[str] = None, password: bool = False):
        """
        :param preference_name: the attribute of the preferences this edits (None to not be bound to one)
        :param password: True to not show what is typed (see ShowButton)
        """
        super().__init__()
        self.preference_name = preference_name
        if password:
            self.setEchoMode(QLineEdit.Password)
        if preference_name is not None:
            self.textChanged.connect(self.save)

    def setText(self, a0: Optional[str]):
        """
        Show a text. None (a preference that is not set) leaves what is shown as it is.

        :param a0: the text (the name is the one PyQt5 gives this parameter of QLineEdit.setText)
        """
        if a0 is not None:
            super().setText(a0)

    def text(self):
        """
        :return: the text, without the whitespace around it
        """
        return super().text().strip()

    def load(self, preferences):
        """
        Show the preference this is bound to (nothing to show if it is not bound to one).
        """
        if self.preference_name is not None:
            self.setText(getattr(preferences, self.preference_name))

    def save(self):
        """
        Write the text to the preference this is bound to (nothing to write if it is not bound to one).
        """
        if self.preference_name is not None:
            setattr(get_gui_preferences(), self.preference_name, self.text())


class PreferenceCheckBox(QCheckBox):
    """
    A check box that is bound to a bool preference: load() shows it and every click writes it.
    """

    def __init__(self, label: str, preference_name: str):
        """
        :param label: the text of the check box
        :param preference_name: the attribute of the preferences this sets
        """
        super().__init__(label)
        self.preference_name = preference_name
        self.clicked.connect(self.save)

    def load(self, preferences):
        """
        Show the preference this is bound to. A preference that is not set (None) is not checked.
        """
        self.setChecked(bool(getattr(preferences, self.preference_name)))

    def save(self):
        """
        Write whether this is checked to the preference it is bound to.
        """
        setattr(get_gui_preferences(), self.preference_name, self.isChecked())


class ShowButton(QPushButton):
    """
    A button that shows what is typed in a password line edit, and hides it again.
    """

    def __init__(self, line_edit: QLineEdit):
        """
        :param line_edit: the password line edit
        """
        super().__init__("Show")
        self.line_edit = line_edit
        self.clicked.connect(self.toggle)

    def toggle(self):
        """
        Show what is typed if it is hidden, and hide it if it is shown. The text of the button is what a click does next.
        """
        if self.line_edit.echoMode() == QLineEdit.Password:
            self.setText("Hide")
            self.line_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.setText("Show")
            self.line_edit.setEchoMode(QLineEdit.Password)


class CredentialCheckButton(QPushButton):
    """
    A button that checks the credentials of one backup type as they are in the preferences now (every edit is saved right away),
    and says how the check went in the status line of the main window (and in its own tool tip). The check makes a request to AWS
    or GitHub, which can take a while, so it runs in a thread of its own and the button is disabled until it is back.
    """

    result_signal = pyqtSignal(object)  # the CredentialCheck of a check, from its thread to the GUI thread

    def __init__(self, name: str, check: Callable[..., CredentialCheck]):
        """
        :param name: what the button checks, e.g. "S3"
        :param check: does the check: it is given the preferences and returns how the check went (see bup/credential_check.py)
        """
        super().__init__(f"Test {name}")
        self.name = name
        self.check = check
        self.result: Optional[CredentialCheck] = None  # how the most recent check went, None if there has been none (or it is running)
        self.check_thread: Optional[threading.Thread] = None
        self.result_signal.connect(self.show_result)
        self.clicked.connect(self.start_check)

    def start_check(self):
        """
        Start the check, in its thread. The result is shown by show_result().
        """
        self.setEnabled(False)
        self.result = None
        self.setToolTip("")
        status_emitter.status_signal.emit(f"Testing the {self.name} credentials ...")
        # a daemon thread, so that a check that is waiting for a response does not keep bup from closing
        self.check_thread = threading.Thread(target=self.run_check, args=(get_gui_preferences(),), name=f"{self.text()}", daemon=True)
        self.check_thread.start()

    def run_check(self, preferences):
        """
        What the thread runs: do the check and send how it went to the GUI thread.

        :param preferences: the preferences to check the credentials of
        """
        try:
            credential_check = self.check(preferences)
        except Exception as e:
            # not one of the failures a check reports itself: show it, since the button is waiting for a result, and let it on its way
            self.send_result(CredentialCheck(False, f"{type(e).__name__} : {e}"))
            raise
        self.send_result(credential_check)

    def send_result(self, credential_check: CredentialCheck):
        """
        Send how the check went to the GUI thread, from the thread of the check.
        """
        try:
            self.result_signal.emit(credential_check)
        except RuntimeError:
            pass  # the button no longer exists (bup was closed while the check was running), so there is nowhere to show the result

    def show_result(self, credential_check: CredentialCheck):
        """
        Show how the check went, and let the user check again. Connected to the result signal, so it runs in the GUI thread.
        """
        self.result = credential_check
        self.setToolTip(credential_check.message)
        status_emitter.status_signal.emit(f"{self.name} credentials: {credential_check.message}")
        self.setEnabled(True)


class PreferencesWidget(QWidget):
    """
    "Preferences" tab - the backup directory, the AWS and GitHub credentials with a test of each, the automatic backup schedule, the
    detailed log directory and the options of a backup.
    """

    def __init__(self):
        """
        Make the tab, showing the preferences as they are saved.
        """
        super().__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)

        # backup directory
        self.backup_directory_line_edit = PreferencesLineEdit("backup_directory")
        self.select_backup_directory_button = QPushButton("Select Backup Directory")
        self.select_backup_directory_button.clicked.connect(self.select_backup_directory)
        self.backup_directory_widget = make_row("Backup Directory:", self.backup_directory_line_edit, self.select_backup_directory_button)
        self.backup_directory_widget.adjustSize()  # all done adding - figure out what the height should be
        self.backup_directory_widget.setMaximumHeight(self.backup_directory_widget.minimumHeight())
        self.layout().addWidget(self.backup_directory_widget)
        self.add_space(2)

        # AWS credentials: a profile, or an access key ID and a secret access key
        self.aws_profile_line_edit = PreferencesLineEdit("aws_profile")
        self.aws_profile_widget = make_row("AWS Profile:", self.aws_profile_line_edit)
        self.layout().addWidget(self.aws_profile_widget)
        or_label = QLabel("or")  # italicize "or"
        or_font = or_label.font()
        or_font.setItalic(True)
        or_label.setFont(or_font)
        self.layout().addWidget(or_label)
        self.aws_access_key_id_line_edit = PreferencesLineEdit("aws_access_key_id")
        self.aws_secret_access_key_line_edit = PreferencesLineEdit("aws_secret_access_key", password=True)
        self.aws_show_button = ShowButton(self.aws_secret_access_key_line_edit)
        self.aws_key_widget = make_row("AWS Access Key ID:", self.aws_access_key_id_line_edit, "AWS Secret Access Key:", self.aws_secret_access_key_line_edit, self.aws_show_button)
        self.layout().addWidget(self.aws_key_widget)
        self.add_space(1)

        # AWS region, and a test of the AWS credentials for each backup type that uses them (their permissions can differ)
        self.aws_region_line_edit = PreferencesLineEdit("aws_region")
        self.test_s3_button = CredentialCheckButton("S3", check_s3_credentials)
        self.test_dynamodb_button = CredentialCheckButton("DynamoDB", check_dynamodb_credentials)
        self.aws_region_widget = make_row("AWS Region:", self.aws_region_line_edit, self.test_s3_button, self.test_dynamodb_button)
        self.layout().addWidget(self.aws_region_widget)
        self.add_space(2)

        # github
        self.github_token_line_edit = PreferencesLineEdit("github_token", password=True)
        self.github_show_button = ShowButton(self.github_token_line_edit)
        self.test_github_button = CredentialCheckButton("GitHub", check_github_credentials)
        self.github_widget = make_row("github token:", self.github_token_line_edit, self.github_show_button, self.test_github_button)
        self.layout().addWidget(self.github_widget)
        self.add_space(2)

        # automatic backup
        self.automatic_backup_period = QSpinBox()
        self.automatic_backup_period.setMinimum(1)
        self.automatic_backup_period.textChanged.connect(self.automatic_backup_changed)
        self.automatic_backup_enable_check_box = QCheckBox("enable")
        self.automatic_backup_enable_check_box.clicked.connect(self.automatic_backup_changed)
        self.automatic_backup_widget = make_row("Backup every (hours):", self.automatic_backup_period, self.automatic_backup_enable_check_box)
        self.layout().addWidget(self.automatic_backup_widget)
        self.add_space(2)

        # detailed log directory (optional - one log file per backup type, with e.g. every S3 object a sync downloads)
        # debounce applying the directory so a half-typed path doesn't start collecting log files
        self.detailed_log_apply_timer = QTimer(self)
        self.detailed_log_apply_timer.setSingleShot(True)
        self.detailed_log_apply_timer.setInterval(1000)  # ms
        self.detailed_log_apply_timer.timeout.connect(self.apply_detailed_log_directory)
        self.detailed_log_directory_line_edit = PreferencesLineEdit("detailed_log_directory")
        self.detailed_log_directory_line_edit.textChanged.connect(self.detailed_log_apply_timer.start)
        self.select_detailed_log_directory_button = QPushButton("Select Detailed Log Directory")
        self.select_detailed_log_directory_button.clicked.connect(self.select_detailed_log_directory)
        self.detailed_log_file_size_limit = QSpinBox()
        self.detailed_log_file_size_limit.setMinimum(1)
        self.detailed_log_file_size_limit.setMaximum(10000)
        self.detailed_log_file_size_limit.setValue(default_file_size_limit_mb)
        self.detailed_log_file_size_limit.valueChanged.connect(self.detailed_log_file_size_limit_changed)
        self.detailed_log_widget = make_row(
            "Detailed Log Directory (blank for none):",
            self.detailed_log_directory_line_edit,
            self.select_detailed_log_directory_button,
            "File size limit (MB):",
            self.detailed_log_file_size_limit,
        )
        self.layout().addWidget(self.detailed_log_widget)
        self.add_space(2)

        # the options of a backup
        self.dry_run_check_box = PreferenceCheckBox("Dry run", "dry_run")
        self.s3_size_only_check_box = PreferenceCheckBox("S3 sync compares file size only, not timestamps (--size_only)", "s3_size_only")
        self.s3_verify_check_box = PreferenceCheckBox(
            "S3 backup is followed by a verification of every local file against S3: size, hash and modification time (a request to S3 per object, and reads every file)", "s3_verify"
        )
        self.s3_fix_mtime_check_box = PreferenceCheckBox(
            "The verification fixes the modification time of a local file that has the contents of its S3 object (downloads an object S3 has no hash of, to compare)", "s3_fix_mtime"
        )
        self.verbose_check_box = PreferenceCheckBox("Verbose", "verbose")
        for check_box in (self.dry_run_check_box, self.s3_size_only_check_box, self.s3_verify_check_box, self.s3_fix_mtime_check_box, self.verbose_check_box):
            self.layout().addWidget(check_box)

        layout.addStretch()  # bottom padding

        # the widgets that are bound to a preference of their own
        self.preference_widgets = [
            self.backup_directory_line_edit,
            self.aws_profile_line_edit,
            self.aws_access_key_id_line_edit,
            self.aws_secret_access_key_line_edit,
            self.aws_region_line_edit,
            self.github_token_line_edit,
            self.detailed_log_directory_line_edit,
            self.dry_run_check_box,
            self.s3_size_only_check_box,
            self.s3_verify_check_box,
            self.s3_fix_mtime_check_box,
            self.verbose_check_box,
        ]

        self.load_preferences()

    def add_space(self, line_count: int):
        """
        Add vertical space between two groups of preferences.

        :param line_count: the height of the space, in lines of text
        """
        for _unused_line in range(line_count):
            self.layout().addWidget(QLabel())

    def load_preferences(self):
        """
        Show the preferences as they are saved.
        """
        preferences = get_gui_preferences()
        for preference_widget in self.preference_widgets:
            preference_widget.load(preferences)
        if preferences.detailed_log_file_size_limit_mb is not None:
            self.detailed_log_file_size_limit.setValue(preferences.detailed_log_file_size_limit_mb)
        self.automatic_backup_enable_check_box.setChecked(bool(preferences.automatic_backup))
        if preferences.backup_period is not None:
            self.automatic_backup_period.setValue(preferences.backup_period)

    def select_backup_directory(self):
        """
        Let the user pick the backup directory in a dialog (nothing changes if the dialog is cancelled).
        """
        new_backup_directory = QFileDialog.getExistingDirectory(self, "Select Backup Directory")
        if new_backup_directory is not None and len(new_backup_directory) > 0:
            self.backup_directory_line_edit.setText(new_backup_directory)

    def select_detailed_log_directory(self):
        """
        Let the user pick the detailed log directory in a dialog (nothing changes if the dialog is cancelled).
        """
        new_detailed_log_directory = QFileDialog.getExistingDirectory(self, "Select Detailed Log Directory")
        if new_detailed_log_directory is not None and len(new_detailed_log_directory) > 0:
            self.detailed_log_directory_line_edit.setText(new_detailed_log_directory)

    def detailed_log_file_size_limit_changed(self):
        """
        Save the file size limit of the detailed logs, and apply it a moment later (see apply_detailed_log_directory()).
        """
        get_gui_preferences().detailed_log_file_size_limit_mb = self.detailed_log_file_size_limit.value()  # QSpinBox guarantees an int
        self.detailed_log_apply_timer.start()

    def apply_detailed_log_directory(self):
        """
        Start (or stop, or move) the detailed file logging, as the detailed log directory and file size limit are now.
        """
        set_detailed_file_logging(self.detailed_log_directory_line_edit.text(), self.detailed_log_file_size_limit.value())

    def automatic_backup_changed(self):
        """
        Save whether the automatic backup is enabled and its period, which the main window reads every second (see
        BupDialog.autobackup_tick()).
        """
        preferences = get_gui_preferences()
        preferences.automatic_backup = self.automatic_backup_enable_check_box.isChecked()
        preferences.backup_period = self.automatic_backup_period.value()  # QSpinBox guarantees an int
