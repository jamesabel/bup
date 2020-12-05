from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QLabel, QFileDialog, QLineEdit, QCheckBox, QSpinBox

from bup import get_preferences, UITypes


def get_gui_preferences():
    return get_preferences(UITypes.gui)


class PreferencesLineEdit(QLineEdit):
    def setText(self, s: (str, None)):
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
        self.automatic_backup_frequency = QSpinBox()
        self.automatic_backup_frequency.textChanged.connect(self.automatic_backup_changed)
        self.automatic_backup_widget.layout().addWidget(QLabel("Automatic backup frequency (hours):"))
        self.automatic_backup_widget.layout().addWidget(self.automatic_backup_frequency)
        self.automatic_backup_enable_check_box = QCheckBox("enable")
        self.automatic_backup_enable_check_box.clicked.connect(self.automatic_backup_changed)
        self.automatic_backup_widget.layout().addWidget(self.automatic_backup_enable_check_box)
        self.automatic_backup_widget.layout().addStretch()
        self.layout().addWidget(self.automatic_backup_widget)
        self.layout().addWidget(QLabel())  # space
        self.layout().addWidget(QLabel())  # space

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
        self.verbose_check_box.setChecked(bool(preferences.verbose))  # None translates to False
        self.automatic_backup_enable_check_box.setChecked(bool(preferences.automatic_backup))
        self.automatic_backup_frequency.setValue(preferences.backup_frequency)

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

    def github_visible_clicked(self):
        if self.github_token_line_edit.echoMode() == PreferencesLineEdit.Password:
            self.github_show_button.setText("Hide")
            self.github_token_line_edit.setEchoMode(PreferencesLineEdit.Normal)
        else:
            self.github_show_button.setText("Show")
            self.github_token_line_edit.setEchoMode(PreferencesLineEdit.Password)

    def verbose_clicked(self):
        get_gui_preferences().verbose = self.verbose_check_box.isChecked()

    def automatic_backup_changed(self):
        preferences = get_gui_preferences()
        preferences.automatic_backup = self.automatic_backup_enable_check_box.isChecked()
        if len(backup_frequency := self.automatic_backup_frequency.text().strip()) > 0:
            preferences.backup_frequency = int(round(float(backup_frequency)))
