from __future__ import annotations

from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper
from src.plugins.terraform.mappers.aws.aws_nat_gateway import AWSNATGatewayMapper


class FakeReq:
    def __init__(self, node: FakeNode, name: str) -> None:
        self._node = node
        self._name = name
        self._target: str | None = None
        self._relationship: Any = None  # can be str or dict

    def to_node(self, target: str) -> FakeReq:
        self._target = target
        return self

    def with_relationship(self, rel: Any) -> FakeReq:
        self._relationship = rel
        return self

    def and_node(self) -> FakeNode:
        self._node.requirements.append((self._name, self._target, self._relationship))
        return self._node


class FakeCap:
    def __init__(self, node: FakeNode, name: str) -> None:
        self._node = node
        self.name = name
        self.properties: dict[str, Any] = {}

    def with_property(self, key: str, value: Any) -> FakeCap:
        self.properties[key] = value
        return self

    def and_node(self) -> FakeNode:
        self._node.capabilities[self.name] = dict(self.properties)
        return self._node


class FakeNode:
    def __init__(self, name: str, node_type: str) -> None:
        self.name = name
        self.node_type = node_type
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.capabilities: dict[str, dict[str, Any]] = {}
        self.requirements: list[tuple[str, str | None, Any]] = []

    def with_property(self, key: str, value: Any) -> FakeNode:
        self.properties[key] = value
        return self

    def add_capability(self, name: str) -> FakeCap:
        return FakeCap(self, name)

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


class DummyCtx:
    """
    Minimal context to satisfy mapper calls in tests.

    - get_resolved_values: returns raw values (or could adjust them)
    - generate_tosca_node_name_from_address: delegates to BaseResourceMapper
    - extract_filtered_terraform_references: returns provided refs but with
      targets already resolved to TOSCA node names, as expected by the mapper
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
        # In these tests, just forward the concrete "values"
        return resource_data.get("values", {})

    def generate_tosca_node_name_from_address(
        self, address: str, resource_type: str
    ) -> str:
        return BaseResourceMapper.generate_tosca_node_name(address, resource_type)

    def extract_filtered_terraform_references(
        self,
        resource_data: dict[str, Any],
        _dependency_filter: object,  # provided by mapper; ignore here
    ) -> list[tuple[str, str, str]]:
        # Convert refs like ("subnet_id", "aws_subnet.public1", "DependsOn")
        # into ("subnet_id", "<tosca_node_name>", "DependsOn")
        resolved: list[tuple[str, str, str]] = []
        for prop_name, target_ref, rel in self._refs:
            if "." in target_ref:
                typ = target_ref.split(".", 1)[0]
                resolved.append(
                    (
                        prop_name,
                        BaseResourceMapper.generate_tosca_node_name(target_ref, typ),
                        rel,
                    )
                )
            else:
                resolved.append((prop_name, target_ref, rel))
        return resolved


class TestCanMap:
    def test_true_for_nat(self) -> None:
        m = AWSNATGatewayMapper()
        assert m.can_map("aws_nat_gateway", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSNATGatewayMapper()
        assert m.can_map("aws_eip", {}) is False


class TestValidationGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSNATGatewayMapper()
        b = FakeBuilder()
        m.map_resource("aws_nat_gateway.main", "aws_nat_gateway", {}, b)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)


class TestHappyPathNoContext:
    def test_maps_properties_metadata_and_link_capability(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("DEBUG")
        m = AWSNATGatewayMapper()
        b = FakeBuilder()

        resource_name = "aws_nat_gateway.ngw"
        values = {
            "subnet_id": "subnet-aaa",
            "allocation_id": "eipalloc-123",
            "connectivity_type": "public",
            "public_ip": "198.51.100.10",
            "network_interface_id": "eni-111",
            "tags": {"Name": "edge-nat"},
            "id": "ngw-xyz",
        }
        resource = {
            "values": values,
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }

        m.map_resource(resource_name, "aws_nat_gateway", resource, b)

        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, "aws_nat_gateway"
        )
        assert node_name in b.nodes
        node = b.nodes[node_name]

        # Node basics
        assert node.node_type == "Network"
        assert node.properties["network_type"] == "public"
        assert node.properties["ip_version"] == 4
        assert node.properties["network_name"] == "NATGW-edge-nat"
        # link capability
        assert "link" in node.capabilities

        # Metadata
        md = node.metadata
        assert md["original_resource_type"] == "aws_nat_gateway"
        assert md["original_resource_name"] == "ngw"
        assert md["aws_component_type"] == "NATGateway"
        assert md["aws_connectivity_type"] == "public"
        assert md["aws_subnet_id"] == "subnet-aaa"
        assert md["aws_allocation_id"] == "eipalloc-123"
        assert md["aws_public_ip"] == "198.51.100.10"
        assert md["aws_network_interface_id"] == "eni-111"
        assert md["aws_id"] == "ngw-xyz"
        assert md["aws_tags"] == {"Name": "edge-nat"}

        # No dependencies without context; warning emitted
        assert any(
            "No context provided to detect dependencies" in r.message
            for r in caplog.records
        )


class TestHappyPathWithContext:
    def test_uses_context_for_node_name_and_dependencies(self) -> None:
        m = AWSNATGatewayMapper()
        b = FakeBuilder()

        resource_name = "aws_nat_gateway.main"
        values = {
            "subnet_id": "subnet-123",
            "allocation_id": "eipalloc-abc",
            "connectivity_type": "private",
            "tags": {"role": "egress"},
        }
        resource = {"values": values}

        # Two deps: subnet + eip
        refs = [
            ("subnet_id", "aws_subnet.public1", "DependsOn"),
            ("allocation_id", "aws_eip.nat_eip", "DependsOn"),
        ]
        ctx = DummyCtx(refs=refs, parsed_data={})

        m.map_resource(resource_name, "aws_nat_gateway", resource, b, context=ctx)

        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, "aws_nat_gateway"
        )  # same as context impl
        node = b.nodes[node_name]

        # Properties reflect private connectivity
        assert node.properties["network_type"] == "private"
        assert node.properties["ip_version"] == 4
        assert node.properties["network_name"] == "NATGW-main"  # no Name tag, fallback

        # Requirements added with prop-named edges and resolved targets
        targets = {t for (_, t, _) in node.requirements}
        assert (
            BaseResourceMapper.generate_tosca_node_name(
                "aws_subnet.public1", "aws_subnet"
            )
            in targets
        )
        assert (
            BaseResourceMapper.generate_tosca_node_name("aws_eip.nat_eip", "aws_eip")
            in targets
        )

    def test_name_tag_changes_network_name(self) -> None:
        m = AWSNATGatewayMapper()
        b = FakeBuilder()

        resource_name = "aws_nat_gateway.edge"
        resource = {"values": {"tags": {"Name": "prod-egress"}}}
        m.map_resource(resource_name, "aws_nat_gateway", resource, b)

        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, "aws_nat_gateway"
        )
        assert b.nodes[node_name].properties["network_name"] == "NATGW-prod-egress"
