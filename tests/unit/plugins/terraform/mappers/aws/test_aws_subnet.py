from __future__ import annotations

import logging
from typing import Any

import pytest

from src.plugins.terraform.mappers.aws.aws_subnet import AWSSubnetMapper


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
        self._req = {}

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
    def test_can_map_true_for_subnet(self) -> None:
        m = AWSSubnetMapper()
        assert m.can_map("aws_subnet", {"values": {}}) is True

    def test_can_map_false_for_other(self) -> None:
        m = AWSSubnetMapper()
        assert m.can_map("aws_instance", {"values": {}}) is False


class TestMapResource:
    def test_map_happy_path_and_dependency(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = AWSSubnetMapper()
        b = FakeBuilder()
        res_name = "aws_subnet.subnet-1[0]"
        res_type = "aws_subnet"
        data = {
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "values": {
                "cidr_block": "10.0.1.0/24",
                "availability_zone": "eu-west-1a",
                "ipv6_cidr_block": "2a05:d018:abcd::/64",
                "map_public_ip_on_launch": True,
                "vpc_id": "vpc-123",
                "tags": {"Name": "backend-subnet", "env": "prod"},
                "customer_owned_ipv4_pool": "pool-1",
                "map_customer_owned_ip_on_launch": False,
                "outpost_arn": "arn:aws:outposts:...:op-xyz",
            },
        }

        # Create a fake context that returns the expected reference
        class FakeContext:
            def extract_terraform_references(self, resource_data: dict[str, Any]):
                return [("vpc_id", "aws_vpc.main", "tosca.relationships.DependsOn")]

            def get_resolved_values(
                self, resource_data: dict[str, Any], context: str = "property"
            ):
                # Return the original values for testing
                return resource_data.get("values", {})

        context = FakeContext()
        m.map_resource(res_name, res_type, data, b, context)

        # Node name must be normalized by BaseResourceMapper
        node_name = "aws_subnet_subnet_1_0"
        assert node_name in b.nodes
        node = b.nodes[node_name]

        # Type and properties
        assert node["type"] == "Network"
        assert node["properties"]["cidr"] == "10.0.1.0/24"
        # 'Name' tag overrides default AZ-based network_name
        assert node["properties"]["network_name"] == "backend-subnet"

        # Metadata
        md = node["metadata"]
        assert md["original_resource_type"] == "aws_subnet"
        assert md["original_resource_name"] == "subnet-1[0]"
        assert md["aws_provider"].startswith("registry.terraform.io")
        assert md["aws_availability_zone"] == "eu-west-1a"
        assert md["aws_ipv6_cidr_block"] == "2a05:d018:abcd::/64"
        assert md["aws_map_public_ip_on_launch"] is True
        assert md["aws_vpc_id"] == "vpc-123"
        assert md["aws_tags"]["env"] == "prod"
        assert md["aws_customer_owned_ipv4_pool"] == "pool-1"
        assert md["aws_map_customer_owned_ip_on_launch"] is False
        assert md["aws_outpost_arn"].startswith("arn:aws:outposts")

        # Capability 'link' added
        assert "link" in node["capabilities"]

        # One dependency requirement to generated VPC node name
        reqs = node["requirements"]
        assert len(reqs) == 1
        dep = reqs[0]["vpc_id"]
        assert dep["relationship"] == "tosca.relationships.DependsOn"
        assert dep["node"] == "aws_vpc_main"

    def test_map_without_values_is_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSSubnetMapper()
        b = FakeBuilder()
        m.map_resource("aws_subnet.empty", "aws_subnet", {}, b)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_map_without_mapper_in_stack_no_requirement(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSSubnetMapper()
        b = FakeBuilder()
        data = {
            "values": {
                "cidr_block": "10.0.2.0/24",
                "availability_zone": "eu-west-1b",
            }
        }
        # Call without context
        m.map_resource("aws_subnet.other", "aws_subnet", data, b, None)

        node_name = "aws_subnet_other"
        assert node_name in b.nodes
        node = b.nodes[node_name]

        # Still has capability 'link'
        assert "link" in node["capabilities"]
        # No requirements added
        assert node["requirements"] == []
        # Warning logged
        assert any(
            "No context provided to detect dependencies" in r.message
            for r in caplog.records
        )

    def test_network_name_from_az_when_no_name_tag(self) -> None:
        m = AWSSubnetMapper()
        b = FakeBuilder()
        data = {
            "values": {
                "cidr_block": "10.0.3.0/24",
                "availability_zone": "eu-west-1c",
                "tags": {"env": "dev"},
            }
        }
        m.map_resource("aws_subnet.azonly", "aws_subnet", data, b)
        node = b.nodes["aws_subnet_azonly"]
        # network_name derived from AZ since no 'Name' tag
        assert node["properties"]["network_name"] == "subnet-eu-west-1c"
        # tags still in metadata
        assert node["metadata"]["aws_tags"]["env"] == "dev"
