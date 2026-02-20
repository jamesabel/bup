from pathlib import Path

from PyQt5.QtWidgets import QVBoxLayout, QWidget, QTextBrowser
from balsa import get_logger

from bup import __url__, __author_url__, __version__, __application_name__

log = get_logger(__application_name__)


class BupAbout(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        # locate the license files
        license_file_name = "LICENSE"
        gpl_license_file_name = "gpl-3.0.md"

        license_file_parent_dir = Path(__file__).parent.parent
        license_path = next((p for p in license_file_parent_dir.rglob(license_file_name) if p.is_file()), None)
        if license_path is not None:
            gpl_license_path = Path(license_path.parent, gpl_license_file_name)
            gpl_text = gpl_license_path.read_text() if gpl_license_path.exists() and gpl_license_path.is_file() else f'GPL license file not found at "{gpl_license_path.absolute()}"'
        else:
            gpl_text = ""

        if license_path is not None and license_path.exists() and license_path.is_file():

            about_text = f"### BUP ({__version__})\n\n"
            about_text += license_path.read_text()
            about_text += "\n---\n"
            about_text += f"\nsource code: [{__url__}]({__url__})\n"
            about_text += f"\nauthor's web site: [{__author_url__}]({__author_url__})\n"
            about_text += "\n---\n"
            about_text += "\n---\n"
            about_text += gpl_text

            self.about_text_widget = QTextBrowser()
            self.about_text_widget.setOpenExternalLinks(True)
            self.about_text_widget.setMarkdown(about_text)
            self.layout().addWidget(self.about_text_widget)

        else:
            if license_path is None:
                absolute_license_path = None
            else:
                absolute_license_path = license_path.absolute()

            error_message = f'License file not found at "{license_path}" ("{absolute_license_path}"), license_file_parent_dir="{license_file_parent_dir}".'
            # log.info(error_message)  # not fatal
            self.about_text_widget = QTextBrowser()
            self.about_text_widget.setMarkdown(error_message)
            self.layout().addWidget(self.about_text_widget)
