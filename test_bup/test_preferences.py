from bup.gui import PreferencesStore, ListOfStringsStore

from bup import BackupTypes


def test_preferences():
    preferences = PreferencesStore()
    test_aws_profile = "test_aws_profile"
    preferences.aws_profile = test_aws_profile

    preferences = PreferencesStore()
    assert preferences.aws_profile == test_aws_profile

    exclusions = ListOfStringsStore(BackupTypes.S3)
    test_list = ["hi", "hello", "goodbye"]
    exclusions.set_list(test_list)
    assert exclusions.get_list() == test_list
