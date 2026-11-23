"""
The user interfaces of bup.
"""

from enum import Enum


class UITypes(Enum):
    """
    A user interface. Each has its own preferences.
    """

    cli = "cli"
    gui = "gui"
