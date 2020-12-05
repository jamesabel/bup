from PyQt5.QtWidgets import QApplication
from balsa import Balsa

from bup import __application_name__, __author__
from bup.gui import BupDialog, get_gui_preferences


def gui_main():

    # even though this is a GUI app, we don't use Balsa's GUI feature since we're already outputting to a GUI
    balsa = Balsa(__application_name__, __author__, verbose=get_gui_preferences().verbose)
    balsa.init_logger()

    app = QApplication([])
    bup_gui = BupDialog()
    bup_gui.show()
    app.exec_()
