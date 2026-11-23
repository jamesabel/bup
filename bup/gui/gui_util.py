"""
Small helpers that the GUI's widgets share.
"""

from datetime import datetime
from typing import Optional, Union

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget


def make_row(*items: Union[QWidget, str]) -> QWidget:
    """
    Make a widget that holds widgets in a row, left to right, with the remaining width left empty.

    :param items: the widgets of the row. A string is a label with that text.
    :return: the row
    """
    row = QWidget()
    row.setLayout(QHBoxLayout())
    for item in items:
        row.layout().addWidget(QLabel(item) if isinstance(item, str) else item)
    row.layout().addStretch()
    return row


def to_positive_int(value) -> Optional[int]:
    """
    A saved size (e.g. the height of a pane, from the preferences) as a size that can be restored.

    :param value: the saved value, which is None if it was never saved
    :return: the value as an int, or None if there is nothing to restore: it was never saved, or it is not positive (e.g. the user
      reduced a pane to nothing, and it has to come up visible)
    """
    if value is None or int(value) <= 0:
        return None
    return int(value)


def get_local_time_string(timespec: str = "auto") -> str:
    """
    :param timespec: the precision of the time, as for datetime.isoformat() (e.g. "seconds")
    :return: the time now as an ISO 8601 string in local time, with the UTC offset
    """
    return datetime.now().astimezone().isoformat(timespec=timespec)
