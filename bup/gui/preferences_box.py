from pathlib import Path

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QGroupBox, QTextEdit, QLabel, QFileDialog, QGridLayout, QLineEdit
from PyQt5.QtGui import QFontMetrics

from bup.gui import GUIPreferences


class PreferencesBox(QGroupBox):
    def __init__(self):
        super().__init__("Preferences")
        self.setLayout(QGridLayout())

        self.backup_directory_box = QLineEdit()

        self.select_backup_directory_button = QPushButton("Select Backup Directory")
        self.select_backup_directory_button.clicked.connect(self.select_backup_directory)

        self.layout().addWidget(QLabel("Backup Directory:"), 0, 0)
        self.layout().addWidget(self.backup_directory_box, 0, 1)
        self.layout().addWidget(self.select_backup_directory_button, 0, 2)

        self.aws_profile_box = QLineEdit()
        self.aws_access_key_id_box = QLineEdit()
        self.aws_secret_access_key_box = QLineEdit()
        self.aws_secret_access_key_box.setEchoMode(QLineEdit.Password)
        self.aws_show_button = QPushButton("Show")
        self.aws_save_button = QPushButton("Save")
        self.aws_cancel_button = QPushButton("Cancel")

        self.layout().addWidget(QLabel(), 1, 0)

        aws_iam_row = 2
        self.layout().addWidget(QLabel("AWS Profile"), aws_iam_row, 0)
        self.layout().addWidget(self.aws_profile_box, aws_iam_row, 1)
        self.layout().addWidget(QLabel("AWS Access Key ID"), aws_iam_row, 2)
        self.layout().addWidget(self.aws_access_key_id_box, aws_iam_row, 3)
        self.layout().addWidget(QLabel("AWS Secret Access Key"), aws_iam_row, 4)
        self.layout().addWidget(self.aws_secret_access_key_box, aws_iam_row, 5)
        self.layout().addWidget(self.aws_show_button, aws_iam_row, 6)
        self.layout().addWidget(self.aws_save_button, aws_iam_row, 7)
        self.layout().addWidget(self.aws_cancel_button, aws_iam_row, 8)

        self.load_preferences()

    def load_preferences(self):
        preferences = GUIPreferences()

        if (backup_path := preferences.get_backup_directory()) is None:
            self.backup_directory_box.setText('press "Select Backup Directory" button to set ------>')
        else:
            self.backup_directory_box.setText(str(backup_path))

    def select_backup_directory(self):
        new_backup_directory = QFileDialog.getExistingDirectory(self, "Select Backup Directory")
        if new_backup_directory is not None and len(new_backup_directory) > 0:
            self.backup_directory_box.setText(new_backup_directory)
            GUIPreferences().set_backup_directory(Path(new_backup_directory))
