from __future__ import annotations

from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper
from src.plugins.terraform.mappers.aws.aws_route_table_association import (
    AWSRouteTableAssociationMapper,
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
    def __init__(self, name: str, node_type: str = "Root") -> None:
        self.name = name
        self.node_type = node_type
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.requirements: list[tuple[str, str | None, str | None]] = []

    def add_requirement(self, name: str) -> FakeReq:
        return FakeReq(self, name)

    # Helpers used in other mappers; harmless to include here
    def with_property(self, k: str, v: Any) -> FakeNode:
        self.properties[k] = v
        return self

    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self.metadata = md
        return self


class FakeBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, FakeNode] = {}

    def add_node(self, name: str, node_type: str = "Root") -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node

    def get_node(self, name: str) -> FakeNode:
        if name not in self.nodes:
            raise KeyError(name)
        return self.nodes[name]


class DummyCtx:
    """Minimal context for testing reference extraction and TOSCA naming."""

    def __init__(
        self,
        refs: list[tuple[str, str, str]] | None = None,
        parsed_data: dict | None = None,
    ) -> None:
        self._refs = refs or []
        self.parsed_data = parsed_data or {}

    def get_resolved_values(
        self, resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        # We simply return the values; the mapper does the rest.
        return resource_data.get("values", {})

    def extract_terraform_references(
        self, resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        return list(self._refs)

    def generate_tosca_node_name_from_address(
        self, address: str, resource_type: str
    ) -> str:
        # Reuse the same logic from BaseResourceMapper for consistency
        return BaseResourceMapper.generate_tosca_node_name(address, resource_type)


class TestCanMap:
    def test_true_for_assoc(self) -> None:
        m = AWSRouteTableAssociationMapper()
        assert m.can_map("aws_route_table_association", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSRouteTableAssociationMapper()
        assert m.can_map("aws_route_table", {}) is False


class TestGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteTableAssociationMapper()
        b = FakeBuilder()
        m.map_resource(
            "aws_route_table_association.a",
            "aws_route_table_association",
            {},
            b,
            context=None,
        )
        assert not b.nodes  # no changes
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_skips_when_no_context(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteTableAssociationMapper()
        b = FakeBuilder()
        resource = {"values": {"subnet_id": "subnet-123", "route_table_id": "rtb-456"}}
        m.map_resource(
            "aws_route_table_association.a",
            "aws_route_table_association",
            resource,
            b,
            context=None,
        )
        assert any(
            "No context provided to resolve references" in r.message
            for r in caplog.records
        )


class TestHappyPathWithRefs:
    def test_subnet_association_via_refs(self) -> None:
        m = AWSRouteTableAssociationMapper()
        b = FakeBuilder()

        # Terraform references from context (plan)
        refs = [
            ("subnet_id", "aws_subnet.public", "DependsOn"),
            ("route_table_id", "aws_route_table.public", "DependsOn"),
        ]
        ctx = DummyCtx(refs=refs)

        # Pre-create the nodes that the mapper should modify
        subnet_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_subnet.public", "aws_subnet"
        )
        rtb_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route_table.public", "aws_route_table"
        )
        b.add_node(subnet_node_name, "Network")
        b.add_node(rtb_node_name, "Network")

        resource = {"values": {"subnet_id": "ignored", "route_table_id": "ignored"}}

        m.map_resource(
            "aws_route_table_association.subnet",
            "aws_route_table_association",
            resource,
            b,
            context=ctx,
        )

        subnet_node = b.get_node(subnet_node_name)
        # Should have added a dependency requirement to the route table
        assert ("dependency", rtb_node_name, "DependsOn") in subnet_node.requirements

    def test_gateway_association_via_refs(self) -> None:
        m = AWSRouteTableAssociationMapper()
        b = FakeBuilder()

        refs = [
            ("gateway_id", "aws_internet_gateway.igw", "DependsOn"),
            ("route_table_id", "aws_route_table.public", "DependsOn"),
        ]
        ctx = DummyCtx(refs=refs)

        igw_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_internet_gateway.igw", "aws_internet_gateway"
        )
        rtb_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route_table.public", "aws_route_table"
        )
        b.add_node(igw_node_name, "Network")
        b.add_node(rtb_node_name, "Network")

        resource = {"values": {"gateway_id": "ignored", "route_table_id": "ignored"}}

        m.map_resource(
            "aws_route_table_association.igw",
            "aws_route_table_association",
            resource,
            b,
            context=ctx,
        )

        igw_node = b.get_node(igw_node_name)
        assert ("dependency", rtb_node_name, "DependsOn") in igw_node.requirements


class TestFallbackFromStateValues:
    def test_fallback_maps_by_ids_when_no_refs(self) -> None:
        m = AWSRouteTableAssociationMapper()
        # Context with state containing resources and their IDs
        parsed_state = {
            "state": {
                "values": {
                    "root_module": {
                        "resources": [
                            {
                                "address": "aws_subnet.public",
                                "type": "aws_subnet",
                                "values": {"id": "subnet-123"},
                            },
                            {
                                "address": "aws_route_table.public",
                                "type": "aws_route_table",
                                "values": {"id": "rtb-456"},
                            },
                        ]
                    }
                }
            }
        }
        ctx = DummyCtx(refs=[], parsed_data=parsed_state)

        b = FakeBuilder()
        subnet_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_subnet.public", "aws_subnet"
        )
        rtb_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route_table.public", "aws_route_table"
        )
        b.add_node(subnet_node_name, "Network")
        b.add_node(rtb_node_name, "Network")

        # No refs in plan; only state values with concrete IDs
        resource = {"values": {"subnet_id": "subnet-123", "route_table_id": "rtb-456"}}

        m.map_resource(
            "aws_route_table_association.from_state",
            "aws_route_table_association",
            resource,
            b,
            context=ctx,
        )

        subnet_node = b.get_node(subnet_node_name)
        assert ("dependency", rtb_node_name, "DependsOn") in subnet_node.requirements


class TestValidationFailures:
    def test_missing_route_table_skips(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteTableAssociationMapper()
        b = FakeBuilder()

        refs = [("subnet_id", "aws_subnet.public", "DependsOn")]
        ctx = DummyCtx(refs=refs)

        subnet_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_subnet.public", "aws_subnet"
        )
        b.add_node(subnet_node_name, "Network")

        # Provide values that pass initial check but have no route table ref
        resource = {"values": {"subnet_id": "subnet-123"}}

        m.map_resource(
            "aws_route_table_association.bad",
            "aws_route_table_association",
            resource,
            b,
            context=ctx,
        )

        assert any(
            "Could not resolve route table reference" in r.message
            for r in caplog.records
        )

    def test_missing_subnet_and_gateway_skips(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteTableAssociationMapper()
        b = FakeBuilder()

        refs = [("route_table_id", "aws_route_table.public", "DependsOn")]
        ctx = DummyCtx(refs=refs)

        rtb_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route_table.public", "aws_route_table"
        )
        b.add_node(rtb_node_name, "Network")

        # Provide values that pass initial check but have no subnet/gateway ref
        resource = {"values": {"route_table_id": "rtb-456"}}

        m.map_resource(
            "aws_route_table_association.bad2",
            "aws_route_table_association",
            resource,
            b,
            context=ctx,
        )

        assert any(
            "Could not resolve subnet or gateway reference" in r.message
            for r in caplog.records
        )
