"""
The status line of the GUI's main window: how a tab tells the user something in it.
"""

from PyQt5.QtCore import QObject, pyqtSignal


class StatusEmitter(QObject):
    """
    Has the signal that carries a message to the status line at the bottom of the main window.
    """

    status_signal = pyqtSignal(str)  # the message, which stays in the status line until the next one


# A tab emits its message here, and the main window shows it in its status line (in place of what was there). The tabs do not know the
# main window, so this is how they reach it.
status_emitter = StatusEmitter()
