"""
AWS prices for estimating what a backup costs, per AWS region.

The prices come from the public AWS Price List (bulk) files, which need no AWS credentials or IAM permissions. They are cached in a
local SQLite database and fetched again once they are older than price_max_age_seconds, so bup keeps up with price changes without
anyone having to enter a price.
"""

import json
import sqlite3
import threading
import time
import urllib.request
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import appdirs
from balsa import get_logger

from bup import __application_name__, __author__

log = get_logger(__application_name__)

# one file per AWS service and region, e.g. .../AWSDataTransfer/current/us-east-1/index.json
price_list_url = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service_code}/current/{region}/index.json"
data_transfer_service_code = "AWSDataTransfer"
dynamodb_service_code = "AmazonDynamoDB"

price_max_age_seconds = 7 * 24 * 60 * 60  # fetch the prices again once the cached ones are this old
fetch_retry_seconds = 60 * 60  # after a failed fetch, don't try that region again for this long (a backup may ask once per bucket)

read_units_per_million = 1000000


class AWSPriceError(Exception):
    """
    A price list file does not have the price being looked for.
    """


@dataclass(frozen=True)
class AWSPrices:
    region: str
    transfer_out_price_per_gb: float  # USD, data transfer out to the internet
    dynamodb_read_price_per_million_units: float  # USD, on-demand read request units
    fetched: float  # when the prices were fetched (epoch seconds)


def get_aws_price_cache_path() -> Path:
    return Path(appdirs.user_cache_dir(__application_name__, __author__), "aws_prices.db")


def fetch_offer(service_code: str, region: str, timeout: float = 60.0) -> dict:
    """
    Download one AWS Price List file. Raises OSError (covers URLError, HTTPError and timeouts) or ValueError (not JSON).
    """
    url = price_list_url.format(service_code=service_code, region=region)
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def get_first_tier_price(offer: dict, sku: str) -> float:
    """
    USD price per unit of a product, for the pricing tier that starts at zero usage (volume discount tiers are ignored).
    """
    for term in offer["terms"]["OnDemand"][sku].values():
        for price_dimension in term["priceDimensions"].values():
            if float(price_dimension["beginRange"]) == 0.0:
                return float(price_dimension["pricePerUnit"]["USD"])
    raise AWSPriceError(f"no price from zero usage for product {sku}")


def parse_transfer_out_price(offer: dict, region: str) -> float:
    """
    USD per GB of data transfer out to the internet from a region, from an AWSDataTransfer price list file.
    """
    for sku, product in offer["products"].items():
        attributes = product["attributes"]
        if attributes.get("transferType") == "AWS Outbound" and attributes.get("fromRegionCode") == region and attributes.get("toLocation") == "External":
            return get_first_tier_price(offer, sku)
    raise AWSPriceError(f"no data transfer out to the internet price for {region}")


def parse_dynamodb_read_price(offer: dict) -> float:
    """
    USD per million on-demand read request units, from a region's AmazonDynamoDB price list file.
    """
    for sku, product in offer["products"].items():
        if product.get("productFamily") == "Amazon DynamoDB PayPerRequest Throughput" and product["attributes"].get("group") == "DDB-ReadUnits":
            return get_first_tier_price(offer, sku) * read_units_per_million
    raise AWSPriceError("no DynamoDB on-demand read request unit price")


def fetch_aws_prices(region: str) -> AWSPrices:
    """
    Get a region's current prices from AWS. Raises OSError, ValueError, KeyError or AWSPriceError if they can't be had.
    """
    transfer_out_price_per_gb = parse_transfer_out_price(fetch_offer(data_transfer_service_code, region), region)
    dynamodb_read_price_per_million_units = parse_dynamodb_read_price(fetch_offer(dynamodb_service_code, region))
    return AWSPrices(region, transfer_out_price_per_gb, dynamodb_read_price_per_million_units, time.time())


class AWSPriceCache:
    """
    The fetched prices of each region, in a SQLite database. Each call opens its own connection, so this can be used from any thread.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS aws_prices "
                "(region TEXT PRIMARY KEY, transfer_out_price_per_gb REAL NOT NULL, dynamodb_read_price_per_million_units REAL NOT NULL, fetched REAL NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get(self, region: str) -> Optional[AWSPrices]:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT region, transfer_out_price_per_gb, dynamodb_read_price_per_million_units, fetched FROM aws_prices WHERE region = ?", (region,)).fetchone()
        return None if row is None else AWSPrices(*row)

    def get_all(self) -> List[AWSPrices]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT region, transfer_out_price_per_gb, dynamodb_read_price_per_million_units, fetched FROM aws_prices ORDER BY region").fetchall()
        return [AWSPrices(*row) for row in rows]

    def put(self, aws_prices: AWSPrices):
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT OR REPLACE INTO aws_prices (region, transfer_out_price_per_gb, dynamodb_read_price_per_million_units, fetched) VALUES (?, ?, ?, ?)",
                (aws_prices.region, aws_prices.transfer_out_price_per_gb, aws_prices.dynamodb_read_price_per_million_units, aws_prices.fetched),
            )


def get_cached_aws_prices() -> List[AWSPrices]:
    """
    The prices of every region fetched so far, without fetching anything. Raises sqlite3.Error or OSError if the cache can't be read.
    """
    return AWSPriceCache(get_aws_price_cache_path()).get_all()


# the S3 and DynamoDB backups run at the same time in their own threads - one of them at a time looks up (and possibly fetches) prices
_get_aws_prices_lock = threading.Lock()
_failed_fetch_times: Dict[str, float] = {}  # region -> when a fetch last failed (epoch seconds)


def get_aws_prices(region) -> Optional[AWSPrices]:
    """
    A region's prices: the cached ones, fetched (again) from AWS first if there are none or they are older than price_max_age_seconds.
    If the fetch fails the cached prices are still used, however old.
    :param region: AWS region name, e.g. "us-east-1" (anything else, e.g. None for an undetermined region, has no prices)
    :return: the prices, or None if there are none (never fetched and can't be fetched now) - the cost is then not estimated
    """
    if not isinstance(region, str) or len(region) == 0:
        return None
    with _get_aws_prices_lock:
        try:
            aws_price_cache = AWSPriceCache(get_aws_price_cache_path())
            aws_prices = aws_price_cache.get(region)
        except (sqlite3.Error, OSError) as e:
            log.warning(f"could not read the AWS price cache - costs are not estimated : {e}")
            return None
        now = time.time()
        is_stale = aws_prices is None or now - aws_prices.fetched > price_max_age_seconds
        if is_stale and now - _failed_fetch_times.get(region, 0.0) > fetch_retry_seconds:
            try:
                aws_prices = fetch_aws_prices(region)
                aws_price_cache.put(aws_prices)
                log.info(f"fetched AWS prices for {region} : {aws_prices}")
            except (OSError, ValueError, KeyError, AWSPriceError, sqlite3.Error) as e:
                # e.g. offline, or a region whose price list has no USD prices
                _failed_fetch_times[region] = now
                consequence = "costs for this region are not estimated" if aws_prices is None else "using the previously fetched prices"
                log.warning(f"could not get AWS prices for {region} - {consequence} : {e}")
        return aws_prices
