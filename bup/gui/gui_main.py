from PyQt5.QtWidgets import QApplication
from balsa import Balsa
from ismain import is_main

from bup import __application_name__, __author__
from bup.gui import BupDialog


def gui_main():
    app = QApplication([])
    bup_gui = BupDialog()
    bup_gui.show()
    app.exec_()


if is_main():
    balsa = Balsa(__application_name__, __author__)
    balsa.init_logger()
    gui_main()
