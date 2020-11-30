from pprint import pprint

from ismain import is_main
from PyQt5.Qt import QApplication

from bup.gui import PreferencesStore, PreferencesWidget


def test_preferences():

    # todo: this currently just tests what's ever in the preferences, which can be nothing - in the future add writing test data

    gui_preferences = PreferencesStore()
    pprint(gui_preferences)

    app = QApplication([])  # needed for the preferences widget
    preferences_widget = PreferencesWidget()
    pprint(preferences_widget)

    assert gui_preferences.items() == preferences_widget.items()


if is_main():
    test_preferences()
