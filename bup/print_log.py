from balsa import get_logger

from bup import __application_name__

log = get_logger(__application_name__)


def print_log(s):
    log.info(s)
    print(f"\r{s}", end="", flush=True)
