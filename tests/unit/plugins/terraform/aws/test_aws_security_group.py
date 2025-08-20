from __future__ import annotations

from typing import Any

import pytest
from plugins.terraform.mapper import TerraformMapper

from src.plugins.terraform.mappers.aws.aws_security_group import (
    AWSSecurityGroupMapper,
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
        self.metadata: dict[str, Any] = {}
        self.requirements: list[tuple[str, str | None, str | None]] = []

    # Mapper APIs used
    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        # Store by reference so later mutations are reflected
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


class Harness(TerraformMapper):
    """Helper to expose a frame with `self` being a TerraformMapper.

    This allows AWSSecurityGroupMapper to retrieve parsed_data via
    inspect.stack() -> get_current_parsed_data().
    """

    def invoke(
        self,
        sg: AWSSecurityGroupMapper,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: FakeBuilder,
        parsed_data: dict[str, Any],
    ) -> None:
        self._current_parsed_data = parsed_data
        sg.map_resource(resource_name, resource_type, resource_data, builder)


class TestCanMap:
    def test_true_for_sg(self) -> None:
        sg = AWSSecurityGroupMapper()
        assert sg.can_map("aws_security_group", {}) is True

    def test_false_for_other(self) -> None:
        sg = AWSSecurityGroupMapper()
        assert sg.can_map("aws_vpc", {}) is False


class TestMapBasic:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        sg = AWSSecurityGroupMapper()
        b = FakeBuilder()
        sg.map_resource("aws_security_group.empty", "aws_security_group", {}, b)
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_maps_metadata_and_legacy_rules(self) -> None:
        sg = AWSSecurityGroupMapper()
        b = FakeBuilder()
        resource_name = "aws_security_group.allow_tls"
        values = {
            "name": "allow-tls",
            "description": "TLS ingress",
            "vpc_id": "vpc-123",
            "arn": "arn:aws:ec2:region:acct:sg/sg-123",
            "id": "sg-123",
            "owner_id": "111122223333",
            "tags": {"env": "dev"},
            "tags_all": {"env": "dev", "owner": "team"},
            "ingress": [
                {
                    "from_port": 443,
                    "to_port": 443,
                    "protocol": "tcp",
                    "description": "https",
                    "cidr_blocks": ["0.0.0.0/0"],
                    "ipv6_cidr_blocks": ["::/0"],
                    "prefix_list_ids": [],
                    "security_groups": [],
                    "self": False,
                }
            ],
            "egress": [
                {
                    "from_port": 0,
                    "to_port": 0,
                    "protocol": "-1",
                    "description": "all",
                    "cidr_blocks": ["0.0.0.0/0"],
                    "ipv6_cidr_blocks": ["::/0"],
                    "prefix_list_ids": [],
                    "security_groups": [],
                    "self": False,
                }
            ],
        }
        resource_data = {"values": values}

        sg.map_resource(resource_name, "aws_security_group", resource_data, b)

        node = next(iter(b.nodes.values()))
        md = node.metadata

        assert node.node_type == "Root"
        assert md["original_resource_type"] == "aws_security_group"
        assert md["original_resource_name"] == "allow_tls"
        assert md["aws_security_group_name"] == "allow-tls"
        assert md["aws_description"] == "TLS ingress"
        assert md["aws_vpc_id"] == "vpc-123"
        assert md["aws_arn"].endswith("sg/sg-123")
        assert md["aws_security_group_id"] == "sg-123"
        assert md["aws_owner_id"] == "111122223333"
        assert md["aws_tags"] == {"env": "dev"}
        assert md["aws_tags_all"]["owner"] == "team"

        assert isinstance(md.get("aws_ingress_rules"), list)
        assert isinstance(md.get("aws_egress_rules"), list)
        assert md["aws_ingress_rules"][0]["from_port"] == 443
        assert md["aws_egress_rules"][0]["protocol"] == "-1"


class TestSeparateRulesAndDependencies:
    def test_collects_separate_rule_resources(self) -> None:
        sg = AWSSecurityGroupMapper()
        b = FakeBuilder()
        harness = Harness()

        # Use TerraformMapper.map to set current plan in the call stack
        harness.register_mapper("aws_security_group", sg)

        resource_name = "aws_security_group.allow_tls"
        parsed = {
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": resource_name,
                            "name": "allow_tls",
                            "type": "aws_security_group",
                            "values": {"name": "allow-tls", "vpc_id": "vpc-123"},
                        },
                        {
                            "address": "aws_vpc_security_group_ingress_rule.rule1",
                            "name": "rule1",
                            "type": "aws_vpc_security_group_ingress_rule",
                            "values": {
                                "from_port": 443,
                                "to_port": 443,
                                "ip_protocol": "tcp",
                                "description": "https",
                                "cidr_ipv4": "0.0.0.0/0",
                                "cidr_ipv6": "::/0",
                            },
                        },
                        {
                            "address": "aws_vpc_security_group_egress_rule.rule2",
                            "name": "rule2",
                            "type": "aws_vpc_security_group_egress_rule",
                            "values": {
                                "from_port": 0,
                                "to_port": 0,
                                "ip_protocol": "-1",
                                "description": "all",
                                "cidr_ipv4": "0.0.0.0/0",
                            },
                        },
                    ]
                }
            },
            "configuration": {
                "root_module": {
                    "resources": [
                        {
                            "address": resource_name,
                            "expressions": {},
                        },
                        {
                            "address": "aws_vpc_security_group_ingress_rule.rule1",
                            "expressions": {
                                "security_group_id": {
                                    "references": ["aws_security_group.allow_tls.id"]
                                },
                                "cidr_ipv4": {"references": ["var.world_cidr_v4"]},
                                "cidr_ipv6": {"references": ["var.world_cidr_v6"]},
                            },
                        },
                        {
                            "address": "aws_vpc_security_group_egress_rule.rule2",
                            "expressions": {
                                "security_group_id": {
                                    "references": ["aws_security_group.allow_tls.id"]
                                },
                                "cidr_ipv4": {"references": ["var.world_cidr_v4"]},
                            },
                        },
                    ]
                }
            },
        }

        harness.map(parsed, b)

        node = next(iter(b.nodes.values()))
        md = node.metadata

        assert any(r["rule_id"] == "rule1" for r in md["ingress_rules"])  # type: ignore[index]
        assert any(r["rule_id"] == "rule2" for r in md["egress_rules"])  # type: ignore[index]
        # refs captured
        ing = [r for r in md["ingress_rules"] if r["rule_id"] == "rule1"][0]
        assert ing["cidr_ipv4"] == "0.0.0.0/0"
        assert ing["cidr_ipv6"] == "::/0"
        assert ing["cidr_ipv4_ref"] == "var.world_cidr_v4"

    def test_adds_vpc_dependency_requirement(self) -> None:
        sg = AWSSecurityGroupMapper()
        b = FakeBuilder()
        harness = Harness()
        harness.register_mapper("aws_security_group", sg)

        resource_name = "aws_security_group.allow_tls"
        parsed = {
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": resource_name,
                            "name": "allow_tls",
                            "type": "aws_security_group",
                            "values": {"name": "allow-tls", "vpc_id": "vpc-123"},
                        }
                    ]
                }
            },
            "configuration": {
                "root_module": {
                    "resources": [
                        {
                            "address": resource_name,
                            "expressions": {
                                "vpc_id": {"references": ["aws_vpc.main.id"]}
                            },
                        }
                    ]
                }
            },
        }

        harness.map(parsed, b)

        node = next(iter(b.nodes.values()))
        # Expect a single dependency to aws_vpc_main with DependsOn
        assert ("dependency", "aws_vpc_main", "DependsOn") in node.requirements
