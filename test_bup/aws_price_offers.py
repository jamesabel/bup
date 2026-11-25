"""
AWS Price List files for tests, cut down from the real ones (same structure, a few of the products).
Everything in this file is AI-authored (Claude Code).
"""

from typing import Optional

import pytest

from bup.aws_prices import AWSPrices


def make_transfer_offer(region: str = "us-east-1", price_per_gb: str = "0.0900000000") -> dict:
    """
    An AWSDataTransfer price list file: the region's data transfer out to the internet (tiered by volume), plus products that must
    not be mistaken for it - the global free tier, accelerated transfer out, and transfer out to another region.
    """
    return {
        "products": {
            "FREETIER": {"productFamily": "Data Transfer", "attributes": {"transferType": "AWS Outbound", "fromLocation": "Global", "fromRegionCode": "", "toLocation": "External"}},
            "ACCELERATED": {
                "productFamily": "Data Transfer",
                "attributes": {"transferType": "Accelerated AWS Outbound from close by location", "fromRegionCode": region, "toLocation": "External"},
            },
            "INTERREGION": {"productFamily": "Data Transfer", "attributes": {"transferType": "InterRegion Outbound", "fromRegionCode": region, "toLocation": "US West (Oregon)"}},
            "INTERNETOUT": {"productFamily": "Data Transfer", "attributes": {"transferType": "AWS Outbound", "fromRegionCode": region, "toLocation": "External"}},
        },
        "terms": {
            "OnDemand": {
                "FREETIER": {"FREETIER.T": {"priceDimensions": {"FREETIER.T.1": {"beginRange": "0", "endRange": "100", "unit": "GB", "pricePerUnit": {"USD": "0.0000000000"}}}}},
                "ACCELERATED": {"ACCELERATED.T": {"priceDimensions": {"ACCELERATED.T.1": {"beginRange": "0", "endRange": "Inf", "unit": "GB", "pricePerUnit": {"USD": "0.0400000000"}}}}},
                "INTERREGION": {"INTERREGION.T": {"priceDimensions": {"INTERREGION.T.1": {"beginRange": "0", "endRange": "Inf", "unit": "GB", "pricePerUnit": {"USD": "0.0200000000"}}}}},
                "INTERNETOUT": {
                    "INTERNETOUT.T": {
                        "priceDimensions": {
                            # deliberately not in tier order
                            "INTERNETOUT.T.2": {"beginRange": "10240", "endRange": "51200", "unit": "GB", "pricePerUnit": {"USD": "0.0850000000"}},
                            "INTERNETOUT.T.1": {"beginRange": "0", "endRange": "10240", "unit": "GB", "pricePerUnit": {"USD": price_per_gb}},
                        }
                    }
                },
            }
        },
    }


def make_dynamodb_offer(price_per_unit: str = "0.0000001250") -> dict:
    """
    An AmazonDynamoDB price list file: on-demand read request units, plus read products that must not be mistaken for them -
    infrequent access reads and provisioned read capacity.
    """
    return {
        "products": {
            "IAREADS": {"productFamily": "Amazon DynamoDB PayPerRequest Throughput", "attributes": {"group": "DDB-ReadUnitsIA"}},
            "PROVISIONED": {"productFamily": "Provisioned IOPS", "attributes": {"group": "DDB-ReadUnits"}},
            "READS": {"productFamily": "Amazon DynamoDB PayPerRequest Throughput", "attributes": {"group": "DDB-ReadUnits"}},
        },
        "terms": {
            "OnDemand": {
                "IAREADS": {"IAREADS.T": {"priceDimensions": {"IAREADS.T.1": {"beginRange": "0", "endRange": "Inf", "unit": "ReadRequestUnits", "pricePerUnit": {"USD": "0.0000001550"}}}}},
                "PROVISIONED": {
                    "PROVISIONED.T": {"priceDimensions": {"PROVISIONED.T.1": {"beginRange": "0", "endRange": "18600", "unit": "ReadCapacityUnit-Hrs", "pricePerUnit": {"USD": "0.0000000000"}}}}
                },
                "READS": {"READS.T": {"priceDimensions": {"READS.T.1": {"beginRange": "0", "endRange": "Inf", "unit": "ReadRequestUnits", "pricePerUnit": {"USD": price_per_unit}}}}},
            }
        },
    }


def _request_product(group: str, usage_type: str, product_family: Optional[str] = "API Request") -> dict:
    return {"productFamily": product_family, "attributes": {"group": group, "usagetype": usage_type}}


def _request_terms(sku: str, price_per_request: str, unit: str = "Requests") -> dict:
    return {f"{sku}.T": {"priceDimensions": {f"{sku}.T.1": {"beginRange": "0", "endRange": "Inf", "unit": unit, "pricePerUnit": {"USD": price_per_request}}}}}


