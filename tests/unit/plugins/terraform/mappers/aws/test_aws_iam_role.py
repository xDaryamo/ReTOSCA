from __future__ import annotations

from typing import Any

import pytest

from src.plugins.provisioning.terraform.mappers.aws.aws_iam_role import (
    AWSIAMRoleMapper,
)


class FakeReq:
    def __init__(self, node: FakeNode, name: str) -> None:
        self.node = node
        self.name = name
        self.target: str | None = None
        self.relationship: str | None = None

    def to_node(self, target: str) -> FakeReq:
        self.target = target
        return self

    def with_relationship(self, rel: str) -> FakeReq:
        self.relationship = rel
        return self

    def and_node(self) -> FakeNode:
        self.node.requirements.append((self.name, self.target, self.relationship))
        return self.node


class FakeNode:
    def __init__(self, name: str, node_type: str) -> None:
        self.name = name
        self.node_type = node_type
        self.metadata: dict[str, Any] = {}
        self.requirements: list[tuple[str, str | None, str | None]] = []
        self.properties: dict[str, Any] = {}
        self.description: str | None = None

    # Mapper APIs used
    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self.metadata = md
        return self

    def with_property(self, name: str, value: Any) -> FakeNode:
        self.properties[name] = value
        return self

    def add_requirement(self, name: str) -> FakeReq:
        return FakeReq(self, name)

    def with_description(self, desc: str) -> FakeNode:
        self.description = desc
        return self


class FakeBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, FakeNode] = {}

    def add_node(self, name: str, node_type: str) -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node


class TestCanMap:
    def test_true_for_iam_role(self) -> None:
        mapper = AWSIAMRoleMapper()
        assert mapper.can_map("aws_iam_role", {}) is True

    def test_false_for_other_types(self) -> None:
        mapper = AWSIAMRoleMapper()
        assert mapper.can_map("aws_vpc", {}) is False


class TestMapIAMRole:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        mapper = AWSIAMRoleMapper()
        b = FakeBuilder()

        mapper.map_resource("aws_iam_role.empty", "aws_iam_role", {}, b)

        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_maps_metadata_and_properties(self) -> None:
        mapper = AWSIAMRoleMapper()
        b = FakeBuilder()

        resource_name = "aws_iam_role.test_role"
        values = {
            "name": "test_role",
            "assume_role_policy": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ec2.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                        "Sid": "",
                    }
                ],
            },
            "path": "/",
            "max_session_duration": 3600,
            "force_detach_policies": False,
            "tags": {"tag-key": "tag-value"},
            # optional extras often present
            "arn": "arn:aws:iam::123:role/test_role",
            "id": "test_role",
        }
        resource_data = {
            "values": values,
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }

        mapper.map_resource(resource_name, "aws_iam_role", resource_data, b)

        # Node name is derived via BaseResourceMapper.generate_tosca_node_name
        assert "aws_iam_role_test_role" in b.nodes
        node = b.nodes["aws_iam_role_test_role"]

        # Type as per YAML example
        assert node.node_type == "SoftwareComponent"

        md = node.metadata
        assert md["original_resource_type"] == "aws_iam_role"
        assert md["original_resource_name"] == "test_role"
        assert md["aws_provider"] == ("registry.terraform.io/hashicorp/aws")

        # Key IAM fields
        assert md["aws_role_name"] == "test_role"
        assert md["aws_assume_role_policy"]["Version"] == "2012-10-17"
        assert md["aws_role_path"] == "/"
        assert md["aws_max_session_duration"] == 3600
        assert md["aws_force_detach_policies"] is False
        assert md["aws_tags"] == {"tag-key": "tag-value"}

        # If the mapper sets a stable component version, verify it
        # (matches the example YAML)
        assert node.properties.get("component_version") == "1.0"

    def test_minimal_role_maps_cleanly(self) -> None:
        mapper = AWSIAMRoleMapper()
        b = FakeBuilder()

        resource_name = "aws_iam_role.minimal"
        values = {
            "name": "minimal",
            "assume_role_policy": {"Version": "2012-10-17", "Statement": []},
        }
        resource_data = {"values": values}

        mapper.map_resource(resource_name, "aws_iam_role", resource_data, b)

        assert "aws_iam_role_minimal" in b.nodes
        node = b.nodes["aws_iam_role_minimal"]

        assert node.node_type in ("SoftwareComponent", "Root")
        assert node.metadata["original_resource_name"] == "minimal"
        assert node.metadata["aws_role_name"] == "minimal"
        assert node.metadata["aws_assume_role_policy"]["Version"] == "2012-10-17"
