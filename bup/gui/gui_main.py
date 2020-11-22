from PyQt5.QtWidgets import QApplication

from bup.gui import BupDialog


def gui_main():
    app = QApplication([])
    bup_gui = BupDialog()
    bup_gui.show()
    app.exec_()
