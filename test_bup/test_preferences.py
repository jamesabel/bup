from copy import deepcopy

from bup import BupPreferences, ExclusionPreferences, BackupTypes

from bup import BackupTypes, __author__
from test_bup import __application_name__


def test_preferences():
    preferences = BupPreferences(__application_name__, __author__)
    test_aws_profile = "test_aws_profile"
    preferences.aws_profile = test_aws_profile

    preferences = BupPreferences(__application_name__, __author__)
    assert preferences.aws_profile == test_aws_profile

    exclusions = ExclusionPreferences(BackupTypes.S3.name)
    saved_exclusions = exclusions.get()
    test_list = ["a", "b", "a", "", "qwertyuiop", "c", 1]  # two "a"s, and an int 1
    expected_results = deepcopy(test_list)
    expected_results.pop(0)  # remove 1st "a"
    expected_results[-1] = str(expected_results[-1])  # the input value can be non-string, but it'll be returned as a string
    exclusions.set(test_list)
    assert exclusions.get() == expected_results
    exclusions.set(saved_exclusions)
