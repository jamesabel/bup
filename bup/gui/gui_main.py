import logging
from PyQt5.QtWidgets import QApplication
from balsa import Balsa, HandlerType, get_logger

from bup import __application_name__, __author__
from bup.gui import BupDialog, get_gui_preferences

log = get_logger(__application_name__)


def gui_main():

    balsa = Balsa(__application_name__, __author__, gui=True, verbose=get_gui_preferences().verbose)
    balsa.init_logger()
    balsa.handlers[HandlerType.DialogBox].setLevel(logging.ERROR)  # don't pop up warnings

    try:
        app = QApplication([])
        bup_gui = BupDialog()
        bup_gui.show()
        app.exec_()
    except Exception as e:
        log.error(e)
        log.exception(e)
