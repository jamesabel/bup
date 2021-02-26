import time
import random

from ismain import is_main
from balsa import get_logger, Balsa

from bup import print_log, __application_name__, __author__

log = get_logger(__application_name__)


def test_print_log():
    start = 11
    for value in range(start, 0, -1):
        if value < start - 1:
            time.sleep(1)
        print_log(f"{value-1}" * int(round(50.0 * random.random())))


if is_main():
    balsa = Balsa(__application_name__, __author__)
    balsa.init_logger()
    test_print_log()
