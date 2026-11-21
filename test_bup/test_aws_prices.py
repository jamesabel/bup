"""
Tests for getting and caching AWS prices (bup/aws_prices.py).
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty price cache of its own and makes fetching fail as if offline.
"""

import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import appdirs
import pytest

from bup import aws_prices, __application_name__, __author__
from bup.aws_prices import (
    AWSPrices,
    AWSPriceCache,
    AWSPriceError,
    fetch_offer,  # imported before conftest.py replaces it for each test, so this is the real one
    fetch_aws_prices,
    get_aws_prices,
    get_aws_price_cache_path as real_get_aws_price_cache_path,  # likewise the real one - only ever used to work out the path
    get_cached_aws_prices,
    get_first_tier_price,
    parse_transfer_out_price,
    parse_dynamodb_read_price,
    price_max_age_seconds,
    fetch_retry_seconds,
)

from .aws_price_offers import make_transfer_offer, make_dynamodb_offer, make_fetch_offer


def _fetch_offer_offline(service_code: str, region: str, timeout: float = 60.0) -> dict:
    raise OSError("offline")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def online(monkeypatch):
    # the price list is reachable - the returned stand-in for fetch_offer records what was fetched
    fake_fetch_offer = make_fetch_offer()
    monkeypatch.setattr("bup.aws_prices.fetch_offer", fake_fetch_offer)
    return fake_fetch_offer


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def clock(monkeypatch):
    # a clock the test can move forward
    class Clock:
        now = 1000000.0

    monkeypatch.setattr("bup.aws_prices.time.time", lambda: Clock.now)
    return Clock


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_parse_transfer_out_price_is_the_first_tier_of_internet_transfer_from_the_region():
    assert parse_transfer_out_price(make_transfer_offer("us-east-1"), "us-east-1") == 0.09
    assert parse_transfer_out_price(make_transfer_offer("ap-southeast-2", "0.1140000000"), "ap-southeast-2") == 0.114


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_parse_transfer_out_price_for_a_region_not_in_the_file():
    with pytest.raises(AWSPriceError, match="eu-west-1"):
        parse_transfer_out_price(make_transfer_offer("us-east-1"), "eu-west-1")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_parse_dynamodb_read_price_is_on_demand_reads_per_million():
    assert parse_dynamodb_read_price(make_dynamodb_offer()) == pytest.approx(0.125)
    assert parse_dynamodb_read_price(make_dynamodb_offer("0.0000001423")) == pytest.approx(0.1423)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_parse_dynamodb_read_price_not_in_the_file():
    with pytest.raises(AWSPriceError):
        parse_dynamodb_read_price({"products": {}, "terms": {"OnDemand": {}}})


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_first_tier_price_without_a_tier_from_zero():
    offer = {"terms": {"OnDemand": {"SKU": {"SKU.T": {"priceDimensions": {"SKU.T.1": {"beginRange": "100", "endRange": "Inf", "pricePerUnit": {"USD": "0.05"}}}}}}}}
    with pytest.raises(AWSPriceError):
        get_first_tier_price(offer, "SKU")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fetch_offer_downloads_the_file_of_the_service_and_region():
    with patch("bup.aws_prices.urllib.request.urlopen", return_value=io.BytesIO(json.dumps({"products": {}}).encode())) as mock_urlopen:
        offer = fetch_offer("AmazonDynamoDB", "eu-west-1")

    assert offer == {"products": {}}
    assert mock_urlopen.call_args.args[0] == "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonDynamoDB/current/eu-west-1/index.json"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fetch_aws_prices(online, clock):
    assert fetch_aws_prices("eu-west-1") == AWSPrices("eu-west-1", 0.09, pytest.approx(0.125), clock.now)
    assert online.fetched == [("AWSDataTransfer", "eu-west-1"), ("AmazonDynamoDB", "eu-west-1")]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_price_cache_is_a_sqlite_database_that_persists(tmp_path):
    cache_path = tmp_path / "new_directory" / "aws_prices.db"
    AWSPriceCache(cache_path).put(AWSPrices("us-east-1", 0.09, 0.125, 1000.0))
    AWSPriceCache(cache_path).put(AWSPrices("eu-west-1", 0.09, 0.1423, 2000.0))
    AWSPriceCache(cache_path).put(AWSPrices("us-east-1", 0.08, 0.125, 3000.0))  # newer prices replace the region's old ones

    aws_price_cache = AWSPriceCache(cache_path)  # a new object, as after a restart
    assert aws_price_cache.get("us-east-1") == AWSPrices("us-east-1", 0.08, 0.125, 3000.0)
    assert aws_price_cache.get("ap-southeast-2") is None
    assert aws_price_cache.get_all() == [AWSPrices("eu-west-1", 0.09, 0.1423, 2000.0), AWSPrices("us-east-1", 0.08, 0.125, 3000.0)]
    with closing(sqlite3.connect(cache_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM aws_prices").fetchone() == (2,)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_fetches_once_then_uses_the_cache(online, clock):
    first = get_aws_prices("us-east-1")
    clock.now += price_max_age_seconds - 1.0
    second = get_aws_prices("us-east-1")

    assert first == second == AWSPrices("us-east-1", 0.09, pytest.approx(0.125), 1000000.0)
    assert len(online.fetched) == 2  # the two files of the region, fetched once
    assert get_cached_aws_prices() == [first]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_fetches_again_when_the_cached_prices_are_old(monkeypatch, online, clock):
    get_aws_prices("us-east-1")
    clock.now += price_max_age_seconds + 1.0
    monkeypatch.setattr("bup.aws_prices.fetch_offer", make_fetch_offer(transfer_price_per_gb="0.0800000000"))  # AWS changed a price

    refreshed = get_aws_prices("us-east-1")

    assert refreshed == AWSPrices("us-east-1", 0.08, pytest.approx(0.125), clock.now)
    assert get_cached_aws_prices() == [refreshed]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_each_region_has_its_own_prices(online):
    get_aws_prices("us-east-1")
    get_aws_prices("eu-west-1")

    assert [cached.region for cached in get_cached_aws_prices()] == ["eu-west-1", "us-east-1"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_offline_with_nothing_cached_has_no_prices(caplog):
    assert get_aws_prices("us-east-1") is None
    assert any("could not get AWS prices for us-east-1 - costs for this region are not estimated" in record.getMessage() for record in caplog.records)
    assert all(record.levelname == "WARNING" for record in caplog.records)  # being offline is not an error


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_offline_uses_old_cached_prices(monkeypatch, online, clock, caplog):
    fetched = get_aws_prices("us-east-1")
    clock.now += price_max_age_seconds + 1.0
    monkeypatch.setattr("bup.aws_prices.fetch_offer", _fetch_offer_offline)

    assert get_aws_prices("us-east-1") == fetched
    assert any("using the previously fetched prices" in record.getMessage() for record in caplog.records)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_does_not_retry_a_failed_fetch_right_away(monkeypatch, clock):
    assert get_aws_prices("us-east-1") is None  # offline
    online = make_fetch_offer()
    monkeypatch.setattr("bup.aws_prices.fetch_offer", online)

    clock.now += fetch_retry_seconds - 1.0
    assert get_aws_prices("us-east-1") is None  # too soon to try again (a backup asks once per bucket)
    assert online.fetched == []
    assert get_aws_prices("eu-west-1") is not None  # another region is not held back

    clock.now += 2.0
    assert get_aws_prices("us-east-1") is not None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_price_list_without_the_price_has_no_prices(monkeypatch, caplog):
    monkeypatch.setattr("bup.aws_prices.fetch_offer", lambda service_code, region, timeout=60.0: {"products": {}, "terms": {"OnDemand": {}}})

    assert get_aws_prices("us-east-1") is None
    assert any("could not get AWS prices" in record.getMessage() for record in caplog.records)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_undetermined_region_has_no_prices(online):
    assert get_aws_prices(None) is None
    assert get_aws_prices("") is None
    assert online.fetched == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_aws_prices_unreadable_cache_has_no_prices(online, caplog):
    cache_path = aws_prices.get_aws_price_cache_path()  # this test's own cache (see conftest.py)
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"this is not a SQLite database, and is long enough to not look like an empty one" * 10)

    assert get_aws_prices("us-east-1") is None
    assert any("could not read the AWS price cache" in record.getMessage() for record in caplog.records)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_price_cache_is_in_the_user_cache_directory():
    # only works out the path - nothing is read from or written to the real cache
    assert real_get_aws_price_cache_path() == Path(appdirs.user_cache_dir(__application_name__, __author__), "aws_prices.db")
