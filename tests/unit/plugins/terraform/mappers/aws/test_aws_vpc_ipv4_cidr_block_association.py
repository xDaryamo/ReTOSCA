from __future__ import annotations

from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper
from src.plugins.provisioning.terraform.mappers.aws.aws_vpc_ipv4_cidr_block_association import (  # noqa: E501
    AWSVPCIpv4CidrBlockAssociationMapper,
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


class FakeCap:
    def __init__(self, node: FakeNode, name: str) -> None:
        self.node = node
        self.name = name
        self.props: dict[str, Any] = {}

    def with_property(self, k: str, v: Any) -> FakeCap:
        self.props[k] = v
        return self

    def and_node(self) -> FakeNode:
        self.node.capabilities[self.name] = dict(self.props)
        return self.node


class FakeNode:
    def __init__(self, name: str, node_type: str = "Root") -> None:
        self.name = name
        self.node_type = node_type
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.capabilities: dict[str, dict[str, Any]] = {}
        self.requirements: list[tuple[str, str | None, str | None]] = []

    def with_property(self, k: str, v: Any) -> FakeNode:
        self.properties[k] = v
        return self

    def with_properties(self, d: dict[str, Any]) -> FakeNode:
        self.properties.update(d)
        return self

    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self.metadata = md
        return self

    def add_requirement(self, name: str) -> FakeReq:
        return FakeReq(self, name)

    def add_capability(self, name: str) -> FakeCap:
        return FakeCap(self, name)


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
    """
    Minimal context.
    - `refs`: list of tuples (prop_name, target_ref, relationship_type).
      In this mapper we assume that `target_ref` is already a *TOSCA node name*.
    - `parsed_data`: structure with state/planned_values for fallback by-id.
    - `name_override`: if passed, forces the generated TOSCA name for the current node.
    """

    def __init__(
        self,
        refs: list[tuple[str, str, str]] | None = None,
        parsed_data: dict | None = None,
        name_override: str | None = None,
    ) -> None:
        self._refs = refs or []
        self.parsed_data = parsed_data or {}
        self._name_override = name_override

    def get_resolved_values(
        self, resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        return resource_data.get("values", {})

    def extract_terraform_references(
        self, resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        return list(self._refs)

    def generate_tosca_node_name_from_address(
        self, address: str, resource_type: str
    ) -> str:
        if self._name_override:
            return self._name_override
        return BaseResourceMapper.generate_tosca_node_name(address, resource_type)


class TestCanMap:
    def test_true_for_assoc(self) -> None:
        m = AWSVPCIpv4CidrBlockAssociationMapper()
        assert m.can_map("aws_vpc_ipv4_cidr_block_association", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSVPCIpv4CidrBlockAssociationMapper()
        assert m.can_map("aws_vpc", {}) is False


class TestNoContext:
    def test_builds_node_and_warns_without_context(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSVPCIpv4CidrBlockAssociationMapper()
        b = FakeBuilder()

        resource = {
            "values": {
                "cidr_block": "10.1.0.0/16",
                "vpc_id": "vpc-abc123",
            }
        }

        m.map_resource(
            "aws_vpc_ipv4_cidr_block_association.extra",
            "aws_vpc_ipv4_cidr_block_association",
            resource,
            b,
            context=None,
        )

        # Generated name without context
        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_vpc_ipv4_cidr_block_association.extra",
            "aws_vpc_ipv4_cidr_block_association",
        )
        node = b.get_node(node_name)

        # Main properties
        assert node.properties["cidr"] == "10.1.0.0/16"
        assert node.properties["network_type"] == "additional_cidr"
        assert node.properties["ip_version"] == 4
        assert node.properties["dhcp_enabled"] is True
        # network_name derived from CIDR
        assert node.properties["network_name"] == "additional_cidr_10_1_0_0_16"

        # Capability 'link' added
        assert "link" in node.capabilities

        # Warning about missing context for dependencies
        assert any(
            "No context provided to detect dependencies" in r.message
            for r in caplog.records
        )


class TestWithContextAndRefs:
    def test_uses_context_name_override_and_adds_dependency_from_refs(self) -> None:
        m = AWSVPCIpv4CidrBlockAssociationMapper()
        b = FakeBuilder()

        # Prepare a custom TOSCA name via context
        ctx = DummyCtx(
            refs=[
                # The target_ref here is already a ready TOSCA node name
                ("vpc_id", "aws_vpc_main_node", "DependsOn"),
            ],
            name_override="custom_cidr_node",
        )

        resource = {"values": {"cidr_block": "10.0.2.0/24", "vpc_id": "vpc-xyz"}}

        m.map_resource(
            "aws_vpc_ipv4_cidr_block_association.foo",
            "aws_vpc_ipv4_cidr_block_association",
            resource,
            b,
            context=ctx,
        )

        # The node must be named as decided by the context
        node = b.get_node("custom_cidr_node")
        # Must have the requirement based on refs
        assert ("vpc_id", "aws_vpc_main_node", "DependsOn") in node.requirements


class TestFallbackByIds:
    def test_adds_vpc_dependency_when_no_refs_but_vpc_id_present(self) -> None:
        m = AWSVPCIpv4CidrBlockAssociationMapper()
        b = FakeBuilder()

        # State with a VPC present (id -> address) for fallback resolution
        parsed_state = {
            "state": {
                "values": {
                    "root_module": {
                        "resources": [
                            {
                                "address": "aws_vpc.main",
                                "type": "aws_vpc",
                                "values": {"id": "vpc-12345"},
                            }
                        ]
                    }
                }
            }
        }
        ctx = DummyCtx(parsed_data=parsed_state)

        resource = {"values": {"cidr_block": "10.2.0.0/16", "vpc_id": "vpc-12345"}}

        m.map_resource(
            "aws_vpc_ipv4_cidr_block_association.bar",
            "aws_vpc_ipv4_cidr_block_association",
            resource,
            b,
            context=ctx,
        )

        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_vpc_ipv4_cidr_block_association.bar",
            "aws_vpc_ipv4_cidr_block_association",
        )
        node = b.get_node(node_name)

        vpc_node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_vpc.main", "aws_vpc"
        )
        # In fallback, the requirement is called 'vpc_dependency'
        assert ("vpc_dependency", vpc_node_name, "DependsOn") in node.requirements


class TestGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSVPCIpv4CidrBlockAssociationMapper()
        b = FakeBuilder()
        m.map_resource(
            "aws_vpc_ipv4_cidr_block_association.x",
            "aws_vpc_ipv4_cidr_block_association",
            {},
            b,
            context=None,
        )
        assert any("has no 'values' section" in r.message for r in caplog.records)
