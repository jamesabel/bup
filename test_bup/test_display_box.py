from unittest.mock import patch

from bup.gui.run_backup_widget import DisplayBox, max_text_lines


def test_creation(qapp):
    box = DisplayBox("Test", read_only=True)
    assert box.text_box.isReadOnly()
    assert box.text == []


def test_append_text(qapp):
    box = DisplayBox("Test", read_only=True)
    box.append_text("line one")
    assert len(box.text) == 1
    assert "line one" in box.text[0]
    # should contain a timestamp
    assert len(box.text[0]) > len("line one")


def test_fifo_limit(qapp):
    box = DisplayBox("Test", read_only=True)
    for i in range(max_text_lines + 50):
        box.append_text(f"line {i}")
    assert len(box.text) == max_text_lines
    # oldest lines should have been evicted; newest should be present
    assert "line 0" not in box.text[0]


def test_clear_text(qapp):
    box = DisplayBox("Test", read_only=True)
    box.append_text("something")
    box.clear_text()
    assert box.text == []
    assert box.text_box.toPlainText() == ""


def test_newest_first(qapp):
    box = DisplayBox("Test", read_only=True)
    box.append_text("first")
    box.append_text("second")
    rendered = box.text_box.toPlainText()
    # "second" should appear before "first" in the rendered text
    assert rendered.index("second") < rendered.index("first")
