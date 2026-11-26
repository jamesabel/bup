"""
The GUI's "About" tab.
"""

import platform
from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget, QTextBrowser
from balsa import get_logger

from bup import __url__, __author_url__, __version__, __application_name__

log = get_logger(__application_name__)

license_file_name = "LICENSE"  # the license of bup
gpl_license_file_name = "gpl-3.0.md"  # the text of the GPL, which is next to the license file


def find_license_path(directory: Path) -> Optional[Path]:
    """
    :param directory: the directory the license file is in, at any depth
    :return: the path of the license file, or None if there is none
    """
    return next((path for path in directory.rglob(license_file_name) if path.is_file()), None)


def get_gpl_text(license_path: Path) -> str:
    """
    :param license_path: the path of the license file
    :return: the text of the GPL, or where its file was looked for if it is not there
    """
    gpl_license_path = Path(license_path.parent, gpl_license_file_name)
    if gpl_license_path.is_file():
        return gpl_license_path.read_text()
    return f'GPL license file not found at "{gpl_license_path.absolute()}"'


def get_about_text() -> str:
    """
    :return: what the About tab shows, as Markdown: the versions of bup and of Python, the license, where bup comes from and the
      GPL. Without the license file (it is installed with the bup package) it only says that the file was not found.
    """
    license_file_parent_dir = Path(__file__).parent.parent  # the bup package
    license_path = find_license_path(license_file_parent_dir)
    if license_path is None:
        return f'License file not found at "{license_path}" ("{license_path}"), license_file_parent_dir="{license_file_parent_dir}".'
    return "".join(
        [
            f"### BUP ({__version__})\n\n",
            f"Python version: {platform.python_version()}\n\n",  # the Python this application is running on
            license_path.read_text(),
            "\n---\n",
            f"\nsource code: [{__url__}]({__url__})\n",
            f"\nauthor's web site: [{__author_url__}]({__author_url__})\n",
            "\n---\n",
            "\n---\n",
            get_gpl_text(license_path),
        ]
    )


class BupAbout(QWidget):
    """
    "About" tab - the versions of bup and of Python, the license, and where bup comes from.
    """

    def __init__(self):
        """
        Make the tab, with its text (see get_about_text()).
        """
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.about_text_widget = QTextBrowser()
        self.about_text_widget.setOpenExternalLinks(True)
        self.about_text_widget.setMarkdown(get_about_text())
        self.layout().addWidget(self.about_text_widget)
