from copy import deepcopy

from bup.gui import PreferencesStore, OrderedSetOfStringsStore

from bup import BackupTypes


def test_preferences():
    preferences = PreferencesStore()
    test_aws_profile = "test_aws_profile"
    preferences.aws_profile = test_aws_profile

    preferences = PreferencesStore()
    assert preferences.aws_profile == test_aws_profile

    exclusions = OrderedSetOfStringsStore(BackupTypes.S3)
    test_list = ["a", "b", "a", "", "qwertyuiop", "c", 1]  # two "a"s, and an int 1
    expected_results = deepcopy(test_list)
    expected_results.pop(0)  # remove 1st "a"
    expected_results[-1] = str(expected_results[-1])  # the input value can be non-string, but it'll be returned as a string
    exclusions.set_set(test_list)
    assert exclusions.get_set() == expected_results
