from typing import Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QLabel, QFileDialog, QLineEdit, QCheckBox, QSpinBox

from bup import get_preferences, UITypes
from bup.log_routing import set_detailed_file_logging, default_file_size_limit_mb


def get_gui_preferences():
    return get_preferences(UITypes.gui)


class PreferencesLineEdit(QLineEdit):
    def setText(self, s: Optional[str]):
        # tolerate None
        if s is not None:
            super().setText(s)

    def text(self):
        return super().text().strip()


class PreferencesWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        # backup directory
        self.backup_directory_widget = QWidget()
        self.backup_directory_widget.setLayout(QHBoxLayout())
        self.backup_directory_line_edit = PreferencesLineEdit()
        self.backup_directory_line_edit.textChanged.connect(self.backup_directory_changed)
        self.select_backup_directory_button = QPushButton("Select Backup Directory")
        self.select_backup_directory_button.clicked.connect(self.select_backup_directory)
        self.backup_directory_widget.layout().addWidget(QLabel("Backup Directory:"))
        self.backup_directory_widget.layout().addWidget(self.backup_directory_line_edit)
        self.backup_directory_widget.layout().addWidget(self.select_backup_directory_button)
        self.backup_directory_widget.layout().addStretch()
        self.backup_directory_widget.adjustSize()  # all done adding - figure out what the height should be
        self.backup_directory_widget.setMaximumHeight(self.backup_directory_widget.minimumHeight())
        self.layout().addWidget(self.backup_directory_widget)
        self.layout().addWidget(QLabel())  # space
        self.layout().addWidget(QLabel())  # space

        # AWS Credentials
        # profile
        self.aws_profile_widget = QWidget()
        self.aws_profile_widget.setLayout(QHBoxLayout())
        self.aws_profile_widget.layout().addWidget(QLabel("AWS Profile:"))
        self.aws_profile_line_edit = PreferencesLineEdit()
        self.aws_profile_line_edit.textChanged.connect(self.aws_profile_changed)
        self.aws_profile_widget.layout().addWidget(self.aws_profile_line_edit)
        self.aws_profile_widget.layout().addStretch()
        self.layout().addWidget(self.aws_profile_widget)
        or_label = QLabel("or")  # italicize "or"
        or_font = or_label.font()
        or_font.setItalic(True)
        or_label.setFont(or_font)
        self.layout().addWidget(or_label)
        # access key ID and secret access key
        self.aws_key_widget = QWidget()
        self.aws_key_widget.setLayout(QHBoxLayout())
        self.aws_key_widget.layout().addWidget(QLabel("AWS Access Key ID:"))
        self.aws_access_key_id_line_edit = PreferencesLineEdit()
        self.aws_access_key_id_line_edit.textChanged.connect(self.aws_access_key_id_changed)
        self.aws_key_widget.layout().addWidget(self.aws_access_key_id_line_edit)
        self.aws_key_widget.layout().addWidget(QLabel("AWS Secret Access Key:"))
        self.aws_secret_access_key_line_edit = PreferencesLineEdit()
        self.aws_secret_access_key_line_edit.textChanged.connect(self.aws_secret_access_key_changed)
        self.aws_secret_access_key_line_edit.setEchoMode(PreferencesLineEdit.Password)
        self.aws_key_widget.layout().addWidget(self.aws_secret_access_key_line_edit)
        self.aws_show_button = QPushButton("Show")
        self.aws_show_button.clicked.connect(self.aws_secret_access_key_visible_clicked)
        self.aws_key_widget.layout().addWidget(self.aws_show_button)
        self.aws_key_widget.layout().addStretch()
        self.layout().addWidget(self.aws_key_widget)
        self.layout().addWidget(QLabel())  # space
        # region
        self.aws_region_widget = QWidget()
        self.aws_region_widget.setLayout(QHBoxLayout())
        self.aws_region_widget.layout().addWidget(QLabel("AWS Region:"))
        self.aws_region_line_edit = PreferencesLineEdit()
        self.aws_region_line_edit.textChanged.connect(self.aws_region_changed)
        self.aws_region_widget.layout().addWidget(self.aws_region_line_edit)
        self.aws_region_widget.layout().addStretch()
        self.layout().addWidget(self.aws_region_widget)
        self.layout().addWidget(QLabel())  # space
        self.layout().addWidget(QLabel())  # space

        # github
        self.github_widget = QWidget()
        self.github_widget.setLayout(QHBoxLayout())
        self.github_widget.layout().addWidget(QLabel("github token:"))
        self.github_token_line_edit = PreferencesLineEdit()
        self.github_token_line_edit.setEchoMode(PreferencesLineEdit.Password)
        self.github_token_line_edit.textChanged.connect(self.github_token_changed)
        self.github_widget.layout().addWidget(self.github_token_line_edit)
        self.github_show_button = QPushButton("Show")
        self.github_show_button.clicked.connect(self.github_visible_clicked)
        self.github_widget.layout().addWidget(self.github_show_button)
        self.github_widget.layout().addStretch()
        self.layout().addWidget(self.github_widget)
        self.layout().addWidget(QLabel())  # space
        self.layout().addWidget(QLabel())  # space

        # automatic backup
        self.automatic_backup_widget = QWidget()
        self.automatic_backup_widget.setLayout(QHBoxLayout())
        self.automatic_backup_period = QSpinBox()
        self.automatic_backup_period.setMinimum(1)
        self.automatic_backup_period.textChanged.connect(self.automatic_backup_changed)
        self.automatic_backup_widget.layout().addWidget(QLabel("Backup every (hours):"))
        self.automatic_backup_widget.layout().addWidget(self.automatic_backup_period)
        self.automatic_backup_enable_check_box = QCheckBox("enable")
        self.automatic_backup_enable_check_box.clicked.connect(self.automatic_backup_changed)
        self.automatic_backup_widget.layout().addWidget(self.automatic_backup_enable_check_box)
        self.automatic_backup_widget.layout().addStretch()
        self.layout().addWidget(self.automatic_backup_widget)
        self.layout().addWidget(QLabel())  # space
        self.layout().addWidget(QLabel())  # space

        # detailed log directory (optional - one log file per backup type, with e.g. the full AWS CLI calls and their output)
        # debounce applying the directory so a half-typed path doesn't start collecting log files
        self.detailed_log_apply_timer = QTimer(self)
        self.detailed_log_apply_timer.setSingleShot(True)
        self.detailed_log_apply_timer.setInterval(1000)  # ms
        self.detailed_log_apply_timer.timeout.connect(self.apply_detailed_log_directory)
        self.detailed_log_widget = QWidget()
        self.detailed_log_widget.setLayout(QHBoxLayout())
        self.detailed_log_directory_line_edit = PreferencesLineEdit()
        self.detailed_log_directory_line_edit.textChanged.connect(self.detailed_log_directory_changed)
        self.select_detailed_log_directory_button = QPushButton("Select Detailed Log Directory")
        self.select_detailed_log_directory_button.clicked.connect(self.select_detailed_log_directory)
        self.detailed_log_widget.layout().addWidget(QLabel("Detailed Log Directory (blank for none):"))
        self.detailed_log_widget.layout().addWidget(self.detailed_log_directory_line_edit)
        self.detailed_log_widget.layout().addWidget(self.select_detailed_log_directory_button)
        self.detailed_log_widget.layout().addWidget(QLabel("File size limit (MB):"))
        self.detailed_log_file_size_limit = QSpinBox()
        self.detailed_log_file_size_limit.setMinimum(1)
        self.detailed_log_file_size_limit.setMaximum(10000)
        self.detailed_log_file_size_limit.setValue(default_file_size_limit_mb)
        self.detailed_log_file_size_limit.valueChanged.connect(self.detailed_log_file_size_limit_changed)
        self.detailed_log_widget.layout().addWidget(self.detailed_log_file_size_limit)
        self.detailed_log_widget.layout().addStretch()
        self.layout().addWidget(self.detailed_log_widget)
        self.layout().addWidget(QLabel())  # space
        self.layout().addWidget(QLabel())  # space

        # dry run
        self.dry_run_check_box = QCheckBox("Dry run")
        self.dry_run_check_box.clicked.connect(self.dry_run_clicked)
        self.layout().addWidget(self.dry_run_check_box)

        # verbose
        self.verbose_check_box = QCheckBox("Verbose")
        self.verbose_check_box.clicked.connect(self.verbose_clicked)
        self.layout().addWidget(self.verbose_check_box)

        self.layout().addStretch()  # bottom padding

        self.load_preferences()

    def load_preferences(self):
        preferences = get_gui_preferences()
        self.backup_directory_line_edit.setText(preferences.backup_directory)
        self.aws_profile_line_edit.setText(preferences.aws_profile)
        self.aws_access_key_id_line_edit.setText(preferences.aws_access_key_id)
        self.aws_secret_access_key_line_edit.setText(preferences.aws_secret_access_key)
        self.aws_region_line_edit.setText(preferences.aws_region)
        self.github_token_line_edit.setText(preferences.github_token)
        self.detailed_log_directory_line_edit.setText(preferences.detailed_log_directory)
        if preferences.detailed_log_file_size_limit_mb is not None:
            self.detailed_log_file_size_limit.setValue(preferences.detailed_log_file_size_limit_mb)
        self.dry_run_check_box.setChecked(bool(preferences.dry_run))  # None translates to False
        self.verbose_check_box.setChecked(bool(preferences.verbose))  # None translates to False
        self.automatic_backup_enable_check_box.setChecked(bool(preferences.automatic_backup))
        if preferences.backup_period is not None:
            self.automatic_backup_period.setValue(preferences.backup_period)

    def select_backup_directory(self):
        new_backup_directory = QFileDialog.getExistingDirectory(self, "Select Backup Directory")
        if new_backup_directory is not None and len(new_backup_directory) > 0:
            self.backup_directory_line_edit.setText(new_backup_directory)

    def backup_directory_changed(self):
        get_gui_preferences().backup_directory = self.backup_directory_line_edit.text()

    def aws_profile_changed(self):
        get_gui_preferences().aws_profile = self.aws_profile_line_edit.text()

    def aws_access_key_id_changed(self):
        get_gui_preferences().aws_access_key_id = self.aws_access_key_id_line_edit.text()

    def aws_secret_access_key_changed(self):
        get_gui_preferences().aws_secret_access_key = self.aws_secret_access_key_line_edit.text()

    def aws_secret_access_key_visible_clicked(self):
        if self.aws_secret_access_key_line_edit.echoMode() == PreferencesLineEdit.Password:
            self.aws_show_button.setText("Hide")
            self.aws_secret_access_key_line_edit.setEchoMode(PreferencesLineEdit.Normal)
        else:
            self.aws_show_button.setText("Show")
            self.aws_secret_access_key_line_edit.setEchoMode(PreferencesLineEdit.Password)

    def aws_region_changed(self):
        get_gui_preferences().aws_region = self.aws_region_line_edit.text()

    def github_token_changed(self):
        get_gui_preferences().github_token = self.github_token_line_edit.text()

    def select_detailed_log_directory(self):
        new_detailed_log_directory = QFileDialog.getExistingDirectory(self, "Select Detailed Log Directory")
        if new_detailed_log_directory is not None and len(new_detailed_log_directory) > 0:
            self.detailed_log_directory_line_edit.setText(new_detailed_log_directory)

    def detailed_log_directory_changed(self):
        get_gui_preferences().detailed_log_directory = self.detailed_log_directory_line_edit.text()
        self.detailed_log_apply_timer.start()

    def detailed_log_file_size_limit_changed(self):
        get_gui_preferences().detailed_log_file_size_limit_mb = self.detailed_log_file_size_limit.value()  # QSpinBox guarantees an int
        self.detailed_log_apply_timer.start()

    def apply_detailed_log_directory(self):
        set_detailed_file_logging(self.detailed_log_directory_line_edit.text(), self.detailed_log_file_size_limit.value())

    def github_visible_clicked(self):
        if self.github_token_line_edit.echoMode() == PreferencesLineEdit.Password:
            self.github_show_button.setText("Hide")
            self.github_token_line_edit.setEchoMode(PreferencesLineEdit.Normal)
        else:
            self.github_show_button.setText("Show")
            self.github_token_line_edit.setEchoMode(PreferencesLineEdit.Password)

    def verbose_clicked(self):
        get_gui_preferences().verbose = self.verbose_check_box.isChecked()

    def dry_run_clicked(self):
        get_gui_preferences().dry_run = self.dry_run_check_box.isChecked()

    def automatic_backup_changed(self):
        preferences = get_gui_preferences()
        preferences.automatic_backup = self.automatic_backup_enable_check_box.isChecked()
        preferences.backup_period = self.automatic_backup_period.value()  # QSpinBox guarantees an int
