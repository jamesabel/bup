from pathlib import Path

from PyQt5.QtWidgets import QVBoxLayout, QWidget, QTextBrowser

from bup import __url__, __author_url__, __version__


class BupAbout(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        about_text = f"### BUP ({__version__})\n\n"
        about_text += Path("LICENSE").read_text()
        about_text += "\n---\n"
        about_text += f"\nsource code: [{__url__}]({__url__})\n"
        about_text += f"\nauthor's web site: [{__author_url__}]({__author_url__})\n"
        about_text += "\n---\n"
        about_text += "\n---\n"
        about_text += Path("gpl-3.0.md").read_text()

        self.about_text_widget = QTextBrowser()
        self.about_text_widget.setOpenExternalLinks(True)
        self.about_text_widget.setMarkdown(about_text)
        self.layout().addWidget(self.about_text_widget)
