"""
Tests for how a backup's output reaches its caller when the UI is the GUI (through Qt signals, not direct calls).
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import pytest

from bup import BupBase, UITypes


class _NoOpBackup(BupBase):
    def run_backup(self):
        pass


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("ui_type", [UITypes.gui, UITypes.cli])
def test_output_reaches_the_caller(qapp, ui_type):
    # In the GUI the output goes through a signal, so that a backup's thread never touches a widget. Emitted from the thread the
    # backup object lives in (as here), the signal is delivered straight away.
    infos, warnings, errors = [], [], []
    backup = _NoOpBackup(ui_type, infos.append, warnings.append, errors.append)

    backup.info_out("an info")
    backup.warning_out("a warning")
    backup.error_out("an error")
    backup.error_out("another error")

    assert infos == ["an info"]
    assert warnings == ["a warning"]
    assert errors == ["an error", "another error"]
    assert backup.error_count == 2
