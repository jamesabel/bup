import logging
import os

from PyQt5.QtWidgets import QApplication
from balsa import Balsa, HandlerType, get_logger
import sentry_sdk
from dotenv import load_dotenv, find_dotenv

from bup import __application_name__, __author__
from bup.gui import BupDialog, get_gui_preferences

load_dotenv(find_dotenv())

log = get_logger(__application_name__)


def gui_main():

    sentry_sdn = os.getenv("SENTRY_SDK_DSN", "https://62697cf1309de18a5bc087a14d2c373e@o69774.ingest.us.sentry.io/4507660750356480")
    sentry_sdk.init(dsn=sentry_sdn, traces_sample_rate=1.0, profiles_sample_rate=1.0)

    balsa = Balsa(__application_name__, __author__, gui=True, verbose=get_gui_preferences().verbose)
    balsa.use_sentry = True
    balsa.sentry_dsn = sentry_sdn
    balsa.init_logger()
    balsa.handlers[HandlerType.DialogBox].setLevel(logging.ERROR)  # don't pop up warnings

    app = QApplication([])
    bup_gui = BupDialog()
    bup_gui.show()
    app.exec_()
