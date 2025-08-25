from __future__ import annotations

from typing import Any

import pytest

from src.plugins.terraform.mapper import TerraformMapper
from src.plugins.terraform.mappers.aws.aws_lb import AWSLoadBalancerMapper


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


class FakeCap:
    def __init__(self, node: FakeNode, name: str) -> None:
        self.node = node
        self.name = name
        self.props: dict[str, Any] = {}

    def with_property(self, k: str, v: Any) -> FakeCap:
        self.props[k] = v
        # store on node
        entry = self.node.capabilities.setdefault(self.name, {"properties": {}})
        entry["properties"][k] = v
        return self

    def and_node(self) -> FakeNode:
        return self.node


class FakeNode:
    def __init__(self, name: str, node_type: str) -> None:
        self.name = name
        self.node_type = node_type
        self.metadata: dict[str, Any] = {}
        self.properties: dict[str, Any] = {}
        self.capabilities: dict[str, dict[str, Any]] = {}
        self.requirements: list[tuple[str, str | None, Any]] = []

    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self.metadata = md
        return self

    def with_property(self, k: str, v: Any) -> FakeNode:
        self.properties[k] = v
        return self

    def add_capability(self, name: str) -> FakeCap:
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

    def get_node(self, name: str) -> FakeNode:
        return self.nodes[name]


class Harness(TerraformMapper):
    def invoke(
        self,
        mapper: AWSLoadBalancerMapper,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: FakeBuilder,
        parsed_data: dict[str, Any],
    ) -> None:
        self._current_parsed_data = parsed_data
        mapper.map_resource(resource_name, resource_type, resource_data, builder)


class TestCanMap:
    def test_true_for_aws_lb(self) -> None:
        m = AWSLoadBalancerMapper()
        assert m.can_map("aws_lb", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSLoadBalancerMapper()
        assert m.can_map("aws_alb", {}) is False


class TestGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSLoadBalancerMapper()
        b = FakeBuilder()
        h = Harness()

        rd = {"address": "aws_lb.web"}  # no 'values'
        parsed = {
            "configuration": {"root_module": {"resources": []}},
            "planned_values": {"root_module": {"resources": []}},
        }

        h.invoke(m, "aws_lb.web", "aws_lb", rd, b, parsed)

        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)


class TestALBExternalWithDependencies:
    def _parsed_with_refs(self, address: str) -> dict[str, Any]:
        # configuration includes subnet & sg references
        return {
            "planned_values": {"root_module": {"resources": []}},
            "configuration": {
                "root_module": {
                    "resources": [
                        {
                            "address": address,
                            "expressions": {
                                "subnets": {
                                    "references": [
                                        "aws_subnet.public1.id",
                                        "aws_subnet.public2.id",
                                    ]
                                },
                                "security_groups": {
                                    "references": ["aws_security_group.lb_sg.id"]
                                },
                            },
                        }
                    ]
                }
            },
        }

    def test_maps_alb_public_and_adds_dependencies(self) -> None:
        m = AWSLoadBalancerMapper()
        b = FakeBuilder()
        h = Harness()

        address = "aws_lb.web"
        parsed = self._parsed_with_refs(address)
        values = {
            "name": "web-lb",
            "load_balancer_type": "application",
            "internal": False,
            "ip_address_type": "ipv4",
            "region": "us-east-1",
            "enable_deletion_protection": True,
            "enable_http2": True,
            "idle_timeout": 60,
            "tags": {"env": "prod"},
        }
        rd = {
            "address": address,
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "values": values,
        }

        h.invoke(m, address, "aws_lb", rd, b, parsed)

        # node presence & type
        node = b.get_node("aws_lb_web")
        assert node.node_type == "LoadBalancer"

        # metadata
        md = node.metadata
        assert md["original_resource_type"] == "aws_lb"
        assert md["original_resource_name"] == "web"
        assert md["aws_component_type"] == "LoadBalancer"
        assert md["aws_load_balancer_type"] == "application"
        assert md["aws_internal"] is False
        assert md["aws_provider"].endswith("hashicorp/aws")
        assert md["aws_region"] == "us-east-1"
        assert md["aws_http2_enabled"] is True
        assert md["aws_deletion_protection_enabled"] is True
        assert md["aws_tags"] == {"env": "prod"}

        # properties
        assert node.properties["algorithm"] == "round_robin"

        # client capability (PUBLIC HTTP:80)
        cap_props = node.capabilities["client"]["properties"]
        assert cap_props["network_name"] == "PUBLIC"
        assert cap_props["protocol"] == "http"
        assert cap_props["port"] == 80
        assert cap_props["secure"] is False

        # dependencies from subnets and security groups
        targets = {t for (_name, t, _rel) in node.requirements}
        assert "aws_subnet_public1" in targets
        assert "aws_subnet_public2" in targets
        assert "aws_security_group_lb_sg" in targets

        # all relationships are DependsOn
        assert all(rel == "DependsOn" for (_n, _t, rel) in node.requirements)


class TestNLBInternalProperties:
    def test_maps_nlb_private_and_sets_expected_props(self) -> None:
        m = AWSLoadBalancerMapper()
        b = FakeBuilder()
        h = Harness()

        address = "aws_lb.nlb1"
        parsed = {
            "configuration": {
                "root_module": {"resources": [{"address": address, "expressions": {}}]}
            },
            "planned_values": {"root_module": {"resources": []}},
        }
        values = {
            "name": "nlb-1",
            "load_balancer_type": "network",
            "internal": True,
            "ip_address_type": "dualstack",
            "enable_cross_zone_load_balancing": True,
            "region": "eu-west-1",
        }
        rd = {"address": address, "values": values}

        h.invoke(m, address, "aws_lb", rd, b, parsed)

        node = b.get_node("aws_lb_nlb1")

        # algorithm for NLB
        assert node.properties["algorithm"] == "flow_hash"

        # PRIVATE TCP client capability
        cap_props = node.capabilities["client"]["properties"]
        assert cap_props["network_name"] == "PRIVATE"
        assert cap_props["protocol"] == "tcp"

        # metadata flags
        md = node.metadata
        assert md["aws_cross_zone_load_balancing"] is True
        assert md["aws_ip_address_type"] == "dualstack"
        assert md["aws_region"] == "eu-west-1"
