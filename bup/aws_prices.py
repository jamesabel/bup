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
from typing import Dict, List, Optional, Tuple

import appdirs
from balsa import get_logger

from bup import __application_name__, __author__

log = get_logger(__application_name__)

# one file per AWS service and region, e.g. .../AWSDataTransfer/current/us-east-1/index.json
price_list_url = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service_code}/current/{region}/index.json"
data_transfer_service_code = "AWSDataTransfer"
dynamodb_service_code = "AmazonDynamoDB"
s3_service_code = "AmazonS3"

price_max_age_seconds = 7 * 24 * 60 * 60  # fetch the prices again once the cached ones are this old
fetch_retry_seconds = 60 * 60  # after a failed fetch, don't try that region again for this long (a backup may ask once per bucket)

read_units_per_million = 1000000
requests_per_thousand = 1000

# The "group" a price list file has the S3 request prices under. The requests of bup that are tier 1 (PUT, COPY, POST and LIST) are
# listings, which are not for an object of a storage class, so there is one tier 1 price. A tier 2 request (GET, HEAD and all other
# requests) is priced by the storage class of its object, which is the name S3 itself gives the storage class (e.g. of a HeadObject).
s3_standard_storage_class = "STANDARD"
s3_tier1_request_group = "S3-API-Tier1"
s3_tier2_request_groups = {
    s3_standard_storage_class: "S3-API-Tier2",
    "STANDARD_IA": "S3-API-SIA-Tier2",
    "ONEZONE_IA": "S3-API-ZIA-Tier2",
    "INTELLIGENT_TIERING": "S3-API-INT-Tier2",
    "GLACIER_IR": "S3-API-GIR-Tier2",
    "GLACIER": "S3-API-GLACIER-Tier2",
    "DEEP_ARCHIVE": "S3-API-GDA-Tier2",
}
# The "group" of the retrieval fee of each storage class that has one: a price per GB of the objects that are read, which is on top of
# the data transfer out. (An archived object, e.g. of GLACIER, has to be restored before it can be read, which bup does not do.)
s3_retrieval_groups = {
    "STANDARD_IA": "S3-API-SIA-Retrieval",
    "ONEZONE_IA": "S3-API-ZIA-Retrieval",
    "GLACIER_IR": "S3-API-GIR-Retrieval",
}


class AWSPriceError(Exception):
    """
    A price list file does not have the price being looked for.
    """


@dataclass(frozen=True)
class AWSPrices:
    """
    The prices of one AWS region that a backup's cost is estimated with.
    """

    region: str
    transfer_out_price_per_gb: float  # USD, data transfer out to the internet
    dynamodb_read_price_per_million_units: float  # USD, on-demand read request units
    fetched: float  # when the prices were fetched (epoch seconds)
    s3_tier1_request_price_per_thousand: float  # USD, S3 PUT, COPY, POST and LIST requests (of bup: the listings)
    # USD, S3 GET, HEAD and all other requests, by the storage class of the object. Always has STANDARD, which is also the price of a
    # storage class that is not here.
    s3_tier2_request_prices_per_thousand: Dict[str, float]
    s3_retrieval_prices_per_gb: Dict[str, float]  # USD, the retrieval fee of the S3 storage classes that have one, by storage class

    def get_s3_tier2_request_price_per_thousand(self, storage_class: str) -> float:
        """
        :param storage_class: the storage class of an S3 object, as S3 names it (e.g. "GLACIER_IR")
        :return: USD per 1000 GET, HEAD or other tier 2 requests for objects of the storage class
        """
        return self.s3_tier2_request_prices_per_thousand.get(storage_class, self.s3_tier2_request_prices_per_thousand[s3_standard_storage_class])

    def get_s3_retrieval_price_per_gb(self, storage_class: str) -> float:
        """
        :param storage_class: the storage class of an S3 object, as S3 names it (e.g. "GLACIER_IR")
        :return: USD per GB read of objects of the storage class, which is zero for a storage class without a retrieval fee (e.g. STANDARD)
        """
        return self.s3_retrieval_prices_per_gb.get(storage_class, 0.0)


def get_aws_price_cache_path() -> Path:
    """
    :return: the path of the SQLite database the fetched prices are cached in (in bup's user cache directory)
    """
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


def find_s3_price(offer: dict, group: str, usage_type_end: str) -> Optional[float]:
    """
    USD per unit of an S3 product, from a region's AmazonS3 price list file. A group can have more than one product (e.g. "S3-API-Tier2"
    also has the annotation requests), so the product is also known by what its usage type ends with. The usage types of a region
    other than us-east-1 start with the region's prefix, e.g. "EU-Requests-SIA-Tier2".

    :param group: the "group" attribute of the product, e.g. "S3-API-SIA-Tier2"
    :param usage_type_end: what the "usagetype" attribute of the product ends with, e.g. "Requests-SIA-Tier2"
    :return: the price, or None if the file does not have it (e.g. a storage class the region does not have)
    """
    for sku, product in offer["products"].items():
        attributes = product["attributes"]
        if attributes.get("group") == group and attributes.get("usagetype", "").endswith(usage_type_end):
            return get_first_tier_price(offer, sku)
    return None


def find_s3_request_price(offer: dict, group: str) -> Optional[float]:
    """
    USD per 1000 S3 requests of a group, from a region's AmazonS3 price list file.

    :param group: the "group" attribute of the product, e.g. "S3-API-SIA-Tier2" (whose usage type ends with "Requests-SIA-Tier2")
    :return: the price, or None if the file does not have it (e.g. a storage class the region does not have)
    """
    price_per_request = find_s3_price(offer, group, "Requests-" + group.removeprefix("S3-API-"))
    return None if price_per_request is None else price_per_request * requests_per_thousand


