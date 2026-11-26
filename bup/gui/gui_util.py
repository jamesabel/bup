"""
Small helpers that the GUI's widgets share.
"""

from datetime import datetime
from typing import List, Optional, Sequence, Union

from PyQt5.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QWidget


def make_row(*items: Union[QWidget, str]) -> QWidget:
    """
    Make a widget that holds widgets in a row, left to right, with the remaining width left empty.

    :param items: the widgets of the row. A string is a label with that text.
    :return: the row
    """
    row = QWidget()
    layout = QHBoxLayout()
    row.setLayout(layout)
    for item in items:
        layout.addWidget(QLabel(item) if isinstance(item, str) else item)
    layout.addStretch()
    return row


def make_table(column_titles: Sequence[str]) -> QTableWidget:
    """
    Make a table that shows rows of text: it has no rows yet, the user can not edit it, and every column is as wide as its contents.

    :param column_titles: the title of each column
    :return: the table
    """
    table = QTableWidget(0, len(column_titles))
    table.setHorizontalHeaderLabels(column_titles)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    return table


def set_table_row(table: QTableWidget, row: int, row_text: Sequence[str]) -> List[QTableWidgetItem]:
    """
    Set the text of a row of a table, which has to be a row of the table already.

    :param table: the table
    :param row: the index of the row
    :param row_text: the text of each column of the row, from the first column on
    :return: the items that were made, one per column that was given
    """
    items = [QTableWidgetItem(text) for text in row_text]
    for column, item in enumerate(items):
        table.setItem(row, column, item)
    return items


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
