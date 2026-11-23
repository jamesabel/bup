"""
The graphical user interface of bup.
"""

import os

from PyQt5.QtWidgets import QApplication
from balsa import Balsa, get_logger
import sentry_sdk
from dotenv import load_dotenv, find_dotenv
from tobool import to_bool_strict

from bup import __application_name__, __author__
from bup.log_routing import set_detailed_file_logging
from bup.gui import BupDialog, get_gui_preferences

load_dotenv(find_dotenv())

log = get_logger(__application_name__)


def gui_main():
    """
    Run the GUI: set up logging (and Sentry, if the environment asks for it), show the main window and run until it is closed.
    """

    # Balsa is an attrs class in the older "@attrs" spelling, which ty does not take for one (it sees a class with no arguments)
    balsa = Balsa(__application_name__, __author__, gui=True, verbose=get_gui_preferences().verbose)  # ty: ignore[too-many-positional-arguments, unknown-argument]
    balsa.use_sentry = to_bool_strict(os.environ.get("USE_SENTRY", "false"))
    if balsa.use_sentry:
        sentry_dsn = os.getenv("SENTRY_SDK_DSN", "")
        if sentry_dsn:
            # every transaction is traced, and profiled for as long as it runs
            sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=1.0, profile_session_sample_rate=1.0, profile_lifecycle="trace")
            balsa.sentry_dsn = sentry_dsn
    balsa.init_logger()

    gui_preferences = get_gui_preferences()
    set_detailed_file_logging(gui_preferences.detailed_log_directory, gui_preferences.detailed_log_file_size_limit_mb)

    app = QApplication([])
    bup_gui = BupDialog()
    bup_gui.show()
    app.exec_()
