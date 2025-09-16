from __future__ import annotations

from typing import Any

import pytest

from src.plugins.provisioning.terraform.mappers.aws.aws_eip import AWSEIPMapper


class FakeCap:
    def __init__(self, node: FakeNode, name: str) -> None:
        self.node = node
        self.name = name
        self.properties: dict[str, Any] = {}

    def with_property(self, k: str, v: Any) -> FakeCap:
        self.properties[k] = v
        self.node.capabilities[self.name] = self.properties
        return self

    def and_node(self) -> FakeNode:
        return self.node


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
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.capabilities: dict[str, dict[str, Any]] = {}
        self.requirements: list[tuple[str, str | None, Any]] = []
        self._data = {"metadata": self.metadata}  # used in some mappers

    def with_property(self, k: str, v: Any) -> FakeNode:
        self.properties[k] = v
        return self

    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self.metadata = md
        self._data["metadata"] = md
        return self

    def add_capability(self, name: str) -> FakeCap:
        if name not in self.capabilities:
            self.capabilities[name] = {}
        return FakeCap(self, name)

    def add_requirement(self, name: str) -> FakeReq:
        return FakeReq(self, name)


class FakeBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, FakeNode] = {}

    def add_node(self, name: str, node_type: str) -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node

    # Optional helper if mapper searches for nodes later (not needed here)
    def get_node(self, name: str) -> FakeNode:
        return self.nodes[name]


