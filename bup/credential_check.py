"""
Checks of the credentials in the preferences, without running a backup: each one makes the first request that the backup of its type
makes (list the S3 buckets, list the DynamoDB tables, log in to GitHub) and says how that went. Nothing is backed up or written.

A check that fails is an outcome, not an error of bup: it is what the user asked to find out.
"""

from dataclasses import dataclass

import github3
from awsimple import DynamoDBAccess, S3Access
from balsa import get_logger
from botocore.exceptions import BotoCoreError, ClientError
from github3.exceptions import AuthenticationFailed, GitHubError, TransportError

from bup import __application_name__
from bup.aws_access import get_aws_access_kwargs

log = get_logger(__application_name__)


@dataclass(frozen=True)
class CredentialCheck:
    """
    How a check of credentials went.
    """

    ok: bool  # True if the credentials were accepted
    message: str  # what to tell the user, e.g. "OK - 12 buckets" or why they were not accepted


def _get_check(name: str, ok: bool, message: str) -> CredentialCheck:
    """
    Make the outcome of a check, and put it in the log.

    :param name: what was checked, e.g. "S3"
    :param ok: True if the credentials were accepted
    :param message: what to tell the user
    :return: the outcome
    """
    log_out = log.info if ok else log.warning
    log_out(f"{name} credentials check : {message}")
    return CredentialCheck(ok, message)


def check_s3_credentials(preferences) -> CredentialCheck:
    """
    Check the AWS credentials of the preferences with what the S3 backup starts with: a listing of the buckets.

    :param preferences: the preferences (see BupPreferences)
    :return: how it went
    """
    try:
        bucket_names = S3Access(**get_aws_access_kwargs(preferences)).bucket_list()  # making the access raises if the AWS profile does not exist
    except (ClientError, BotoCoreError) as e:
        # BotoCoreError covers e.g. ProfileNotFound, NoCredentialsError and EndpointConnectionError
        return _get_check("S3", False, f"could not list the S3 buckets : {e}")
    return _get_check("S3", True, f"OK - {len(bucket_names)} buckets")


def check_dynamodb_credentials(preferences) -> CredentialCheck:
    """
    Check the AWS credentials and region of the preferences with what the DynamoDB backup starts with: a listing of the tables.

    :param preferences: the preferences (see BupPreferences)
    :return: how it went
    """
    try:
        table_names = DynamoDBAccess(**get_aws_access_kwargs(preferences)).get_table_names()  # making the access raises if the AWS profile does not exist
    except (ClientError, BotoCoreError) as e:
        return _get_check("DynamoDB", False, f"could not list the DynamoDB tables : {e}")
    region = f" in {preferences.aws_region}" if preferences.aws_region else ""
    return _get_check("DynamoDB", True, f"OK - {len(table_names)} tables{region}")


def check_github_credentials(preferences) -> CredentialCheck:
    """
    Check the GitHub token of the preferences by asking GitHub whose it is. The token is not in what this returns or logs.

    :param preferences: the preferences (see BupPreferences)
    :return: how it went
    """
    name = "GitHub"
    token = preferences.github_token
    if not token:
        return _get_check(name, False, "no github token is set")
    try:
        user_login = github3.login(token=token).me().login  # a request to GitHub
    except AuthenticationFailed:
        return _get_check(name, False, "github did not accept the token")
    except TransportError as e:
        # no response from GitHub at all, e.g. no internet connectivity
        return _get_check(name, False, f"could not reach github : {e}".replace(token, "***"))
    except GitHubError as e:
        # a response that is not the user, e.g. the rate limit is exceeded or GitHub has a server error
        return _get_check(name, False, f"github refused : {e}".replace(token, "***"))
    return _get_check(name, True, f"OK - logged in as {user_login}")
