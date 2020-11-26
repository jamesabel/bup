from enum import Enum

from bup import S3Backup, DynamoDBBackup, GithubBackup


class BackupTypes(Enum):
    S3 = 0
    DynamoDB = 1
    github = 2


backup_classes = {BackupTypes.S3: S3Backup, BackupTypes.DynamoDB: DynamoDBBackup, BackupTypes.github: GithubBackup}
