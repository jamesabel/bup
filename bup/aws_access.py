"""
What the AWS backups (S3 and DynamoDB) have in common in how they access AWS: the credentials and region from the preferences, and
quiet boto logging.
"""

import logging
from typing import Optional


def quiet_boto_logging():
    """
    Keep boto3 and botocore from logging below WARNING. They log every response at DEBUG level, and the repr() of a large response
    can contain characters that cp1252 (the default of a Windows console) can not encode, which causes noisy logging errors.
    """
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)


quiet_boto_logging()


def get_aws_access_kwargs(preferences, region_name: Optional[str] = None) -> dict:
    """
    The keyword arguments that give an awsimple access (S3Access, DynamoDBAccess) the AWS credentials and region of the preferences.
    A preference that is not set (None or blank) is None, which leaves it to the AWS defaults (e.g. the default profile).

    :param preferences: the preferences (see BupPreferences)
    :param region_name: the AWS region to access, if it is not the region of the preferences (e.g. the region an S3 bucket is in)
    :return: keyword arguments for an awsimple access
    """
    return {
        "profile_name": preferences.aws_profile or None,
        "aws_access_key_id": preferences.aws_access_key_id or None,
        "aws_secret_access_key": preferences.aws_secret_access_key or None,
        "region_name": region_name or preferences.aws_region or None,
    }
