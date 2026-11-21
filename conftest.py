"""
Test configuration for the whole repository. All fixtures in this file are AI-authored (Claude Code).
"""

import pytest


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture(autouse=True)
def isolated_aws_prices(monkeypatch, tmp_path):
    """
    Keep every test away from the real AWS price list and the user's real price cache: bup fetches AWS prices over the network and
    caches them in the user's cache directory whenever a backup receives data, which tests of the backups would otherwise trigger.
    Each test gets an empty price cache of its own, and fetching fails as if offline (so costs are not estimated) unless the test
    replaces bup.aws_prices.fetch_offer itself.
    """

    def fetch_offer_offline(service_code: str, region: str, timeout: float = 60.0) -> dict:
        raise OSError("no network access in tests")

    monkeypatch.setattr("bup.aws_prices.fetch_offer", fetch_offer_offline)
    monkeypatch.setattr("bup.aws_prices.get_aws_price_cache_path", lambda: tmp_path / "aws_price_cache" / "aws_prices.db")
    monkeypatch.setattr("bup.aws_prices._failed_fetch_times", {})
