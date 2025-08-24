from __future__ import annotations

from typing import Any

import pytest

from src.plugins.terraform.mapper import TerraformMapper
from src.plugins.terraform.mappers.aws.aws_volume_attachment import (
    AWSVolumeAttachmentMapper,
)


class FakeReq:
    def __init__(self, node: FakeNode, name: str) -> None:
        self.node = node
        self.name = name
        self.target: str | None = None
        self.relationship: Any = None

    def to_node(self, target: str) -> FakeReq:
        self.target = target
        return self

    def with_relationship(self, rel: Any) -> FakeReq:
        self.relationship = rel
        return self

    def and_node(self) -> FakeNode:
        self.node.requirements.append((self.name, self.target, self.relationship))
        return self.node


class FakeNode:
    def __init__(self, name: str, node_type: str) -> None:
        self.name = name
        self.node_type = node_type
        self.requirements: list[tuple[str, str | None, Any]] = []

    def add_requirement(self, name: str) -> FakeReq:
        return FakeReq(self, name)


class FakeBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, FakeNode] = {}

    def add_node(self, name: str, node_type: str) -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node

    # Mapper expects this method; raise KeyError if not found
    def get_node(self, name: str) -> FakeNode:
        return self.nodes[name]


# Helper to ensure a TerraformMapper is on the call stack so that
# the mapper can extract references via inspect.stack().
class Harness(TerraformMapper):
    def invoke(
        self,
        mapper: AWSVolumeAttachmentMapper,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: FakeBuilder,
        parsed_data: dict[str, Any],
    ) -> None:
        self._current_parsed_data = parsed_data
        mapper.map_resource(resource_name, resource_type, resource_data, builder)


class TestCanMap:
    def test_true_for_attachment(self) -> None:
        m = AWSVolumeAttachmentMapper()
        assert m.can_map("aws_volume_attachment", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSVolumeAttachmentMapper()
        assert m.can_map("aws_instance", {}) is False


class TestValidationGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSVolumeAttachmentMapper()
        b = FakeBuilder()
        m.map_resource("aws_volume_attachment.att", "aws_volume_attachment", {}, b)
        # no nodes modified
        assert all(len(n.requirements) == 0 for n in b.nodes.values())
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_skips_when_no_device_name(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSVolumeAttachmentMapper()
        b = FakeBuilder()
        rd = {"address": "aws_volume_attachment.att", "values": {"device_name": ""}}
        m.map_resource("aws_volume_attachment.att", "aws_volume_attachment", rd, b)
        assert all(len(n.requirements) == 0 for n in b.nodes.values())
        assert any("No device_name found" in r.message for r in caplog.records)

    def test_skips_when_no_references_available(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # No TerraformMapper on the stack -> references cannot be resolved
        caplog.set_level("WARNING")
        m = AWSVolumeAttachmentMapper()
        b = FakeBuilder()
        rd = {
            "address": "aws_volume_attachment.att",
            "values": {"device_name": "/dev/sdh"},
        }
        m.map_resource("aws_volume_attachment.att", "aws_volume_attachment", rd, b)
        assert all(len(n.requirements) == 0 for n in b.nodes.values())
        assert any(
            "Could not resolve instance or volume references" in r.message
            for r in caplog.records
        )


class TestHappyPath:
    def test_adds_local_storage_requirement(self) -> None:
        m = AWSVolumeAttachmentMapper()
        b = FakeBuilder()
        h = Harness()

        # Pre-create the instance and volume nodes that the mapper will link
        inst = b.add_node("aws_instance_web", "Compute")
        vol = b.add_node("aws_ebs_volume_data", "Storage.BlockStorage")
        assert inst and vol  # sanity

        resource_name = "aws_volume_attachment.ebs_att"
        resource_type = "aws_volume_attachment"
        resource_data = {
            "address": resource_name,
            "values": {"device_name": "/dev/sdh"},
        }

        parsed = {
            "configuration": {
                "root_module": {
                    "resources": [
                        {
                            "address": resource_name,
                            "expressions": {
                                "instance_id": {"references": ["aws_instance.web.id"]},
                                "volume_id": {"references": ["aws_ebs_volume.data.id"]},
                            },
                        }
                    ]
                }
            }
        }

        h.invoke(m, resource_name, resource_type, resource_data, b, parsed)

        # Expect exactly one requirement on the instance node
        reqs = b.nodes["aws_instance_web"].requirements
        assert len(reqs) == 1
        name, target, rel = reqs[0]
        assert name == "local_storage"
        assert target == "aws_ebs_volume_data"
        assert isinstance(rel, dict)
        assert rel["type"] == "AttachesTo"
        assert rel["properties"]["device"] == "/dev/sdh"
        # mount point derived from device name
        assert rel["properties"]["location"] == "/mnt/sdh"

    def test_missing_instance_node_skips(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSVolumeAttachmentMapper()
        b = FakeBuilder()
        h = Harness()

        # Only volume node exists
        b.add_node("aws_ebs_volume_data", "Storage.BlockStorage")

        rd = {
            "address": "aws_volume_attachment.ebs_att",
            "values": {"device_name": "/dev/sdh"},
        }
        parsed = {
            "configuration": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_volume_attachment.ebs_att",
                            "expressions": {
                                "instance_id": {"references": ["aws_instance.web.id"]},
                                "volume_id": {"references": ["aws_ebs_volume.data.id"]},
                            },
                        }
                    ]
                }
            }
        }

        h.invoke(
            m, "aws_volume_attachment.ebs_att", "aws_volume_attachment", rd, b, parsed
        )

        # No requirement added
        assert all(len(n.requirements) == 0 for n in b.nodes.values())
        assert any(
            "Instance node 'aws_instance_web' not found" in r.message
            for r in caplog.records
        )

    def test_missing_volume_node_skips(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSVolumeAttachmentMapper()
        b = FakeBuilder()
        h = Harness()

        # Only instance node exists
        b.add_node("aws_instance_web", "Compute")

        rd = {
            "address": "aws_volume_attachment.ebs_att",
            "values": {"device_name": "/dev/sdh"},
        }
        parsed = {
            "configuration": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_volume_attachment.ebs_att",
                            "expressions": {
                                "instance_id": {"references": ["aws_instance.web.id"]},
                                "volume_id": {"references": ["aws_ebs_volume.data.id"]},
                            },
                        }
                    ]
                }
            }
        }

        h.invoke(
            m, "aws_volume_attachment.ebs_att", "aws_volume_attachment", rd, b, parsed
        )

        # No requirement added
        assert all(len(n.requirements) == 0 for n in b.nodes.values())
        assert any(
            "Volume node 'aws_ebs_volume_data' not found" in r.message
            for r in caplog.records
        )


class TestMountPointHelper:
    def test_generate_mount_point_from_plain_name(self) -> None:
        m = AWSVolumeAttachmentMapper()
        assert m._generate_mount_point("xvdf") == "/mnt/xvdf"

    def test_generate_mount_point_from_path(self) -> None:
        m = AWSVolumeAttachmentMapper()
        assert m._generate_mount_point("/dev/nvme1n1") == "/mnt/nvme1n1"

    def test_generate_mount_point_empty(self) -> None:
        m = AWSVolumeAttachmentMapper()
        assert m._generate_mount_point("") == "unspecified"