def parse_s3_retrieval_prices(offer: dict) -> Dict[str, float]:
    """
    The retrieval fees of a region's AmazonS3 price list file, in USD per GB read.

    :return: the retrieval fee of each storage class the file has one for (none is not an error: not every region has every storage class)
    """
    retrieval_prices = {}
    for storage_class, group in s3_retrieval_groups.items():
        # e.g. the usage type of "S3-API-SIA-Retrieval" ends with "Retrieval-SIA"
        if (retrieval_price := find_s3_price(offer, group, "Retrieval-" + group.removeprefix("S3-API-").removesuffix("-Retrieval"))) is not None:
            retrieval_prices[storage_class] = retrieval_price
    return retrieval_prices


def parse_s3_request_prices(offer: dict) -> Tuple[float, Dict[str, float]]:
    """
    The S3 request prices of a region's AmazonS3 price list file, in USD per 1000 requests.

    :return: (the tier 1 price, the tier 2 price of each storage class the file has one for, which STANDARD is always one of)
    """
    tier1_price = find_s3_request_price(offer, s3_tier1_request_group)
    if tier1_price is None:
        raise AWSPriceError("no S3 tier 1 (PUT, COPY, POST and LIST) request price")
    tier2_prices = {}
    for storage_class, group in s3_tier2_request_groups.items():
        if (tier2_price := find_s3_request_price(offer, group)) is not None:
            tier2_prices[storage_class] = tier2_price
    if s3_standard_storage_class not in tier2_prices:
        raise AWSPriceError("no S3 tier 2 (GET and all other) request price")
    return tier1_price, tier2_prices


def fetch_aws_prices(region: str) -> AWSPrices:
    """
    Get a region's current prices from AWS. Raises OSError, ValueError, KeyError or AWSPriceError if they can't be had.
    """
    transfer_out_price_per_gb = parse_transfer_out_price(fetch_offer(data_transfer_service_code, region), region)
    dynamodb_read_price_per_million_units = parse_dynamodb_read_price(fetch_offer(dynamodb_service_code, region))
    s3_offer = fetch_offer(s3_service_code, region)
    s3_tier1_request_price, s3_tier2_request_prices = parse_s3_request_prices(s3_offer)
    s3_retrieval_prices = parse_s3_retrieval_prices(s3_offer)
    return AWSPrices(region, transfer_out_price_per_gb, dynamodb_read_price_per_million_units, time.time(), s3_tier1_request_price, s3_tier2_request_prices, s3_retrieval_prices)


# The columns of the price cache table, which are the fields of AWSPrices in order. The prices by storage class (the last two) are
# each a JSON object.
price_cache_column_names = [
    "region",
    "transfer_out_price_per_gb",
    "dynamodb_read_price_per_million_units",
    "fetched",
    "s3_tier1_request_price_per_thousand",
    "s3_tier2_request_prices_per_thousand",
    "s3_retrieval_prices_per_gb",
]
price_cache_columns = ", ".join(price_cache_column_names)


def make_aws_prices(row: tuple) -> AWSPrices:
    """
    :param row: a row of the price cache table (its price_cache_columns)
    :return: the prices of the row
    """
    *values, s3_tier2_request_prices_json, s3_retrieval_prices_json = row
    return AWSPrices(*values, json.loads(s3_tier2_request_prices_json), json.loads(s3_retrieval_prices_json))


class AWSPriceCache:
    """
    The fetched prices of each region, in a SQLite database. Each call opens its own connection, so this can be used from any thread.
    """

    def __init__(self, path: Path):
        """
        :param path: the path of the database (made, with its directory, if it does not exist)
        """
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            # A table without all the prices is of an earlier bup (0.18.0 and before had no S3 request prices, and 0.19.0 no S3
            # retrieval fees). This is a cache, so it is made again and its prices are fetched again.
            existing_column_names = [column[1] for column in connection.execute("PRAGMA table_info(aws_prices)")]
            if existing_column_names and existing_column_names != price_cache_column_names:
                connection.execute("DROP TABLE aws_prices")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS aws_prices "
                "(region TEXT PRIMARY KEY, transfer_out_price_per_gb REAL NOT NULL, dynamodb_read_price_per_million_units REAL NOT NULL, fetched REAL NOT NULL, "
                "s3_tier1_request_price_per_thousand REAL NOT NULL, s3_tier2_request_prices_per_thousand TEXT NOT NULL, s3_retrieval_prices_per_gb TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get(self, region: str) -> Optional[AWSPrices]:
        """
        :return: the cached prices of a region, or None if there are none
        """
        with closing(self._connect()) as connection:
            row = connection.execute(f"SELECT {price_cache_columns} FROM aws_prices WHERE region = ?", (region,)).fetchone()
        return None if row is None else make_aws_prices(row)

    def get_all(self) -> List[AWSPrices]:
        """
        :return: the cached prices of every region, in order of region name
        """
        with closing(self._connect()) as connection:
            rows = connection.execute(f"SELECT {price_cache_columns} FROM aws_prices ORDER BY region").fetchall()
        return [make_aws_prices(row) for row in rows]

    def put(self, aws_prices: AWSPrices):
        """
        Cache the prices of a region, in place of the ones cached for it before.
        """
        with closing(self._connect()) as connection, connection:
            connection.execute(
                f"INSERT OR REPLACE INTO aws_prices ({price_cache_columns}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    aws_prices.region,
                    aws_prices.transfer_out_price_per_gb,
                    aws_prices.dynamodb_read_price_per_million_units,
                    aws_prices.fetched,
                    aws_prices.s3_tier1_request_price_per_thousand,
                    json.dumps(aws_prices.s3_tier2_request_prices_per_thousand),
                    json.dumps(aws_prices.s3_retrieval_prices_per_gb),
                ),
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
