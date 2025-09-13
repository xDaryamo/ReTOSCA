"""Unit tests for AWSInternetGatewayMapper."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from src.plugins.terraform.mappers.aws.aws_internet_gateway import (
    AWSInternetGatewayMapper,
)


class FakeRequirementBuilder:
    def __init__(
        self,
        parent: FakeNodeBuilder,
        sink: dict[str, Any],
        node_name: str,
        req_name: str,
    ) -> None:
        self._parent = parent
        self._sink = sink
        self._node_name = node_name
        self._req_name = req_name
        self._req: dict[str, Any] = {}

    def to_node(self, target: str) -> FakeRequirementBuilder:
        self._req["node"] = target
        return self

    def with_relationship(self, rel: str) -> FakeRequirementBuilder:
        self._req["relationship"] = rel
        return self

    def and_node(self) -> FakeNodeBuilder:
        self._sink[self._node_name]["requirements"].append({self._req_name: self._req})
        return self._parent


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
        sink[self.name] = {
            "type": node_type,
            "properties": {},
            "metadata": {},
            "capabilities": [],
            "requirements": [],
        }

    def with_property(self, name: str, value: Any) -> FakeNodeBuilder:
        self._sink[self.name]["properties"][name] = value
        return self

    def with_metadata(self, metadata: dict[str, Any]) -> FakeNodeBuilder:
        self._sink[self.name]["metadata"].update(metadata)
        return self

    def add_capability(self, cap_name: str) -> FakeCapabilityBuilder:
        return FakeCapabilityBuilder(self, self._sink, self.name, cap_name)

    def add_requirement(self, req_name: str) -> FakeRequirementBuilder:
        return FakeRequirementBuilder(self, self._sink, self.name, req_name)


class FakeBuilder:
    """Collects created nodes."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}

    def add_node(self, name: str, node_type: str) -> FakeNodeBuilder:
        return FakeNodeBuilder(name, node_type, self.nodes)


class TestCanMap:
    def test_can_map_true_for_igw(self) -> None:
        m = AWSInternetGatewayMapper()
        assert m.can_map("aws_internet_gateway", {"values": {}}) is True

    def test_can_map_true_for_egress_only_igw(self) -> None:
        m = AWSInternetGatewayMapper()
        assert m.can_map("aws_egress_only_internet_gateway", {"values": {}}) is True

    def test_can_map_false_for_other(self) -> None:
        m = AWSInternetGatewayMapper()
        assert m.can_map("aws_subnet", {"values": {}}) is False


