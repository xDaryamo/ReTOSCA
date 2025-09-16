"""Unit tests for AWSEBSVolumeMapper."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from src.plugins.provisioning.terraform.mappers.aws.aws_ebs_volume import (
    AWSEBSVolumeMapper,
)


class FakeCapabilityBuilder:
    def __init__(
        self,
        parent: FakeNodeBuilder,
        sink: dict[str, Any],
        node_name: str,
        cap_name: str,
    ) -> None:
        self._parent = parent
        sink[node_name]["capabilities"].append(cap_name)

    def and_node(self) -> FakeNodeBuilder:
        return self._parent


class FakeNodeBuilder:
    def __init__(self, name: str, node_type: str, sink: dict[str, Any]) -> None:
        self.name = name
        self.node_type = node_type
        self._sink = sink
        self._sink[self.name] = {
            "type": node_type,
            "properties": {},
            "metadata": {},
            "capabilities": [],
        }

    def with_property(self, name: str, value: Any) -> FakeNodeBuilder:
        self._sink[self.name]["properties"][name] = value
        return self

    def with_metadata(self, metadata: dict[str, Any]) -> FakeNodeBuilder:
        self._sink[self.name]["metadata"].update(metadata)
        return self

    def add_capability(self, cap_name: str) -> FakeCapabilityBuilder:
        return FakeCapabilityBuilder(self, self._sink, self.name, cap_name)


class FakeBuilder:
    """Minimal builder collecting created nodes."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}

    def add_node(self, name: str, node_type: str) -> FakeNodeBuilder:
        return FakeNodeBuilder(name, node_type, self.nodes)


class TestCanMap:
    def test_can_map_true_for_ebs(self) -> None:
        m = AWSEBSVolumeMapper()
        assert m.can_map("aws_ebs_volume", {"values": {}}) is True

    def test_can_map_false_for_other_type(self) -> None:
        m = AWSEBSVolumeMapper()
        assert m.can_map("aws_instance", {"values": {}}) is False


class TestMapResource:
    def test_map_resource_happy_path(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        m = AWSEBSVolumeMapper()
        b = FakeBuilder()
        res_name = "aws_ebs_volume.data[0]"
        res_type = "aws_ebs_volume"
        data = {
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "values": {
                "size": 20,
                "id": "vol-123",
                "snapshot_id": "snap-1",
                "availability_zone": "eu-west-1a",
                "region": "eu-west-1",
                "encrypted": True,
                "kms_key_id": "arn:kms:key/abc",
                "type": "gp3",
                "iops": 3000,
                "throughput": 125,
                "multi_attach_enabled": False,
                "outpost_arn": "arn:aws:outposts:...:outpost/op-xyz",
                "final_snapshot": "final-snap",
                "volume_initialization_rate": 100,
                "arn": "arn:aws:ec2:...:volume/vol-123",
                "create_time": "2025-01-01T12:00:00Z",
                "tags": {"env": "prod"},
                "tags_all": {"team": "devops"},
            },
        }

        m.map_resource(res_name, res_type, data, b)

        # Expected node name: aws_ebs_volume_data_0
        assert "aws_ebs_volume_data_0" in b.nodes
        node = b.nodes["aws_ebs_volume_data_0"]

        # Correct TOSCA type
        assert node["type"] == "Storage.BlockStorage"

        # Standard properties
        props = node["properties"]
        assert props["size"] == "20 GB"
        assert props["volume_id"] == "vol-123"
        assert props["snapshot_id"] == "snap-1"

        # Mapped metadata
        md = node["metadata"]
        assert md["original_resource_type"] == "aws_ebs_volume"
        assert md["original_resource_name"] == "data[0]"
        assert md["aws_provider"] == "registry.terraform.io/hashicorp/aws"
        assert md["aws_availability_zone"] == "eu-west-1a"
        assert md["aws_region"] == "eu-west-1"
        assert md["aws_encrypted"] is True
        assert md["aws_kms_key_id"] == "arn:kms:key/abc"
        assert md["aws_volume_type"] == "gp3"
        assert md["aws_iops"] == 3000
        assert md["aws_throughput"] == 125
        assert md["aws_multi_attach_enabled"] is False
        assert md["aws_outpost_arn"].startswith("arn:aws:outposts")
        assert md["aws_final_snapshot"] == "final-snap"
        assert md["aws_volume_initialization_rate"] == 100
        assert md["aws_arn"].startswith("arn:aws:ec2")
        assert md["aws_create_time"] == "2025-01-01T12:00:00Z"
        assert md["aws_tags"] == {"env": "prod"}
        assert md["aws_tags_all"] == {"team": "devops"}

        # "attachment" capability added
        assert "attachment" in node["capabilities"]

        # Informational log
        assert any("Mapping EBS Volume resource" in r.message for r in caplog.records)

    def test_map_resource_without_values_is_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSEBSVolumeMapper()
        b = FakeBuilder()
        m.map_resource("aws_ebs_volume.empty", "aws_ebs_volume", {}, b)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_map_with_plain_name_no_dot(self) -> None:
        m = AWSEBSVolumeMapper()
        b = FakeBuilder()
        data = {"values": {"size": 1}}
        m.map_resource("vol1", "aws_ebs_volume", data, b)
        assert "aws_ebs_volume_vol1" in b.nodes
        md = b.nodes["aws_ebs_volume_vol1"]["metadata"]
        assert md["original_resource_name"] == "vol1"

    def test_size_zero_not_set(self) -> None:
        m = AWSEBSVolumeMapper()
        b = FakeBuilder()
        data = {"values": {"size": 0}}
        m.map_resource("zero", "aws_ebs_volume", data, b)
        props = b.nodes["aws_ebs_volume_zero"]["properties"]
        assert "size" not in props
