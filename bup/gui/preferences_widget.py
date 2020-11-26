from pathlib import Path

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QGroupBox, QTextEdit, QLabel, QFileDialog, QGridLayout, QLineEdit

from bup.gui import GUIPreferences


class PreferencesWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        # backup directory
        self.backup_directory_group_box = QGroupBox(title="Backup Directory")
        self.backup_directory_group_box.setLayout(QHBoxLayout())
        self.backup_directory_box = QLineEdit()
        self.select_backup_directory_button = QPushButton("Select Backup Directory")
        self.select_backup_directory_button.clicked.connect(self.select_backup_directory)
        self.backup_directory_group_box.layout().addWidget(QLabel("Backup Directory:"))
        self.backup_directory_group_box.layout().addWidget(self.backup_directory_box)
        self.backup_directory_group_box.layout().addWidget(self.select_backup_directory_button)
        self.backup_directory_group_box.adjustSize()  # all done adding - figure out what the height should be
        self.backup_directory_group_box.setMaximumHeight(self.backup_directory_group_box.minimumHeight())
        self.layout().addWidget(self.backup_directory_group_box)

        # AWS
        self.aws_group_box = QGroupBox(title="AWS (either Profile or Access Key ID/Secret Access Key)")
        self.aws_group_box.setLayout(QHBoxLayout())
        self.aws_profile_box = QLineEdit()
        self.aws_access_key_id_box = QLineEdit()
        self.aws_secret_access_key_box = QLineEdit()
        self.aws_secret_access_key_box.setEchoMode(QLineEdit.Password)
        self.aws_show_button = QPushButton("Show")
        self.aws_save_button = QPushButton("Save")
        self.aws_cancel_button = QPushButton("Cancel")
        self.aws_group_box.layout().addWidget(QLabel("AWS Profile"))
        self.aws_group_box.layout().addWidget(self.aws_profile_box)
        self.aws_group_box.layout().addWidget(QLabel("AWS Access Key ID"))
        self.aws_group_box.layout().addWidget(self.aws_access_key_id_box)
        self.aws_group_box.layout().addWidget(QLabel("AWS Secret Access Key"))
        self.aws_group_box.layout().addWidget(self.aws_secret_access_key_box)
        self.aws_group_box.layout().addWidget(self.aws_show_button)
        self.aws_group_box.layout().addWidget(self.aws_save_button)
        self.aws_group_box.layout().addWidget(self.aws_cancel_button)
        self.aws_group_box.adjustSize()  # all done adding - figure out what the height should be
        self.aws_group_box.setMaximumHeight(self.aws_group_box.minimumHeight())
        self.layout().addWidget(self.aws_group_box)

        self.layout().addWidget(QLabel())  # bottom padding

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
