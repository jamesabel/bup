
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QGroupBox, QTextEdit, QLabel, QFileDialog, QGridLayout, QLineEdit, QSpacerItem, QSizePolicy

from bup import __application_name__, __author__
from bup.gui import BupPreferences


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
        self.backup_directory_widget.adjustSize()  # all done adding - figure out what the height should be
        self.backup_directory_widget.setMaximumHeight(self.backup_directory_widget.minimumHeight())
        self.layout().addWidget(self.backup_directory_widget)
        self.layout().addWidget(QLabel())  # space

        # AWS Credentials
        # profile
        self.layout().addWidget(QLabel("Either provide an AWS Profile or an AWS Access Key ID/AWS Secret Access Key pair:"))
        self.aws_profile_widget = QWidget()
        self.aws_profile_widget.setLayout(QHBoxLayout())
        self.aws_profile_widget.layout().addWidget(QLabel("AWS Profile:"))
        self.aws_profile_line_edit = PreferencesLineEdit()
        self.aws_profile_line_edit.textChanged.connect(self.aws_profile_changed)
        self.aws_profile_widget.layout().addWidget(self.aws_profile_line_edit)
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
        self.layout().addWidget(self.aws_key_widget)
        self.layout().addWidget(QLabel())  # space
        # region
        self.aws_region_widget = QWidget()
        self.aws_region_widget.setLayout(QHBoxLayout())
        self.aws_region_widget.layout().addWidget(QLabel("AWS Region:"))
        self.aws_region_line_edit = PreferencesLineEdit()
        self.aws_region_line_edit.textChanged.connect(self.aws_region_changed)
        self.aws_region_widget.layout().addWidget(self.aws_region_line_edit)
        self.layout().addWidget(self.aws_region_widget)

        self.layout().addStretch()  # bottom padding

        self.load_preferences()

    def load_preferences(self):
        preferences = BupPreferences(__application_name__, __author__)
        self.backup_directory_line_edit.setText(preferences.backup_directory)
        self.aws_profile_line_edit.setText(preferences.aws_profile)
        self.aws_access_key_id_line_edit.setText(preferences.aws_access_key_id)
        self.aws_secret_access_key_line_edit.setText(preferences.aws_secret_access_key)
        self.aws_region_line_edit.setText(preferences.aws_region)

    def select_backup_directory(self):
        new_backup_directory = QFileDialog.getExistingDirectory(self, "Select Backup Directory")
        if new_backup_directory is not None and len(new_backup_directory) > 0:
            self.backup_directory_line_edit.setText(new_backup_directory)

    def backup_directory_changed(self):
        BupPreferences(__application_name__, __author__).backup_directory = self.backup_directory_line_edit.text()

    def aws_profile_changed(self):
        BupPreferences(__application_name__, __author__).aws_profile = self.aws_profile_line_edit.text()

    def aws_access_key_id_changed(self):
        BupPreferences(__application_name__, __author__).aws_access_key_id = self.aws_access_key_id_line_edit.text()

    def aws_secret_access_key_changed(self):
        BupPreferences(__application_name__, __author__).aws_secret_access_key = self.aws_secret_access_key_line_edit.text()

    def aws_secret_access_key_visible_clicked(self):
        if self.aws_secret_access_key_line_edit.echoMode() == PreferencesLineEdit.Password:
            self.aws_show_button.setText("Hide")
            self.aws_secret_access_key_line_edit.setEchoMode(PreferencesLineEdit.Normal)
        else:
            self.aws_show_button.setText("Show")
            self.aws_secret_access_key_line_edit.setEchoMode(PreferencesLineEdit.Password)

    def aws_region_changed(self):
        BupPreferences(__application_name__, __author__).aws_region = self.aws_region_line_edit.text()
