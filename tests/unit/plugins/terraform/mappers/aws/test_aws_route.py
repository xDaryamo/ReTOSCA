from __future__ import annotations

from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper
from src.plugins.terraform.mappers.aws.aws_route import AWSRouteMapper


class FakeReq:
    def __init__(self, node: FakeNode, name: str) -> None:
        self._node = node
        self._name = name
        self._target: str | None = None
        self._relationship: Any = None

    def to_node(self, target: str) -> FakeReq:
        self._target = target
        return self

    def with_relationship(self, rel: Any) -> FakeReq:
        self._relationship = rel
        return self

    def and_node(self) -> FakeNode:
        self._node.requirements.append((self._name, self._target, self._relationship))
        return self._node


class FakeNode:
    def __init__(self, name: str, node_type: str = "Network") -> None:
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

    def get_node(self, name: str) -> FakeNode:
        if name not in self.nodes:
            raise KeyError(name)
        return self.nodes[name]


class DummyCtx:
    """
    - get_resolved_values: returns the raw values
    - generate_tosca_node_name_from_address: delegates to BaseResourceMapper
    - extract_terraform_references: returns the list of fake references
    - parsed_data: used by the fallback on state/planned_values
    """

    def __init__(
        self,
        refs: list[tuple[str, str, str]] | None = None,
        parsed_data: dict[str, Any] | None = None,
    ) -> None:
        self._refs = refs or []
        self.parsed_data = parsed_data or {}

    def get_resolved_values(
        self, resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        return resource_data.get("values", {})

    def generate_tosca_node_name_from_address(
        self, address: str, resource_type: str
    ) -> str:
        return BaseResourceMapper.generate_tosca_node_name(address, resource_type)

    def extract_terraform_references(
        self, resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        return list(self._refs)


class TestCanMap:
    def test_true_for_route(self) -> None:
        m = AWSRouteMapper()
        assert m.can_map("aws_route", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSRouteMapper()
        assert m.can_map("aws_route_table", {}) is False


class TestValidationGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteMapper()
        b = FakeBuilder()
        # Precarica un route table node per vedere che non viene toccato
        rt_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route_table.public", "aws_route_table"
        )
        b.add_node(rt_name, "Network")

        m.map_resource("aws_route.default", "aws_route", {}, b, context=DummyCtx())

        assert len(b.get_node(rt_name).requirements) == 0
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_skips_when_no_destination_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteMapper()
        b = FakeBuilder()

        # route table e target esistono
        rt_addr = "aws_route_table.public"
        gw_addr = "aws_internet_gateway.gw"
        rt_node_name = BaseResourceMapper.generate_tosca_node_name(
            rt_addr, "aws_route_table"
        )
        gw_node_name = BaseResourceMapper.generate_tosca_node_name(
            gw_addr, "aws_internet_gateway"
        )
        b.add_node(rt_node_name, "Network")
        b.add_node(gw_node_name, "Network")

        # riferimenti presenti ma nessuna destination_* nel values
        refs = [
            ("route_table_id", rt_addr, "DependsOn"),
            ("gateway_id", gw_addr, "DependsOn"),
        ]
        # Values non vuoti ma senza destination info
        resource = {"values": {"some_other_field": "value"}}
        m.map_resource(
            "aws_route.r", "aws_route", resource, b, context=DummyCtx(refs=refs)
        )

        assert len(b.get_node(rt_node_name).requirements) == 0
        assert any(
            "Could not extract valid destination information" in r.message
            for r in caplog.records
        )

    def test_skips_without_context(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteMapper()
        b = FakeBuilder()

        # Anche se i values hanno tutto, senza context non si risolvono i nodi
        resource = {
            "values": {
                "destination_cidr_block": "0.0.0.0/0",
                "gateway_id": "igw-abc",
                "route_table_id": "rtb-123",
            }
        }
        m.map_resource("aws_route.noctx", "aws_route", resource, b, context=None)

        assert any(
            "No context provided to resolve references" in r.message
            for r in caplog.records
        )


class TestHappyPathByReferences:
    def test_adds_dependency_links_via_references(self) -> None:
        m = AWSRouteMapper()
        b = FakeBuilder()

        # Prepara nodi esistenti
        rt_addr = "aws_route_table.public"
        gw_addr = "aws_internet_gateway.gw"
        rt_node_name = BaseResourceMapper.generate_tosca_node_name(
            rt_addr, "aws_route_table"
        )
        gw_node_name = BaseResourceMapper.generate_tosca_node_name(
            gw_addr, "aws_internet_gateway"
        )
        b.add_node(rt_node_name, "Network")
        b.add_node(gw_node_name, "Network")

        # Values con destination
        resource = {
            "values": {
                "destination_cidr_block": "0.0.0.0/0",
            }
        }
        refs = [
            ("route_table_id", rt_addr, "DependsOn"),
            ("gateway_id", gw_addr, "DependsOn"),
        ]
        ctx = DummyCtx(refs=refs)

        m.map_resource("aws_route.default", "aws_route", resource, b, context=ctx)

        reqs = b.get_node(rt_node_name).requirements
        assert ("dependency", gw_node_name, "LinksTo") in reqs


class TestFallbackFromState:
    def test_uses_state_ids_when_no_references(self) -> None:
        m = AWSRouteMapper()
        b = FakeBuilder()

        # State con IDs concreti
        parsed_state = {
            "state": {
                "values": {
                    "root_module": {
                        "resources": [
                            {
                                "address": "aws_route_table.public",
                                "type": "aws_route_table",
                                "values": {"id": "rtb-123"},
                            },
                            {
                                "address": "aws_internet_gateway.gw",
                                "type": "aws_internet_gateway",
                                "values": {"id": "igw-abc"},
                            },
                        ]
                    }
                }
            }
        }
        ctx = DummyCtx(refs=[], parsed_data=parsed_state)

        # Prepara nodi calcolando i nomi attesi
        rt_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route_table.public", "aws_route_table"
        )
        gw_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_internet_gateway.gw", "aws_internet_gateway"
        )
        b.add_node(rt_node_name, "Network")
        b.add_node(gw_node_name, "Network")

        resource = {
            "values": {
                "destination_cidr_block": "0.0.0.0/0",
                "gateway_id": "igw-abc",
                "route_table_id": "rtb-123",
            }
        }

        m.map_resource("aws_route.via_state", "aws_route", resource, b, context=ctx)

        reqs = b.get_node(rt_node_name).requirements
        assert ("dependency", gw_node_name, "LinksTo") in reqs


class TestMissingNodes:
    def test_missing_route_table_node_skips(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteMapper()
        b = FakeBuilder()

        gw_addr = "aws_internet_gateway.gw"
        gw_node_name = BaseResourceMapper.generate_tosca_node_name(
            gw_addr, "aws_internet_gateway"
        )
        b.add_node(gw_node_name, "Network")

        refs = [
            ("route_table_id", "aws_route_table.rtb", "DependsOn"),
            ("gateway_id", gw_addr, "DependsOn"),
        ]
        resource = {"values": {"destination_cidr_block": "0.0.0.0/0"}}

        m.map_resource(
            "aws_route.miss_rt", "aws_route", resource, b, context=DummyCtx(refs=refs)
        )

        assert any(
            "Route table node" in r.message and "not found" in r.message
            for r in caplog.records
        )

    def test_missing_target_node_skips(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSRouteMapper()
        b = FakeBuilder()

        rt_addr = "aws_route_table.public"
        rt_node_name = BaseResourceMapper.generate_tosca_node_name(
            rt_addr, "aws_route_table"
        )
        b.add_node(rt_node_name, "Network")

        refs = [
            ("route_table_id", rt_addr, "DependsOn"),
            ("gateway_id", "aws_internet_gateway.gw", "DependsOn"),
        ]
        resource = {"values": {"destination_cidr_block": "0.0.0.0/0"}}

        m.map_resource(
            "aws_route.miss_target",
            "aws_route",
            resource,
            b,
            context=DummyCtx(refs=refs),
        )

        assert any(
            "Target node" in r.message and "not found" in r.message
            for r in caplog.records
        )


class TestIPv6:
    def test_ipv6_destination_uses_linksto(self) -> None:
        m = AWSRouteMapper()
        b = FakeBuilder()

        rt_addr = "aws_route_table.v6"
        gw_addr = "aws_egress_only_internet_gateway.eigw"
        rt_node_name = BaseResourceMapper.generate_tosca_node_name(
            rt_addr, "aws_route_table"
        )
        gw_node_name = BaseResourceMapper.generate_tosca_node_name(
            gw_addr, "aws_egress_only_internet_gateway"
        )
        b.add_node(rt_node_name, "Network")
        b.add_node(gw_node_name, "Network")

        resource = {"values": {"destination_ipv6_cidr_block": "::/0"}}
        refs = [
            ("route_table_id", rt_addr, "DependsOn"),
            ("egress_only_gateway_id", gw_addr, "DependsOn"),
        ]
        ctx = DummyCtx(refs=refs)

        m.map_resource("aws_route.v6", "aws_route", resource, b, context=ctx)

        reqs = b.get_node(rt_node_name).requirements
        assert ("dependency", gw_node_name, "LinksTo") in reqs
