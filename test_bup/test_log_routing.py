import logging
from pathlib import Path

import pytest

from bup import __application_name__, GithubBackup, UITypes
from bup.log_routing import set_detailed_file_logging

logger = logging.getLogger(__application_name__)


@pytest.fixture
def info_level_logger():
    original_level = logger.level
    logger.setLevel(logging.INFO)  # balsa isn't initialized in tests, so set the level the app would normally have
    yield logger
    logger.setLevel(original_level)
    set_detailed_file_logging(None)  # never leave a file handler behind for other tests


def _emit_record_from_file(file_name: str, message: str):
    """
    Send a log record through the application logger as if it came from the given source file.
    """
    pathname = str(Path("bup", file_name).absolute())
    record = logger.makeRecord(logger.name, logging.INFO, pathname, 1, message, (), None)
    logger.handle(record)


def test_records_route_to_per_source_files(tmp_path, info_level_logger):
    set_detailed_file_logging(tmp_path)
    _emit_record_from_file("s3_backup.py", 'aws s3 sync s3://my-bucket "C:\\backup\\s3\\my-bucket"')
    _emit_record_from_file("s3_backup.py", "my-bucket:download: s3://my-bucket/a.txt to a.txt")
    _emit_record_from_file("github_backup.py", 'git clone "owner/repo"')
    logger.info("an application level line")

    s3_text = Path(tmp_path, "s3.log").read_text(encoding="utf-8")
    assert "aws s3 sync s3://my-bucket" in s3_text  # the AWS CLI call itself
    assert "download: s3://my-bucket/a.txt" in s3_text  # its stdout
    assert "git clone" not in s3_text
    assert 'git clone "owner/repo"' in Path(tmp_path, "github.log").read_text(encoding="utf-8")
    assert "an application level line" in Path(tmp_path, "application.log").read_text(encoding="utf-8")
    assert not Path(tmp_path, "dynamodb.log").exists()  # files are created lazily - no records, no file


def test_engine_messages_route_by_backup_type(tmp_path, info_level_logger):
    set_detailed_file_logging(tmp_path)
    backup = GithubBackup(UITypes.cli, lambda s: None, lambda s: None, lambda s: None)
    backup.info_out('git pull "owner/repo" branch:"main"')
    assert "git pull" in Path(tmp_path, "github.log").read_text(encoding="utf-8")
    assert not Path(tmp_path, "application.log").exists()


def test_off_by_default_and_turn_off(tmp_path, info_level_logger):
    logger.info("before enabling")
    assert not Path(tmp_path, "application.log").exists()

    set_detailed_file_logging(tmp_path)
    logger.info("while enabled")
    set_detailed_file_logging(None)
    logger.info("after disabling")

    application_text = Path(tmp_path, "application.log").read_text(encoding="utf-8")
    assert "while enabled" in application_text
    assert "before enabling" not in application_text
    assert "after disabling" not in application_text


def test_blank_directory_means_off(tmp_path, info_level_logger):
    set_detailed_file_logging("   ")
    logger.info("blank directory line")
    assert not Path(tmp_path, "application.log").exists()


def test_changing_the_directory_moves_the_files(tmp_path, info_level_logger):
    first_directory = Path(tmp_path, "first")
    second_directory = Path(tmp_path, "second")
    set_detailed_file_logging(first_directory)
    logger.info("first directory line")
    set_detailed_file_logging(second_directory)
    logger.info("second directory line")

    first_text = Path(first_directory, "application.log").read_text(encoding="utf-8")
    second_text = Path(second_directory, "application.log").read_text(encoding="utf-8")
    assert "first directory line" in first_text
    assert "second directory line" not in first_text
    assert "second directory line" in second_text


def test_directory_is_created_if_missing(tmp_path, info_level_logger):
    new_directory = Path(tmp_path, "does", "not", "exist", "yet")
    set_detailed_file_logging(new_directory)
    logger.info("into a new directory")
    assert "into a new directory" in Path(new_directory, "application.log").read_text(encoding="utf-8")
