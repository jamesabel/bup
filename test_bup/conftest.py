import sys

import pytest
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Single QApplication instance for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