def make_s3_offer(usage_type_prefix: str = "", standard_tier2_price_per_request: str = "0.0000004000") -> dict:
    """
    An AmazonS3 price list file: the tier 1 requests, and the tier 2 requests of STANDARD, STANDARD_IA and GLACIER_IR (and of no other
    storage class), plus products that must not be mistaken for them - the annotation requests (in the group of the STANDARD requests,
    at another price here to tell them apart), the S3 Tables requests and the retrieval fee of a storage class (per GB).
    :param usage_type_prefix: what the usage types of the region start with, e.g. "EU-" for eu-west-1 (nothing for us-east-1)
    """
    return {
        "products": {
            "ANNOTATION1": _request_product("S3-API-Tier1", f"{usage_type_prefix}Requests-Annotation-Tier1"),
            "TIER1": _request_product("S3-API-Tier1", f"{usage_type_prefix}Requests-Tier1"),
            "ANNOTATION2": _request_product("S3-API-Tier2", f"{usage_type_prefix}Requests-Annotation-Tier2"),
            "TIER2": _request_product("S3-API-Tier2", f"{usage_type_prefix}Requests-Tier2"),
            "TABLES2": _request_product("S3-API-Tables-Tier2", f"{usage_type_prefix}Tables-Requests-Tier2", None),
            "SIA2": _request_product("S3-API-SIA-Tier2", f"{usage_type_prefix}Requests-SIA-Tier2"),
            "GIR2": _request_product("S3-API-GIR-Tier2", f"{usage_type_prefix}Requests-GIR-Tier2", None),  # as in the real files: not every region has a product family for it
            "GIRRETRIEVAL": _request_product("S3-API-GIR-Retrieval", f"{usage_type_prefix}Retrieval-GIR"),
            "STORAGE": {"productFamily": "Storage", "attributes": {"usagetype": f"{usage_type_prefix}TimedStorage-ByteHrs", "storageClass": "General Purpose"}},
        },
        "terms": {
            "OnDemand": {
                "ANNOTATION1": _request_terms("ANNOTATION1", "0.0000070000"),
                "TIER1": _request_terms("TIER1", "0.0000050000"),
                "ANNOTATION2": _request_terms("ANNOTATION2", "0.0000008000"),
                "TIER2": _request_terms("TIER2", standard_tier2_price_per_request),
                "TABLES2": _request_terms("TABLES2", "0.0000009000"),
                "SIA2": _request_terms("SIA2", "0.0000010000"),
                "GIR2": _request_terms("GIR2", "0.0000100000"),
                "GIRRETRIEVAL": _request_terms("GIRRETRIEVAL", "0.0300000000", "GB"),
                "STORAGE": _request_terms("STORAGE", "0.0230000000", "GB-Mo"),
            }
        },
    }


# the S3 request prices of make_s3_offer(), in USD per 1000 requests as bup has them
s3_tier1_request_price = 0.005
s3_tier2_request_prices = {"STANDARD": 0.0004, "STANDARD_IA": 0.001, "GLACIER_IR": 0.01}


def make_prices(region: str, transfer_out_price_per_gb: float = 0.09, dynamodb_read_price_per_million_units: float = 0.125, fetched: float = 0.0) -> AWSPrices:
    """
    The prices of a region, with the S3 request prices of make_s3_offer().
    """
    return AWSPrices(region, transfer_out_price_per_gb, dynamodb_read_price_per_million_units, fetched, s3_tier1_request_price, dict(s3_tier2_request_prices))


def approx_prices(region: str, transfer_out_price_per_gb: float, fetched: float) -> AWSPrices:
    """
    What the prices that were fetched with make_fetch_offer() are equal to: the prices that are per thousand or per million are close
    to the ones of make_prices(), since they were multiplied.
    """
    tier2_prices = {storage_class: pytest.approx(price) for storage_class, price in s3_tier2_request_prices.items()}
    return AWSPrices(region, transfer_out_price_per_gb, pytest.approx(0.125), fetched, pytest.approx(s3_tier1_request_price), tier2_prices)


def make_fetch_offer(transfer_price_per_gb: str = "0.0900000000", dynamodb_price_per_unit: str = "0.0000001250"):
    """
    A stand-in for bup.aws_prices.fetch_offer that serves the files above for any region, and records what was fetched in its
    "fetched" attribute as (service code, region).
    """

    def fetch_offer(service_code: str, region: str, timeout: float = 60.0) -> dict:
        fetch_offer.fetched.append((service_code, region))
        if service_code == "AWSDataTransfer":
            return make_transfer_offer(region, transfer_price_per_gb)
        if service_code == "AmazonS3":
            return make_s3_offer()
        return make_dynamodb_offer(dynamodb_price_per_unit)

    fetch_offer.fetched = []
    return fetch_offer
