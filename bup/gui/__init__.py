"""
The graphical user interface of bup: the main window (BupDialog) and a widget per tab.

The order of the imports below matters: a widget imports what it needs from this package, which has to be here already.
"""

from .preferences_widget import PreferencesWidget, get_gui_preferences
from .about import BupAbout
from .gui_icon import get_icon_path
from .log_widget import LogWidget
from .transfer_widget import TransferWidget
from .history_widget import HistoryWidget
from .run_backup_widget import RunBackupWidget
from .bup_dialog import BupDialog
from .gui_main import gui_main
