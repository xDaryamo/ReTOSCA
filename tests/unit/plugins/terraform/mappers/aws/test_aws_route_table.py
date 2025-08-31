from __future__ import annotations

import logging
from typing import Any

import pytest

from src.plugins.terraform.mappers.aws.aws_route_table import (
    AWSRouteTableMapper,
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


# --------------------------- Tests ---------------------------


class TestCanMap:
    def test_can_map_true_for_route_table(self) -> None:
        m = AWSRouteTableMapper()
        assert m.can_map("aws_route_table", {"values": {}}) is True

    def test_can_map_false_for_other(self) -> None:
        m = AWSRouteTableMapper()
        assert m.can_map("aws_subnet", {"values": {}}) is False


class TestMapResourceHappyPath:
    def test_happy_path_with_vpc_and_targets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = AWSRouteTableMapper()
        b = FakeBuilder()

        res_name = "aws_route_table.rt[0]"
        res_type = "aws_route_table"

        values = {
            "vpc_id": "vpc-123",
            "region": "eu-west-1",
            "tags": {"Name": "main-rt", "env": "prod"},
            "route": [
                {"cidr_block": "0.0.0.0/0", "gateway_id": "igw-1"},
                {"ipv6_cidr_block": "::/0", "egress_only_gateway_id": "eigw-1"},
            ],
            "propagating_vgws": ["vgw-1"],
        }
        resource_data = {
            "address": "aws_route_table.rt",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "values": values,
        }

        # Unused parsed data removed for brevity

        # Create a fake context that returns the expected reference
        class FakeContext:
            def extract_terraform_references(self, resource_data: dict[str, Any]):
                return [("vpc_id", "aws_vpc.main", "DependsOn")]

            def get_resolved_values(
                self, resource_data: dict[str, Any], context_type: str
            ):
                return resource_data.get("values", {})

        context = FakeContext()
        m.map_resource(res_name, res_type, resource_data, b, context)

        node_key = "aws_route_table_rt_0"
        assert node_key in b.nodes
        node = b.nodes[node_key]

        # Type and properties
        assert node["type"] == "Network"
        assert node["properties"]["network_type"] == "routing"
        # IPv6 route present -> ip_version 6
        assert node["properties"]["ip_version"] == 6
        # Name from tag
        assert node["properties"]["network_name"] == "main-rt"

        # Capability
        assert "link" in node["capabilities"]

        # Metadata basics
        md = node["metadata"]
        assert md["original_resource_type"] == "aws_route_table"
        assert md["original_resource_name"] == "rt[0]"
        assert md["aws_component_type"] == "RouteTable"
        assert "Route Table" in md["description"]
        assert md["aws_provider"].startswith("registry.terraform.io")
        assert md["aws_vpc_id"] == "vpc-123"
        assert md["aws_region"] == "eu-west-1"
        assert md["aws_tags"]["env"] == "prod"
        assert md["aws_name"] == "main-rt"
        assert md["aws_route_count"] == 2
        assert md["aws_propagating_vgws"] == ["vgw-1"]

        # Processed routes in metadata
        routes = md["aws_routes"]
        assert {
            "destination": "0.0.0.0/0",
            "destination_type": "ipv4_cidr",
            "target": "igw-1",
            "target_type": "gateway_id",
        } in routes
        assert {
            "destination": "::/0",
            "destination_type": "ipv6_cidr",
            "target": "eigw-1",
            "target_type": "egress_only_gateway_id",
        } in routes

        # Dependencies: Only VPC (context only returns VPC reference)
        reqs = node["requirements"]
        assert len(reqs) == 1
        # Extract requirement details
        vpc_req = reqs[0]["vpc_id"]
        assert vpc_req["node"] == "aws_vpc_main"
        assert vpc_req["relationship"] == "DependsOn"


class TestEdgeCases:
    def test_no_values_skips(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSRouteTableMapper()
        b = FakeBuilder()
        m.map_resource("aws_route_table.empty", "aws_route_table", {}, b)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_no_context_no_dependencies(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSRouteTableMapper()
        b = FakeBuilder()
        data = {"values": {"vpc_id": "vpc-1"}}
        m.map_resource("aws_route_table.rt", "aws_route_table", data, b)

        node = b.nodes["aws_route_table_rt"]
        assert node["requirements"] == []
        assert any(
            "No context provided to detect dependencies" in r.message
            for r in caplog.records
        )

    def test_no_name_tag_uses_clean_name(self) -> None:
        m = AWSRouteTableMapper()
        b = FakeBuilder()
        data = {"values": {"vpc_id": "vpc-1", "tags": {}}}
        m.map_resource("aws_route_table.foo", "aws_route_table", data, b, None)
        node = b.nodes["aws_route_table_foo"]
        assert node["properties"]["network_name"] == "foo"
        assert node["properties"]["network_type"] == "routing"

    def test_ipv4_only_routes_set_ip_version_4(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = AWSRouteTableMapper()
        b = FakeBuilder()
        res_name = "aws_route_table.onlyv4"
        res_type = "aws_route_table"
        resource_data = {
            "address": "aws_route_table.onlyv4",
            "values": {"route": [{"cidr_block": "10.0.0.0/16", "gateway_id": "igw"}]},
        }

        # Create a fake context that returns no references
        class FakeContext:
            def extract_terraform_references(self, resource_data: dict[str, Any]):
                return []

            def get_resolved_values(
                self, resource_data: dict[str, Any], context_type: str
            ):
                return resource_data.get("values", {})

        context = FakeContext()
        m.map_resource(res_name, res_type, resource_data, b, context)
        node = b.nodes["aws_route_table_onlyv4"]
        assert node["properties"]["ip_version"] == 4
