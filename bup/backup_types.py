from enum import Enum


class BackupTypes(Enum):
    S3 = 0
    DynamoDB = 1
    github = 2
