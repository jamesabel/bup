from pprint import pprint

from ismain import is_main
from PyQt5.Qt import QApplication

from bup import BupPreferences, __author__, get_preferences, UITypes
from bup.gui import PreferencesWidget


def test_preferences():

    # todo: this currently just tests what's ever in the preferences, which can be nothing - in the future add writing test data
    gui_preferences = get_preferences(UITypes.cli)
    pprint(gui_preferences)


if is_main():
    test_preferences()
