from __future__ import annotations

from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper
from src.plugins.provisioning.terraform.mappers.aws.aws_route53_zone import (
    AWSRoute53ZoneMapper,
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
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.requirements: list[tuple[str, str | None, str | None]] = []

    # APIs used by mapper
    def with_properties(self, props: dict[str, Any]) -> FakeNode:
        self.properties.update(props)
        return self

    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self.metadata = md
        return self

    def add_requirement(self, name: str) -> FakeReq:
        return FakeReq(self, name)


class FakeBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, FakeNode] = {}

    def add_node(self, name: str, node_type: str) -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node

    def get_node(self, name: str) -> FakeNode:
        if name not in self.nodes:
            raise KeyError(name)
        return self.nodes[name]


class DummyCtx:
    """Minimal context: resolves values and provides a VPC ref for dependency tests."""

    def __init__(self, add_vpc_ref: bool = False) -> None:
        self._add_vpc_ref = add_vpc_ref
        self.parsed_data = {}  # not used by mapper in these tests

    def get_resolved_values(
        self, resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        return resource_data.get("values", {})

    def extract_terraform_references(
        self, resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        if self._add_vpc_ref:
            # Simulates a reference from the 'vpc' field to the aws_vpc.main resource
            return [("vpc", "aws_vpc.main", "DependsOn")]
        return []


class TestCanMap:
    def test_true_for_route53_zone(self) -> None:
        m = AWSRoute53ZoneMapper()
        assert m.can_map("aws_route53_zone", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSRoute53ZoneMapper()
        assert m.can_map("aws_route53_record", {}) is False


class TestGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSRoute53ZoneMapper()
        b = FakeBuilder()
        m.map_resource(
            "aws_route53_zone.primary", "aws_route53_zone", {}, b, context=None
        )
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)


class TestPublicZone:
    def test_maps_public_zone_properties_and_metadata(self) -> None:
        m = AWSRoute53ZoneMapper()
        b = FakeBuilder()

        resource = {
            "values": {
                "name": "example.com",
                "comment": "Public zone",
                "vpc": [],  # public
                "tags": {"env": "prod"},
                "arn": "arn:aws:route53:::hostedzone/Z123",
                "zone_id": "Z123",
                "name_servers": ["ns-1", "ns-2"],
                "primary_name_server": "ns-primary",
                "id": "Z123",
            }
        }

        m.map_resource(
            "aws_route53_zone.primary", "aws_route53_zone", resource, b, context=None
        )

        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route53_zone.primary", "aws_route53_zone"
        )
        node = b.get_node(node_name)

        # Node type and network properties
        assert node.node_type == "Network"
        assert node.properties["network_name"] == "example.com"
        assert node.properties["network_type"] == "public"
        assert node.properties["dhcp_enabled"] is False

        # Main metadata
        md = node.metadata
        assert md["aws_component_type"] == "Route53HostedZone"
        assert md["aws_domain_name"] == "example.com"
        assert md["aws_zone_type"] == "public"
        assert md["aws_zone_id"] == "Z123"
        assert md["aws_hosted_zone_id"] == "Z123"
        assert md["aws_arn"].endswith("Z123")
        assert md["aws_name_servers"] == ["ns-1", "ns-2"]
        assert md["aws_primary_name_server"] == "ns-primary"
        assert md["aws_tags"] == {"env": "prod"}


class TestPrivateZone:
    def test_maps_private_zone_sets_private_and_vpc_metadata(self) -> None:
        m = AWSRoute53ZoneMapper()
        b = FakeBuilder()

        resource = {
            "values": {
                "name": "corp.local",
                "comment": "Private zone",
                "vpc": [{"vpc_id": "vpc-abc", "vpc_region": "eu-west-1"}],
                "zone_id": "Z999",
                "id": "Z999",
            }
        }

        m.map_resource(
            "aws_route53_zone.private", "aws_route53_zone", resource, b, context=None
        )

        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route53_zone.private", "aws_route53_zone"
        )
        node = b.get_node(node_name)

        # Properties: private + dhcp_enabled True
        assert node.properties["network_type"] == "private"
        assert node.properties["dhcp_enabled"] is True

        # Metadata: presence of VPC associations and private type
        md = node.metadata
        assert md["aws_zone_type"] == "private"
        assert md["aws_vpc_associations"] == [
            {"vpc_id": "vpc-abc", "vpc_region": "eu-west-1"}
        ]


class TestDependencies:
    def test_adds_dependency_requirements_from_context(self) -> None:
        m = AWSRoute53ZoneMapper()
        b = FakeBuilder()
        ctx = DummyCtx(add_vpc_ref=True)

        resource = {
            "values": {
                "name": "example.org",
                "vpc": [{"vpc_id": "vpc-xyz", "vpc_region": "us-east-1"}],
                "zone_id": "Z777",
                "id": "Z777",
            }
        }

        m.map_resource(
            "aws_route53_zone.dep", "aws_route53_zone", resource, b, context=ctx
        )

        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route53_zone.dep", "aws_route53_zone"
        )
        node = b.get_node(node_name)

        # Expected a "vpc" requirement toward aws_vpc_main with DependsOn relationship
        vpc_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_vpc.main", "aws_vpc"
        )
        assert ("vpc", vpc_node_name, "DependsOn") in node.requirements
