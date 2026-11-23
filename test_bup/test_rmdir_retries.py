"""
Tests for what bup's rmdir() does when a directory can not be removed straight away.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import os
import stat
from unittest.mock import patch, MagicMock

from bup.robust_os_calls import _remove_readonly_onexc, rmdir, rmdir_attempts


def _make_directory(tmp_path):
    directory = tmp_path / "to_delete"
    directory.mkdir()
    (directory / "file.txt").write_text("hello")
    return directory


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rmdir_removes_a_read_only_file(tmp_path):
    # e.g. the object files of a git repository are read-only, which on Windows keeps them from being removed
    directory = _make_directory(tmp_path)
    os.chmod(directory / "file.txt", stat.S_IREAD)

    assert rmdir(directory) is True
    assert not directory.exists()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_read_only_handler_makes_a_directory_tree_writable_and_tries_again(tmp_path):
    directory = _make_directory(tmp_path)
    os.chmod(directory / "file.txt", stat.S_IREAD)
    try_again = MagicMock()

    _remove_readonly_onexc(try_again, str(directory), PermissionError("read-only"))

    assert os.access(directory / "file.txt", os.W_OK)
    try_again.assert_called_once_with(str(directory))


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rmdir_tries_again_until_the_directory_is_removed(tmp_path):
    # e.g. a file that another process (a virus scanner, an indexer) has open for a moment
    directory = _make_directory(tmp_path)
    real_rmtree = __import__("shutil").rmtree
    failures = [PermissionError("in use"), FileNotFoundError("gone meanwhile"), OSError("something else")]

    def flaky_rmtree(path, **kwargs):
        if failures:
            raise failures.pop(0)
        real_rmtree(path, **kwargs)

    with patch("bup.robust_os_calls.shutil.rmtree", side_effect=flaky_rmtree) as mock_rmtree, patch("bup.robust_os_calls.time.sleep") as mock_sleep:
        assert rmdir(directory) is True

    assert not directory.exists()
    assert mock_rmtree.call_count == 4
    assert mock_sleep.call_count == 3  # a wait after every failure


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rmdir_gives_up_and_says_so(tmp_path, caplog):
    directory = _make_directory(tmp_path)

    with patch("bup.robust_os_calls.shutil.rmtree", side_effect=PermissionError("in use")) as mock_rmtree, patch("bup.robust_os_calls.time.sleep"):
        assert rmdir(directory) is False

    assert directory.exists()
    assert mock_rmtree.call_count == rmdir_attempts == 10
    # The caller reports the failure (as an error, where it is one), so here it is a warning and not a second error.
    assert [record.levelname for record in caplog.records if "attempts" in record.getMessage()] == ["WARNING"]
    assert not any(record.levelname == "ERROR" for record in caplog.records)
