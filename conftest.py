"""
Test configuration for the whole repository. All fixtures in this file are AI-authored (Claude Code).
"""

import urllib.request

import pytest
from moto.server import ThreadedMotoServer


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


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def moto_s3_endpoint(monkeypatch, tmp_path):
    """
    A local in-memory S3 server, with the environment set up so boto3 and awsimple talk to it and not real AWS.
    :return: the URL of the server
    """
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    endpoint_url = f"http://{host}:{port}"
    monkeypatch.setenv("AWS_ENDPOINT_URL", endpoint_url)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    # keep any real AWS profile/config on this machine from leaking into the test
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials-file"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config-file"))
    # moto keeps its buckets in this process, across servers: start without the buckets of earlier tests, and leave none behind
    reset_request = urllib.request.Request(f"{endpoint_url}/moto-api/reset", method="POST")
    urllib.request.urlopen(reset_request, timeout=10.0).close()
    yield endpoint_url
    urllib.request.urlopen(reset_request, timeout=10.0).close()
    server.stop()
