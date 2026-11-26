"""
The GUI's "Preferences" tab, and the widgets it is made of. A change in the tab is written to the preferences right away (there is no
"save" button), which is what the backups read when they run.
"""

from typing import Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QPushButton, QLabel, QFileDialog, QLineEdit, QCheckBox, QSpinBox

from bup import get_preferences, UITypes
from bup.log_routing import set_detailed_file_logging, default_file_size_limit_mb
from bup.gui.gui_util import make_row


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
        # tolerate None (a0 is the name PyQt5 gives this parameter of QLineEdit.setText)
        if a0 is not None:
            super().setText(a0)

    def text(self):
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
        if self.line_edit.echoMode() == QLineEdit.Password:
            self.setText("Hide")
            self.line_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.setText("Show")
            self.line_edit.setEchoMode(QLineEdit.Password)


class PreferencesWidget(QWidget):
    """
    "Preferences" tab - the backup directory, the AWS and GitHub credentials, the automatic backup schedule, the detailed log
    directory and the options of a backup.
    """

    def __init__(self):
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

        # AWS region
        self.aws_region_line_edit = PreferencesLineEdit("aws_region")
        self.aws_region_widget = make_row("AWS Region:", self.aws_region_line_edit)
        self.layout().addWidget(self.aws_region_widget)
        self.add_space(2)

        # github
        self.github_token_line_edit = PreferencesLineEdit("github_token", password=True)
        self.github_show_button = ShowButton(self.github_token_line_edit)
        self.github_widget = make_row("github token:", self.github_token_line_edit, self.github_show_button)
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
        new_backup_directory = QFileDialog.getExistingDirectory(self, "Select Backup Directory")
        if new_backup_directory is not None and len(new_backup_directory) > 0:
            self.backup_directory_line_edit.setText(new_backup_directory)

    def select_detailed_log_directory(self):
        new_detailed_log_directory = QFileDialog.getExistingDirectory(self, "Select Detailed Log Directory")
        if new_detailed_log_directory is not None and len(new_detailed_log_directory) > 0:
            self.detailed_log_directory_line_edit.setText(new_detailed_log_directory)

    def detailed_log_file_size_limit_changed(self):
        get_gui_preferences().detailed_log_file_size_limit_mb = self.detailed_log_file_size_limit.value()  # QSpinBox guarantees an int
        self.detailed_log_apply_timer.start()

    def apply_detailed_log_directory(self):
        """
        Start (or stop, or move) the detailed file logging, as the detailed log directory and file size limit are now.
        """
        set_detailed_file_logging(self.detailed_log_directory_line_edit.text(), self.detailed_log_file_size_limit.value())

    def automatic_backup_changed(self):
        preferences = get_gui_preferences()
        preferences.automatic_backup = self.automatic_backup_enable_check_box.isChecked()
        preferences.backup_period = self.automatic_backup_period.value()  # QSpinBox guarantees an int
