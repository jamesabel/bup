
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QGroupBox, QTextEdit, QLabel, QFileDialog, QGridLayout, QLineEdit, QSpacerItem, QSizePolicy

from bup.gui import GUIPreferences


class PreferencesWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        # backup directory
        self.backup_directory_widget = QWidget()
        self.backup_directory_widget.setLayout(QHBoxLayout())
        self.backup_directory_line_edit = QLineEdit()
        self.backup_directory_line_edit.textChanged.connect(self.new_backup_directory)
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
        self.aws_profile_line_edit = QLineEdit()
        self.aws_profile_widget.layout().addWidget(self.aws_profile_line_edit)
        self.layout().addWidget(self.aws_profile_widget)
        or_label = QLabel("or")  # italicize "or"
        or_font = or_label.font()
        or_font.setItalic(True)
        or_label.setFont(or_font)
        self.layout().addWidget(or_label)
        # access key ID and secret access key
        # todo: do we need an AWS region?
        self.aws_key_widget = QWidget()
        self.aws_key_widget.setLayout(QHBoxLayout())
        self.aws_key_widget.layout().addWidget(QLabel("AWS Access Key ID:"))
        self.aws_access_key_id_line_edit = QLineEdit()
        self.aws_key_widget.layout().addWidget(self.aws_access_key_id_line_edit)
        self.aws_key_widget.layout().addWidget(QLabel("AWS Secret Access Key:"))
        self.aws_secret_access_key_line_edit = QLineEdit()
        self.aws_secret_access_key_line_edit.setEchoMode(QLineEdit.Password)
        self.aws_key_widget.layout().addWidget(self.aws_secret_access_key_line_edit)
        self.aws_show_button = QPushButton("Show")
        self.aws_key_widget.layout().addWidget(self.aws_show_button)
        self.layout().addWidget(self.aws_key_widget)
        self.layout().addWidget(QLabel())  # space

        self.layout().addStretch()  # bottom padding

        self.load_preferences()

    def load_preferences(self):
        preferences = GUIPreferences()
        if (backup_path := preferences.get_backup_directory()) is None or len(backup_path.strip()) < 1:
            self.backup_directory_line_edit.setText("")
        else:
            self.backup_directory_line_edit.setText(str(backup_path))

    def select_backup_directory(self):
        new_backup_directory = QFileDialog.getExistingDirectory(self, "Select Backup Directory")
        if new_backup_directory is not None and len(new_backup_directory) > 0:
            self.backup_directory_line_edit.setText(new_backup_directory)

    def new_backup_directory(self):
        gui_preferences = GUIPreferences()
        gui_preferences.set_backup_directory(self.backup_directory_line_edit.text())
