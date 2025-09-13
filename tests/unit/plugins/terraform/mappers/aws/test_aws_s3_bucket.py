from __future__ import annotations

import logging
from typing import Any

import pytest

from src.plugins.terraform.mappers.aws.aws_s3_bucket import AWSS3BucketMapper


class FakeNodeBuilder:
    def __init__(self, name: str, node_type: str, sink: dict[str, Any]) -> None:
        self.name = name
        self.node_type = node_type
        self._sink = sink
        self._sink[self.name] = {
            "type": node_type,
            "properties": {},
            "metadata": {},
        }

    def with_property(self, name: str, value: Any) -> FakeNodeBuilder:
        self._sink[self.name]["properties"][name] = value
        return self

    def with_metadata(self, metadata: dict[str, Any]) -> FakeNodeBuilder:
        self._sink[self.name]["metadata"].update(metadata)
        return self


class FakeBuilder:
    """Minimal builder collecting created nodes."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}

    def add_node(self, name: str, node_type: str) -> FakeNodeBuilder:
        return FakeNodeBuilder(name, node_type, self.nodes)


class TestCanMap:
    def test_can_map_true_for_s3(self) -> None:
        m = AWSS3BucketMapper()
        assert m.can_map("aws_s3_bucket", {"values": {}}) is True

    def test_can_map_false_for_other_type(self) -> None:
        m = AWSS3BucketMapper()
        assert m.can_map("aws_instance", {"values": {}}) is False


class TestMapResource:
    def test_map_resource_happy_path(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        m = AWSS3BucketMapper()
        b = FakeBuilder()
        res_name = "aws_s3_bucket.my-bucket[0]"
        res_type = "aws_s3_bucket"
        data = {
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "values": {
                "bucket": "my-bucket",
                "region": "eu-west-1",
                "arn": "arn:aws:s3:::my-bucket",
                "force_destroy": False,
                "object_lock_enabled": True,
                "tags": {"env": "prod"},
                "tags_all": {"team": "devops"},
                "bucket_domain_name": "my-bucket.s3.amazonaws.com",
                "bucket_region": "eu-west-1",
                "bucket_regional_domain_name": "my-bucket.s3.eu-west-1.amazonaws.com",
                "hosted_zone_id": "Z3AQBSTGFYJSTF",
                # extra field to verify metadata passthrough
                "versioning": {"enabled": True},
            },
        }

        m.map_resource(res_name, res_type, data, b)

        # Expected node name: aws_s3_bucket_my_bucket_0
        assert "aws_s3_bucket_my_bucket_0" in b.nodes
        node = b.nodes["aws_s3_bucket_my_bucket_0"]

        # Correct TOSCA type
        assert node["type"] == "Storage.ObjectStorage"

        # Standard properties
        assert node["properties"]["name"] == "my-bucket"

        # Mapped metadata
        md = node["metadata"]
        assert md["original_resource_type"] == "aws_s3_bucket"
        assert md["original_resource_name"] == "my-bucket[0]"
        assert md["aws_provider"] == "registry.terraform.io/hashicorp/aws"
        assert md["aws_region"] == "eu-west-1"
        assert md["aws_arn"] == "arn:aws:s3:::my-bucket"
        assert md["aws_force_destroy"] is False
        assert md["aws_object_lock_enabled"] is True
        assert md["aws_tags"] == {"env": "prod"}
        assert md["aws_tags_all"] == {"team": "devops"}
        assert md["aws_bucket_domain_name"] == "my-bucket.s3.amazonaws.com"
        assert md["aws_bucket_region"] == "eu-west-1"
        assert md["aws_bucket_regional_domain_name"] == (
            "my-bucket.s3.eu-west-1.amazonaws.com"
        )
        assert md["aws_hosted_zone_id"] == "Z3AQBSTGFYJSTF"

        # Extra field ends up in metadata prefixed with aws_
        assert md["aws_versioning"] == {"enabled": True}

        # Informational log
        assert any("Mapping S3 Bucket resource" in r.message for r in caplog.records)

    def test_map_resource_without_values_is_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSS3BucketMapper()
        b = FakeBuilder()
        m.map_resource("aws_s3_bucket.empty", "aws_s3_bucket", {}, b)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_map_with_plain_name_no_dot(self) -> None:
        m = AWSS3BucketMapper()
        b = FakeBuilder()
        data = {"values": {"bucket": "plain"}}
        m.map_resource("plain", "aws_s3_bucket", data, b)
        # Node name: prefix + clean name
        assert "aws_s3_bucket_plain" in b.nodes
        md = b.nodes["aws_s3_bucket_plain"]["metadata"]
        # original_resource_name matches the passed name
        assert md["original_resource_name"] == "plain"
