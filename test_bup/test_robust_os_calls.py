from bup.robust_os_calls import rmdir, mkdirs


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


def test_mkdirs_creates_nested_directory(tmp_path):
    d = tmp_path / "new" / "nested" / "dir"
    assert not d.exists()
    mkdirs(d)
    assert d.exists()


def test_mkdirs_remove_first(tmp_path):
    d = tmp_path / "to_recreate"
    d.mkdir()
    (d / "existing_file.txt").write_text("content")
    mkdirs(d, remove_first=True)
    assert d.exists()
    assert not (d / "existing_file.txt").exists()


def test_mkdirs_idempotent(tmp_path):
    d = tmp_path / "existing"
    d.mkdir()
    mkdirs(d)  # should not raise
    assert d.exists()
