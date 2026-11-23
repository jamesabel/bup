"""
Tests for the small functions that modules of bup share: how AWS is accessed (bup/aws_access.py) and the GUI helpers
(bup/gui/gui_util.py). All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import logging
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QLabel, QPushButton

from bup.aws_access import get_aws_access_kwargs, quiet_boto_logging
from bup.gui.gui_util import get_local_time_string, make_row, to_positive_int


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_aws_access_kwargs_from_the_preferences():
    preferences = MagicMock(aws_profile="my-profile", aws_access_key_id="AKID", aws_secret_access_key="SECRET", aws_region="us-west-2")

    assert get_aws_access_kwargs(preferences) == {"profile_name": "my-profile", "aws_access_key_id": "AKID", "aws_secret_access_key": "SECRET", "region_name": "us-west-2"}


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("not_set", [None, ""])
def test_aws_access_kwargs_of_preferences_that_are_not_set(not_set):
    # None leaves it to the AWS defaults (a blank profile name, for one, is not a profile)
    preferences = MagicMock(aws_profile=not_set, aws_access_key_id=not_set, aws_secret_access_key=not_set, aws_region=not_set)

    assert get_aws_access_kwargs(preferences) == {"profile_name": None, "aws_access_key_id": None, "aws_secret_access_key": None, "region_name": None}


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_aws_access_kwargs_for_another_region():
    preferences = MagicMock(aws_profile=None, aws_access_key_id=None, aws_secret_access_key=None, aws_region="us-west-2")

    assert get_aws_access_kwargs(preferences, "eu-west-1")["region_name"] == "eu-west-1"
    assert get_aws_access_kwargs(preferences, None)["region_name"] == "us-west-2"  # a region that could not be determined


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_boto_logging_is_quiet():
    for logger_name in ("boto3", "botocore"):
        logging.getLogger(logger_name).setLevel(logging.DEBUG)

    quiet_boto_logging()

    assert [logging.getLogger(logger_name).level for logger_name in ("boto3", "botocore")] == [logging.WARNING, logging.WARNING]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_make_row(qapp):
    button = QPushButton("Start")

    row = make_row("Name:", button)

    layout = row.layout()
    assert layout.count() == 3  # the label, the button and the stretch that takes the remaining width
    assert isinstance(layout.itemAt(0).widget(), QLabel)
    assert layout.itemAt(0).widget().text() == "Name:"
    assert layout.itemAt(1).widget() is button
    assert layout.itemAt(2).spacerItem() is not None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("value,expected", [(None, None), (0, None), (-5, None), (1, 1), (640, 640), (480.0, 480), ("320", 320)])
def test_to_positive_int(value, expected):
    assert to_positive_int(value) == expected


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_local_time_string():
    before = datetime.now().astimezone()
    time_string = get_local_time_string()
    seconds_string = get_local_time_string("seconds")

    assert datetime.fromisoformat(time_string).utcoffset() is not None  # local time, with its UTC offset
    assert abs((datetime.fromisoformat(time_string) - before).total_seconds()) < 60.0
    assert datetime.fromisoformat(seconds_string).microsecond == 0
    assert "." not in seconds_string