class FakeContext:
    """
    Minimal TerraformMappingContext stand-in used by AWSEIPMapper:
    - get_resolved_values(resource_data, "property"|"metadata")
    - extract_filtered_terraform_references(resource_data, dependency_filter)
    - generate_tosca_node_name_from_address(resource_name, resource_type)
    """

    def __init__(
        self,
        property_values: dict[str, Any] | None = None,
        metadata_values: dict[str, Any] | None = None,
        filtered_refs: list[tuple[str, str, str]] | None = None,
        generated_name: str | None = None,
    ) -> None:
        self._property_values = property_values or {}
        self._metadata_values = metadata_values or {}
        self._filtered_refs = filtered_refs or []
        self._generated_name = generated_name or "aws_eip_generated_0"

    def get_resolved_values(
        self, _resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        return self._property_values if kind == "property" else self._metadata_values

    def extract_filtered_terraform_references(
        self, _resource_data: dict[str, Any], _filter: Any
    ):
        # mapper treats target_ref already as a TOSCA node name
        return list(self._filtered_refs)

    def generate_tosca_node_name_from_address(self, _name: str, _rtype: str) -> str:
        return self._generated_name


class TestCanMap:
    def test_true_for_eip(self) -> None:
        m = AWSEIPMapper()
        assert m.can_map("aws_eip", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSEIPMapper()
        assert m.can_map("aws_instance", {}) is False


class TestGuards:
    def test_skips_when_no_values_without_context(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSEIPMapper()
        b = FakeBuilder()
        m.map_resource("aws_eip.myip", "aws_eip", {}, b, context=None)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_skips_when_context_returns_empty_values(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSEIPMapper()
        b = FakeBuilder()
        ctx = FakeContext(property_values={}, metadata_values={})
        # avoid real import usage of DependencyFilter by stubbing it on the module
        import src.plugins.provisioning.terraform.context as ctxmod

        monkeypatch.setattr(ctxmod, "DependencyFilter", object, raising=False)
        m.map_resource("aws_eip.myip", "aws_eip", {"values": {}}, b, context=ctx)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)


class TestHappyPathNoContext:
    def test_maps_properties_and_metadata(self) -> None:
        m = AWSEIPMapper()
        b = FakeBuilder()

        values = {
            "domain": "vpc",
            "vpc": True,
            "instance": "i-123",
            "network_interface": "eni-999",
            "associate_with_private_ip": "10.0.1.10",
            "customer_owned_ipv4_pool": None,
            "allocation_id": "eipalloc-abc",
            "public_ip": "54.12.34.56",
            "private_ip": "10.0.1.10",
            "public_dns": "ec2-54-12-34-56.compute-1.amazonaws.com",
            "private_dns": "ip-10-0-1-10.ec2.internal",
            "address": "54.12.34.56",
            "id": "eip-123",
            "tags": {"Name": "nat-gw-eip", "env": "dev"},
            "tags_all": {"Name": "nat-gw-eip", "env": "dev", "owner": "team"},
        }
        resource = {
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "values": values,
        }

        m.map_resource("aws_eip.nat_gateway", "aws_eip", resource, b, context=None)

        node = b.nodes["aws_eip_nat_gateway"]
        # type
        assert node.node_type == "Network"
        # properties
        assert node.properties["network_type"] == "public"
        assert node.properties["ip_version"] == 4
        assert node.properties["network_name"] == "EIP-nat-gw-eip"
        # capabilities
        assert "link" in node.capabilities
        # metadata
        md = node.metadata
        assert md["original_resource_type"] == "aws_eip"
        assert md["original_resource_name"] == "nat_gateway"
        assert md["aws_component_type"] == "ElasticIP"
        assert md["aws_provider"].endswith("/aws")
        assert md["aws_domain"] == "vpc"
        assert md["aws_vpc"] is True
        assert md["aws_instance"] == "i-123"
        assert md["aws_network_interface"] == "eni-999"
        assert md["aws_associate_with_private_ip"] == "10.0.1.10"
        assert md["aws_allocation_id"] == "eipalloc-abc"
        assert md["aws_public_ip"] == "54.12.34.56"
        assert md["aws_private_ip"] == "10.0.1.10"
        assert md["aws_public_dns"].startswith("ec2-")
        assert md["aws_private_dns"].startswith("ip-")
        assert md["aws_address"] == "54.12.34.56"
        assert md["aws_id"] == "eip-123"
        assert md["aws_tags"]["env"] == "dev"
        assert md["aws_tags_all"]["owner"] == "team"


class TestHappyPathWithContext:
    def test_uses_context_for_node_name_properties_metadata_and_dependencies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = AWSEIPMapper()
        b = FakeBuilder()

        # property values drive TOSCA properties (availability etc. not relevant here)
        prop_vals = {
            "domain": "vpc",
            "vpc": True,
            "tags": {"Name": "bastion-eip"},
        }
        # metadata values are concrete for metadata fields
        meta_vals = {
            "domain": "vpc",
            "vpc": True,
            "allocation_id": "eipalloc-xyz",
            "public_ip": "3.4.5.6",
            "id": "eip-xyz",
            "tags": {"Name": "bastion-eip", "team": "secops"},
            "tags_all": {"Name": "bastion-eip", "team": "secops"},
        }
        # dependencies already resolved to TOSCA node names by context
        filtered_refs = [
            ("instance", "aws_instance_web", "DependsOn"),
            ("network_interface", "aws_network_interface_eth0", "DependsOn"),
        ]

        ctx = FakeContext(
            property_values=prop_vals,
            metadata_values=meta_vals,
            filtered_refs=filtered_refs,
            generated_name="aws_eip_bastion_0",
        )

        # the mapper imports DependencyFilter at runtime; stub it so import works
        import src.plugins.provisioning.terraform.context as ctxmod

        class DummyDF:
            def __init__(
                self,
                exclude_target_types=None,
                exclude_properties=None,
                custom_filter=None,
                synthetic_dependencies=None,
            ):
                self.exclude_target_types = exclude_target_types
                self.exclude_properties = exclude_properties
                self.custom_filter = custom_filter
                self.synthetic_dependencies = synthetic_dependencies

        monkeypatch.setattr(ctxmod, "DependencyFilter", DummyDF, raising=False)

        resource = {
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "values": {"ignored": True},  # mapper will use context values
        }

        m.map_resource("aws_eip.bastion", "aws_eip", resource, b, context=ctx)

        # node name should come from context.generate_tosca_node_name_from_address
        assert "aws_eip_bastion_0" in b.nodes
        node = b.nodes["aws_eip_bastion_0"]

        # properties
        assert node.properties["network_type"] == "public"
        assert node.properties["ip_version"] == 4
        assert node.properties["network_name"] == "EIP-bastion-eip"

        # metadata relies on meta_vals
        md = node.metadata
        assert md["aws_allocation_id"] == "eipalloc-xyz"
        assert md["aws_public_ip"] == "3.4.5.6"
        assert md["aws_id"] == "eip-xyz"
        assert md["aws_tags"]["team"] == "secops"

        # dependencies from filtered_refs
        reqs = set(node.requirements)
        assert ("instance", "aws_instance_web", "DependsOn") in reqs
        assert ("network_interface", "aws_network_interface_eth0", "DependsOn") in reqs

    def test_without_name_tag_network_name_falls_back_to_clean_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = AWSEIPMapper()
        b = FakeBuilder()

        ctx = FakeContext(
            property_values={"vpc": True, "tags": {}},
            metadata_values={"vpc": True},
            filtered_refs=[],
            generated_name="aws_eip_nat_0",
        )
        import src.plugins.provisioning.terraform.context as ctxmod

        class DummyDF:
            def __init__(
                self,
                exclude_target_types=None,
                exclude_properties=None,
                custom_filter=None,
                synthetic_dependencies=None,
            ):
                self.exclude_target_types = exclude_target_types
                self.exclude_properties = exclude_properties
                self.custom_filter = custom_filter
                self.synthetic_dependencies = synthetic_dependencies

        monkeypatch.setattr(ctxmod, "DependencyFilter", DummyDF, raising=False)

        m.map_resource("aws_eip.nat", "aws_eip", {"values": {}}, b, context=ctx)
        node = b.nodes["aws_eip_nat_0"]
        assert node.properties["network_name"] == "EIP-nat"
