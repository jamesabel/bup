from PyQt5.QtWidgets import QApplication
from balsa import Balsa

from bup import __application_name__, __author__, get_preferences
from bup.gui import BupDialog


def gui_main():

    balsa = Balsa(__application_name__, __author__, verbose=get_preferences().verbose)
    balsa.init_logger()

    app = QApplication([])
    bup_gui = BupDialog()
    bup_gui.show()
    app.exec_()
