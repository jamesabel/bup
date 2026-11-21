"""
AWS Price List files for tests, cut down from the real ones (same structure, a few of the products).
Everything in this file is AI-authored (Claude Code).
"""


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


def make_fetch_offer(transfer_price_per_gb: str = "0.0900000000", dynamodb_price_per_unit: str = "0.0000001250"):
    """
    A stand-in for bup.aws_prices.fetch_offer that serves the files above for any region, and records what was fetched in its
    "fetched" attribute as (service code, region).
    """

    def fetch_offer(service_code: str, region: str, timeout: float = 60.0) -> dict:
        fetch_offer.fetched.append((service_code, region))
        if service_code == "AWSDataTransfer":
            return make_transfer_offer(region, transfer_price_per_gb)
        return make_dynamodb_offer(dynamodb_price_per_unit)

    fetch_offer.fetched = []
    return fetch_offer
