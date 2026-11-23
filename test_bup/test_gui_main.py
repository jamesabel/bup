"""
Tests for the start of the GUI (bup/gui/gui_main.py). All tests, fixtures and helpers in this file are AI-authored (Claude Code).

Nothing here starts the real GUI, sets up logging or contacts Sentry: gui_main() is given stand-ins for all of them.
"""

import importlib
import inspect
from unittest.mock import MagicMock

import pytest
from sentry_sdk.consts import ClientConstructor

# bup.gui.gui_main is the function (bup/gui/__init__.py imports it by that name), so the module is taken from the import system
gui_main_module = importlib.import_module("bup.gui.gui_main")

sentry_dsn = "https://public-key@sentry.invalid/1"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def gui_stand_ins(monkeypatch):
    """
    Stand-ins for everything gui_main() starts.
    :return: the stand-ins, by the name gui_main() uses for them
    """
    stand_ins = {name: MagicMock() for name in ("Balsa", "QApplication", "BupDialog", "set_detailed_file_logging", "get_gui_preferences")}
    for name, stand_in in stand_ins.items():
        monkeypatch.setattr(gui_main_module, name, stand_in)
    stand_ins["sentry_init"] = MagicMock()
    monkeypatch.setattr(gui_main_module.sentry_sdk, "init", stand_ins["sentry_init"])
    monkeypatch.delenv("USE_SENTRY", raising=False)
    monkeypatch.delenv("SENTRY_SDK_DSN", raising=False)
    return stand_ins


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_gui_main_shows_the_dialog_and_runs(gui_stand_ins):
    gui_main_module.gui_main()

    gui_stand_ins["Balsa"].return_value.init_logger.assert_called_once_with()
    gui_stand_ins["BupDialog"].return_value.show.assert_called_once_with()
    gui_stand_ins["QApplication"].return_value.exec_.assert_called_once_with()
    gui_stand_ins["sentry_init"].assert_not_called()  # Sentry is only used when the environment asks for it


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_gui_main_without_a_sentry_dsn(gui_stand_ins, monkeypatch):
    monkeypatch.setenv("USE_SENTRY", "true")

    gui_main_module.gui_main()

    gui_stand_ins["sentry_init"].assert_not_called()
    gui_stand_ins["QApplication"].return_value.exec_.assert_called_once_with()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_gui_main_sentry_options_are_ones_sentry_accepts(gui_stand_ins, monkeypatch):
    monkeypatch.setenv("USE_SENTRY", "true")
    monkeypatch.setenv("SENTRY_SDK_DSN", sentry_dsn)

    gui_main_module.gui_main()

    gui_stand_ins["sentry_init"].assert_called_once()
    sentry_options = gui_stand_ins["sentry_init"].call_args.kwargs
    assert sentry_options["dsn"] == sentry_dsn
    assert gui_stand_ins["Balsa"].return_value.sentry_dsn == sentry_dsn
    # sentry_sdk.init() raises a TypeError for an option that is not a parameter of ClientConstructor, which would stop the GUI from starting
    inspect.signature(ClientConstructor.__init__).bind(None, **sentry_options)
    # every traced transaction is profiled
    assert sentry_options["traces_sample_rate"] == 1.0
    assert sentry_options["profile_session_sample_rate"] == 1.0
    assert sentry_options["profile_lifecycle"] == "trace"
