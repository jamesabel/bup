import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, TextIO, Union

from bup import __application_name__, BackupTypes

log_line_format = "%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(threadName)s %(message)s"


class LogSources(Enum):
    s3 = "AWS S3"
    dynamodb = "DynamoDB"
    github = "GitHub"
    application = "Application"


# records stamped with a backup type by BupBase (the info_out/warning_out/error_out path, whose records all originate in bup_base.py)
log_sources_by_backup_type = {
    BackupTypes.S3: LogSources.s3,
    BackupTypes.DynamoDB: LogSources.dynamodb,
    BackupTypes.github: LogSources.github,
}

# records logged directly (not via BupBase) are routed by the source file they were logged from
# (all of bup logs to the same application logger)
log_sources_by_filename = {
    "s3_backup.py": LogSources.s3,
    "aws_cli.py": LogSources.s3,
    "dynamodb_backup.py": LogSources.dynamodb,
    "github_backup.py": LogSources.github,
}


def get_log_source(record: logging.LogRecord) -> LogSources:
    backup_type = getattr(record, "backup_type", None)
    if backup_type in log_sources_by_backup_type:
        return log_sources_by_backup_type[backup_type]
    return log_sources_by_filename.get(record.filename, LogSources.application)


class DetailedFileLogHandler(logging.Handler):
    """
    Writes every log record to a file per log source in the given directory (s3.log, dynamodb.log, github.log, application.log),
    so each backup type's full details (e.g. the AWS CLI calls and their stdout/stderr) are captured separately.
    """

    def __init__(self, directory: Union[str, Path]):
        super().__init__()
        self.directory = Path(directory)
        self.setFormatter(logging.Formatter(log_line_format))
        self.files: Dict[LogSources, TextIO] = {}

    def get_log_file_path(self, log_source: LogSources) -> Path:
        return Path(self.directory, f"{log_source.name}.log")

    def emit(self, record: logging.LogRecord):
        log_source = get_log_source(record)
        try:
            file = self.files.get(log_source)
            if file is None:
                # open lazily so files and directories only appear once there is something to write
                self.directory.mkdir(parents=True, exist_ok=True)
                file = open(self.get_log_file_path(log_source), "a", encoding="utf-8")
                self.files[log_source] = file
            file.write(f"{self.format(record)}\n")
            file.flush()  # the point of this log is diagnosing problems - don't lose lines on a crash
        except OSError:
            self.handleError(record)

    def close(self):
        self.acquire()
        try:
            for file in self.files.values():
                try:
                    file.close()
                except OSError:
                    pass  # closing on teardown - nothing useful to do about a failed close
            self.files = {}
        finally:
            self.release()
        super().close()


_detailed_file_log_handler: Optional[DetailedFileLogHandler] = None


def set_detailed_file_logging(directory: Optional[Union[str, Path]]):
    """
    Write detailed logs to the given directory (one file per log source), replacing any previous detailed log directory.
    None (or blank) turns detailed file logging off.
    """
    global _detailed_file_log_handler
    logger = logging.getLogger(__application_name__)
    if _detailed_file_log_handler is not None:
        logger.removeHandler(_detailed_file_log_handler)
        _detailed_file_log_handler.close()
        _detailed_file_log_handler = None
    directory_string = "" if directory is None else str(directory).strip()
    if len(directory_string) > 0:
        _detailed_file_log_handler = DetailedFileLogHandler(Path(directory_string))
        _detailed_file_log_handler.setLevel(logging.DEBUG)  # capture everything the logger's own level lets through
        logger.addHandler(_detailed_file_log_handler)
