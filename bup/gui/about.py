from pathlib import Path

from PyQt5.QtWidgets import QVBoxLayout, QWidget, QTextEdit

from bup import __url__, __author_url__


class BupAbout(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        about_text = Path("LICENSE").read_text()
        about_text += "\n---\n"
        about_text += f"\nsource code: {__url__}\n"
        about_text += f"\nauthor's web site: {__author_url__}\n"
        about_text += "\n---\n"
        about_text += Path("gpl-3.0.md").read_text()

        self.about_text_widget = QTextEdit()
        self.about_text_widget.setMarkdown(about_text)
        self.about_text_widget.setReadOnly(True)
        self.layout().addWidget(self.about_text_widget)
