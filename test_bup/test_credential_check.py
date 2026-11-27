"""
Tests for the checks of the credentials in the preferences (bup/credential_check.py), and for the buttons of the GUI's Preferences
tab that run them.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
No test makes a request to AWS or GitHub: the accesses are stand-ins.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
from github3.exceptions import AuthenticationFailed, ConnectionError as GitHubConnectionError, ForbiddenError

from bup.credential_check import CredentialCheck, check_dynamodb_credentials, check_github_credentials, check_s3_credentials
from bup.gui import preferences_widget
from bup.gui.preferences_widget import CredentialCheckButton, PreferencesWidget
from bup.gui.status_line import status_emitter

github_token = "ghp_not_a_real_token"


def _make_preferences(**preferences) -> MagicMock:
    return MagicMock(**{"aws_profile": "my-profile", "aws_access_key_id": None, "aws_secret_access_key": None, "aws_region": "us-west-2", "github_token": github_token, **preferences})


def _make_github_response(status_code: int, message: str) -> MagicMock:
    response = MagicMock(status_code=status_code)
    response.json.return_value = {"message": message}
    return response


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_credentials_that_can_list_the_buckets_are_ok():
    with patch("bup.credential_check.S3Access") as mock_s3_access:
        mock_s3_access.return_value.bucket_list.return_value = ["bucket-a", "bucket-b", "bucket-c"]

        credential_check = check_s3_credentials(_make_preferences())

    assert credential_check == CredentialCheck(True, "OK - 3 buckets")
    # the access is made with the credentials and region of the preferences
    mock_s3_access.assert_called_once_with(profile_name="my-profile", aws_access_key_id=None, aws_secret_access_key=None, region_name="us-west-2")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_credentials_that_aws_does_not_accept_are_not_ok():
    with patch("bup.credential_check.S3Access") as mock_s3_access:
        mock_s3_access.return_value.bucket_list.side_effect = ClientError(
            {"Error": {"Code": "InvalidAccessKeyId", "Message": "The AWS Access Key Id you provided does not exist"}}, "ListBuckets"
        )

        credential_check = check_s3_credentials(_make_preferences())

    assert not credential_check.ok
    assert credential_check.message.startswith("could not list the S3 buckets : ")
    assert "InvalidAccessKeyId" in credential_check.message


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_check_with_an_aws_profile_that_does_not_exist_is_not_ok():
    with patch("bup.credential_check.S3Access", side_effect=ProfileNotFound(profile="no-such-profile")):
        credential_check = check_s3_credentials(_make_preferences(aws_profile="no-such-profile"))

    assert not credential_check.ok
    assert "no-such-profile" in credential_check.message


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("aws_region,expected_message", [("us-west-2", "OK - 2 tables in us-west-2"), (None, "OK - 2 tables"), ("", "OK - 2 tables")])
def test_dynamodb_credentials_that_can_list_the_tables_are_ok(aws_region, expected_message):
    with patch("bup.credential_check.DynamoDBAccess") as mock_dynamodb_access:
        mock_dynamodb_access.return_value.get_table_names.return_value = ["customers", "orders"]

        credential_check = check_dynamodb_credentials(_make_preferences(aws_region=aws_region))

    assert credential_check == CredentialCheck(True, expected_message)
    mock_dynamodb_access.assert_called_once_with(profile_name="my-profile", aws_access_key_id=None, aws_secret_access_key=None, region_name=aws_region or None)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dynamodb_check_without_credentials_is_not_ok():
    with patch("bup.credential_check.DynamoDBAccess") as mock_dynamodb_access:
        mock_dynamodb_access.return_value.get_table_names.side_effect = NoCredentialsError()

        credential_check = check_dynamodb_credentials(_make_preferences())

    assert not credential_check.ok
    assert credential_check.message.startswith("could not list the DynamoDB tables : ")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_github_token_that_github_accepts_is_ok():
    with patch("bup.credential_check.github3.login") as mock_login:
        mock_login.return_value.me.return_value.login = "octocat"

        credential_check = check_github_credentials(_make_preferences())

    assert credential_check == CredentialCheck(True, "OK - logged in as octocat")
    mock_login.assert_called_once_with(token=github_token)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("token", [None, ""])
def test_github_check_without_a_token_is_not_ok_and_makes_no_request(token):
    with patch("bup.credential_check.github3.login") as mock_login:
        credential_check = check_github_credentials(_make_preferences(github_token=token))

    assert credential_check == CredentialCheck(False, "no github token is set")
    mock_login.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_github_token_that_github_does_not_accept_is_not_ok():
    with patch("bup.credential_check.github3.login") as mock_login:
        mock_login.return_value.me.side_effect = AuthenticationFailed(_make_github_response(401, "Bad credentials"))

        credential_check = check_github_credentials(_make_preferences())

    assert credential_check == CredentialCheck(False, "github did not accept the token")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize(
    "github_error,expected_start",
    [
        (GitHubConnectionError(OSError(f"could not connect with {github_token}")), "could not reach github : "),
        (ForbiddenError(_make_github_response(403, f"rate limit exceeded for {github_token}")), "github refused : "),
    ],
)
def test_github_check_that_fails_otherwise_says_why_without_the_token(github_error, expected_start):
    with patch("bup.credential_check.github3.login") as mock_login:
        mock_login.return_value.me.side_effect = github_error

        credential_check = check_github_credentials(_make_preferences())

    assert not credential_check.ok
    assert credential_check.message.startswith(expected_start)
    assert github_token not in credential_check.message
    assert "***" in credential_check.message


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_check_is_in_the_log_and_a_failed_one_is_not_an_error(caplog):
    with patch("bup.credential_check.S3Access") as mock_s3_access, caplog.at_level("INFO"):
        mock_s3_access.return_value.bucket_list.return_value = []
        check_s3_credentials(_make_preferences())
        mock_s3_access.return_value.bucket_list.side_effect = NoCredentialsError()
        check_s3_credentials(_make_preferences())

    records = [(record.levelname, record.getMessage()) for record in caplog.records if "credentials check" in record.getMessage()]
    assert [levelname for levelname, _unused_message in records] == ["INFO", "WARNING"]
    assert records[0][1] == "S3 credentials check : OK - 0 buckets"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def gui_preferences(monkeypatch):
    """
    Stand-in for the GUI's preferences, so no test reads or writes the real ones.
    """
    preferences = _make_preferences()
    monkeypatch.setattr(preferences_widget, "get_gui_preferences", lambda: preferences)
    return preferences


def _wait_for_result(qapp, button: CredentialCheckButton, timeout: float = 10.0):
    """
    Let the GUI run until the check of a button is back (the button is enabled again).
    """
    end_time = time.time() + timeout
    while not button.isEnabled() and time.time() < end_time:
        qapp.processEvents()
        time.sleep(0.01)
    assert button.isEnabled(), "the check did not come back"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def status_messages():
    """
    :return: the messages that are sent to the status line of the main window during the test, in order
    """
    messages = []
    status_emitter.status_signal.connect(messages.append)
    yield messages
    status_emitter.status_signal.disconnect(messages.append)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_button_runs_its_check_off_the_gui_thread_and_says_how_it_went(qapp, gui_preferences, status_messages):
    release = threading.Event()
    seen = {}

    def check(preferences) -> CredentialCheck:
        seen["preferences"] = preferences
        seen["thread"] = threading.current_thread()
        release.wait(10.0)
        return CredentialCheck(True, "OK - 3 buckets")

    button = CredentialCheckButton("S3", check)
    assert button.text() == "Test S3"
    assert button.result is None

    button.click()

    # while the check is running the button can not be clicked again
    assert not button.isEnabled()
    assert status_messages == ["Testing the S3 credentials ..."]
    release.set()
    _wait_for_result(qapp, button)
    assert status_messages == ["Testing the S3 credentials ...", "S3 credentials: OK - 3 buckets"]
    assert button.result == CredentialCheck(True, "OK - 3 buckets")
    assert button.toolTip() == "OK - 3 buckets"
    assert seen["preferences"] is gui_preferences
    assert seen["thread"] is not threading.main_thread()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_button_says_that_a_check_failed_and_can_check_again(qapp, gui_preferences, status_messages):
    results = [CredentialCheck(False, "github did not accept the token"), CredentialCheck(True, "OK - logged in as octocat")]
    button = CredentialCheckButton("GitHub", lambda preferences: results.pop(0))

    button.click()
    _wait_for_result(qapp, button)

    assert status_messages[-1] == "GitHub credentials: github did not accept the token"
    assert button.result == CredentialCheck(False, "github did not accept the token")

    button.click()
    assert button.result is None  # the check before is not the result of this one
    assert button.toolTip() == ""
    _wait_for_result(qapp, button)

    assert status_messages[-1] == "GitHub credentials: OK - logged in as octocat"
    assert button.toolTip() == "OK - logged in as octocat"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")  # the failure is let on its way, out of the thread of the check
def test_button_says_a_failure_that_the_check_does_not_report_itself(qapp, gui_preferences, status_messages):
    def check(preferences) -> CredentialCheck:
        raise ZeroDivisionError("unexpected")

    button = CredentialCheckButton("S3", check)
    thread_exceptions = []

    with patch("threading.excepthook", lambda args: thread_exceptions.append(args.exc_type)):
        button.click()
        _wait_for_result(qapp, button)
        button.check_thread.join(10.0)

    assert status_messages[-1] == "S3 credentials: ZeroDivisionError : unexpected"
    assert button.result == CredentialCheck(False, "ZeroDivisionError : unexpected")
    assert thread_exceptions == [ZeroDivisionError]  # it was not swallowed


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_preferences_tab_has_a_test_button_for_each_backup_type(qapp, gui_preferences, status_messages):
    for not_set in ("backup_directory", "detailed_log_directory", "detailed_log_file_size_limit_mb", "backup_period"):
        setattr(gui_preferences, not_set, None)
    checks = {
        "s3": MagicMock(return_value=CredentialCheck(True, "s3 ok")),
        "dynamodb": MagicMock(return_value=CredentialCheck(True, "dynamodb ok")),
        "github": MagicMock(return_value=CredentialCheck(False, "github not ok")),
    }

    with (
        patch("bup.gui.preferences_widget.check_s3_credentials", checks["s3"]),
        patch("bup.gui.preferences_widget.check_dynamodb_credentials", checks["dynamodb"]),
        patch("bup.gui.preferences_widget.check_github_credentials", checks["github"]),
    ):
        widget = PreferencesWidget()
    buttons = {"s3": widget.test_s3_button, "dynamodb": widget.test_dynamodb_button, "github": widget.test_github_button}
    assert [button.text() for button in buttons.values()] == ["Test S3", "Test DynamoDB", "Test GitHub"]
    # the AWS tests are with the AWS preferences and the GitHub test is with the token
    assert widget.test_s3_button.parentWidget() is widget.aws_region_widget
    assert widget.test_dynamodb_button.parentWidget() is widget.aws_region_widget
    assert widget.test_github_button.parentWidget() is widget.github_widget

    # making the tab checks nothing
    assert all(check.call_count == 0 for check in checks.values())
    assert status_messages == []
    for button in buttons.values():
        button.click()
        _wait_for_result(qapp, button)

    assert {name: button.result.message for name, button in buttons.items()} == {"s3": "s3 ok", "dynamodb": "dynamodb ok", "github": "github not ok"}
    assert status_messages[-1] == "GitHub credentials: github not ok"
    for check in checks.values():
        check.assert_called_once_with(gui_preferences)
