from bup.robust_os_calls import rmdir


def test_rmdir_success(tmp_path):
    d = tmp_path / "to_delete"
    d.mkdir()
    assert d.exists()
    assert rmdir(d) is True
    assert not d.exists()


def test_rmdir_nonexistent_returns_true(tmp_path):
    d = tmp_path / "does_not_exist"
    assert not d.exists()
    assert rmdir(d) is True


def test_rmdir_with_nested_files(tmp_path):
    d = tmp_path / "dir_with_files"
    d.mkdir()
    (d / "file.txt").write_text("hello")
    (d / "subdir").mkdir()
    (d / "subdir" / "nested.txt").write_text("nested")
    assert rmdir(d) is True
    assert not d.exists()