class TestMapResource:
    def test_map_happy_path_with_dependency(self) -> None:
        m = AWSInternetGatewayMapper()
        b = FakeBuilder()
        res_name = "aws_internet_gateway.gw[0]"
        res_type = "aws_internet_gateway"
        data = {
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "address": res_name,
            "values": {
                "vpc_id": "vpc-123",
                "region": "eu-west-1",
                "tags": {"Name": "main-igw", "env": "prod"},
            },
        }

        # Create mock context that returns a dependency
        class FakeContext:
            def extract_terraform_references(self, resource_data: dict[str, Any]):
                return [("vpc_id", "aws_vpc_main", "DependsOn")]

            def get_resolved_values(
                self, resource_data: dict[str, Any], context_type: str
            ):
                return resource_data.get("values", {})

            def generate_tosca_node_name_from_address(
                self, resource_address: str, resource_type: str | None = None
            ):
                return "aws_internet_gateway_gw_0"

        context = FakeContext()
        m.map_resource(res_name, res_type, data, b, context)

        node_name = "aws_internet_gateway_gw_0"
        assert node_name in b.nodes
        node = b.nodes[node_name]

        # Type and properties
        assert node["type"] == "Network"
        assert node["properties"]["network_type"] == "public"
        assert node["properties"]["network_name"] == "IGW-main-igw"
        assert node["properties"]["ip_version"] == 4

        # Metadata
        md = node["metadata"]
        assert md["original_resource_type"] == "aws_internet_gateway"
        assert md["original_resource_name"] == "gw[0]"
        assert md["aws_component_type"] == "InternetGateway"
        assert md["aws_gateway_type"] == "standard"
        assert md["aws_traffic_direction"] == "bidirectional"
        assert md["aws_ip_version_support"] == "ipv4_ipv6"
        assert "AWS Internet Gateway providing bidirectional" in md["description"]
        assert md["aws_provider"].startswith("registry.terraform.io")
        assert md["aws_vpc_id"] == "vpc-123"
        assert md["aws_region"] == "eu-west-1"
        assert md["aws_tags"]["env"] == "prod"
        assert md["aws_name"] == "main-igw"

        # Capability
        assert "link" in node["capabilities"]

        # Dependency requirement to VPC
        reqs = node["requirements"]
        assert len(reqs) == 1
        dep = reqs[0]["dependency"]
        assert dep["node"] == "aws_vpc_main"
        assert dep["relationship"] == "DependsOn"

    def test_map_without_values_is_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSInternetGatewayMapper()
        b = FakeBuilder()
        m.map_resource("aws_internet_gateway.empty", "aws_internet_gateway", {}, b)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_map_no_context_no_dependency(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSInternetGatewayMapper()
        b = FakeBuilder()
        data = {"values": {"vpc_id": "vpc-1"}}
        m.map_resource("aws_internet_gateway.gw", "aws_internet_gateway", data, b)

        node = b.nodes["aws_internet_gateway_gw"]
        assert node["requirements"] == []
        assert any(
            "No context provided to detect dependencies" in r.message
            for r in caplog.records
        )

    def test_name_tag_absent_uses_default_network_name(self) -> None:
        m = AWSInternetGatewayMapper()
        b = FakeBuilder()
        data = {"values": {"region": "eu-west-1", "tags": {"env": "dev"}}}
        m.map_resource("aws_internet_gateway.simple", "aws_internet_gateway", data, b)
        node = b.nodes["aws_internet_gateway_simple"]
        assert node["properties"]["network_name"] == "IGW-simple"
        assert node["properties"]["network_type"] == "public"

    def test_plain_resource_name_no_dot_original_name(self) -> None:
        m = AWSInternetGatewayMapper()
        b = FakeBuilder()
        data = {"values": {"vpc_id": "vpc-1"}}
        m.map_resource("igw1", "aws_internet_gateway", data, b)
        node = b.nodes["aws_internet_gateway_igw1"]
        assert node["metadata"]["original_resource_name"] == "igw1"

    def test_map_egress_only_igw_with_dependency(self) -> None:
        """Test mapping of aws_egress_only_internet_gateway with specific metadata."""
        m = AWSInternetGatewayMapper()
        b = FakeBuilder()
        res_name = "aws_egress_only_internet_gateway.egress"
        res_type = "aws_egress_only_internet_gateway"
        data = {
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "address": res_name,
            "values": {
                "vpc_id": "vpc-456",
                "region": "us-east-1",
                "tags": {"Name": "egress-gw", "purpose": "ipv6-outbound"},
            },
        }

        # Create mock context that returns a dependency
        class FakeContext:
            def extract_terraform_references(self, resource_data: dict[str, Any]):
                return [("vpc_id", "aws_vpc_main", "DependsOn")]

            def get_resolved_values(
                self, resource_data: dict[str, Any], context_type: str
            ):
                return resource_data.get("values", {})

            def generate_tosca_node_name_from_address(
                self, resource_address: str, resource_type: str | None = None
            ):
                return "aws_egress_only_internet_gateway_egress"

        context = FakeContext()
        m.map_resource(res_name, res_type, data, b, context)

        node_name = "aws_egress_only_internet_gateway_egress"
        assert node_name in b.nodes
        node = b.nodes[node_name]

        # Type and properties specific to egress-only gateway
        assert node["type"] == "Network"
        assert node["properties"]["network_type"] == "egress_only"
        assert node["properties"]["network_name"] == "EIGW-egress-gw"
        assert node["properties"]["ip_version"] == 6

        # Metadata specific to egress-only gateway
        md = node["metadata"]
        assert md["original_resource_type"] == "aws_egress_only_internet_gateway"
        assert md["original_resource_name"] == "egress"
        assert md["aws_component_type"] == "EgressOnlyInternetGateway"
        assert md["aws_gateway_type"] == "egress_only"
        assert md["aws_traffic_direction"] == "outbound_only"
        assert md["aws_ip_version_support"] == "ipv6_only"
        assert (
            "Egress-only Internet Gateway providing IPv6 outbound" in md["description"]
        )
        assert md["aws_provider"].startswith("registry.terraform.io")
        assert md["aws_region"] == "us-east-1"
        assert md["aws_tags"]["purpose"] == "ipv6-outbound"
        assert md["aws_name"] == "egress-gw"

        # Capability
        assert "link" in node["capabilities"]

        # Dependency requirement to VPC
        reqs = node["requirements"]
        assert len(reqs) == 1
        dep = reqs[0]["dependency"]
        assert dep["node"] == "aws_vpc_main"
        assert dep["relationship"] == "DependsOn"

    def test_map_egress_only_igw_without_name_tag(self) -> None:
        """Test egress-only gateway without Name tag uses default naming."""
        m = AWSInternetGatewayMapper()
        b = FakeBuilder()
        data = {"values": {"region": "eu-west-1", "tags": {"env": "test"}}}
        m.map_resource(
            "aws_egress_only_internet_gateway.test",
            "aws_egress_only_internet_gateway",
            data,
            b,
        )
        node = b.nodes["aws_egress_only_internet_gateway_test"]
        assert node["properties"]["network_name"] == "EIGW-test"
        assert node["properties"]["network_type"] == "egress_only"
        assert node["properties"]["ip_version"] == 6
