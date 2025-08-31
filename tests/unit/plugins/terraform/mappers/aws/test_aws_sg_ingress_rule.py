from __future__ import annotations

from typing import Any

import pytest

from src.plugins.terraform.context import TerraformMappingContext
from src.plugins.terraform.mappers.aws.aws_vpc_security_group_ingress_rule import (
    AWSVPCSecurityGroupIngressRuleMapper,
)


class FakeNode:
    def __init__(self, name: str, node_type: str) -> None:
        self.name = name
        self.node_type = node_type
        # mimic ServiceTemplateBuilder's internal shape used by the mapper
        self._data: dict[str, Any] = {}

    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self._data["metadata"] = md
        return self


class FakeBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, FakeNode] = {}

    def add_node(self, name: str, node_type: str) -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node

    def get_node(self, name: str) -> FakeNode:
        return self.nodes[name]


# ------------------------------ tests -------------------------------


class TestCanMap:
    def test_true_for_ingress_rule(self) -> None:
        m = AWSVPCSecurityGroupIngressRuleMapper()
        assert m.can_map("aws_vpc_security_group_ingress_rule", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSVPCSecurityGroupIngressRuleMapper()
        assert m.can_map("aws_security_group", {}) is False


class TestGuards:
    def test_no_parsed_data_logs_and_skips(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSVPCSecurityGroupIngressRuleMapper()
        b = FakeBuilder()

        rd = {
            "address": "aws_vpc_security_group_ingress_rule.rule1",
            "values": {
                "from_port": 443,
                "to_port": 443,
                "ip_protocol": "tcp",
            },
        }
        # Call directly (no context provided)
        m.map_resource(
            "aws_vpc_security_group_ingress_rule.rule1",
            "aws_vpc_security_group_ingress_rule",
            rd,
            b,
            None,
        )

        assert any("No context provided" in r.message for r in caplog.records)
        assert b.nodes == {}

    def test_missing_values_logs_and_skips(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSVPCSecurityGroupIngressRuleMapper()
        b = FakeBuilder()
        parsed = {
            "configuration": {"root_module": {"resources": []}},
            "planned_values": {"root_module": {"resources": []}},
        }
        rd = {
            "address": "aws_vpc_security_group_ingress_rule.rule1",
            # no 'values'
        }

        context = TerraformMappingContext(parsed_data=parsed, variable_context=None)
        m.map_resource(
            "aws_vpc_security_group_ingress_rule.rule1",
            "aws_vpc_security_group_ingress_rule",
            rd,
            b,
            context,
        )

        assert any("has no 'values' section" in r.message for r in caplog.records)
        assert any(
            "Could not extract rule information" in r.message for r in caplog.records
        )
        assert b.nodes == {}

    def test_missing_config_logs_and_skips(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSVPCSecurityGroupIngressRuleMapper()
        b = FakeBuilder()
        parsed = {
            "configuration": {"root_module": {"resources": []}},
            "planned_values": {"root_module": {"resources": []}},
        }
        rd = {
            "address": "aws_vpc_security_group_ingress_rule.rule1",
            "values": {"from_port": 443, "to_port": 443, "ip_protocol": "tcp"},
        }

        context = TerraformMappingContext(parsed_data=parsed, variable_context=None)
        m.map_resource(
            "aws_vpc_security_group_ingress_rule.rule1",
            "aws_vpc_security_group_ingress_rule",
            rd,
            b,
            context,
        )

        assert any(
            "Could not find security group reference" in r.message
            for r in caplog.records
        )
        assert any(
            "Could not extract rule information" in r.message for r in caplog.records
        )
        assert b.nodes == {}


class TestHappyPath:
    def _parsed_with_refs(self, address: str) -> dict[str, Any]:
        # minimal config that carries the security_group_id and cidr refs
        return {
            "planned_values": {"root_module": {"resources": []}},
            "configuration": {
                "root_module": {
                    "resources": [
                        {
                            "address": address,
                            "expressions": {
                                "security_group_id": {
                                    "references": ["aws_security_group.allow_tls.id"]
                                },
                                "cidr_ipv4": {"references": ["var.world_cidr_v4"]},
                                "cidr_ipv6": {"references": ["var.world_cidr_v6"]},
                            },
                        }
                    ]
                }
            },
        }

    def test_adds_ingress_rule_to_existing_sg(self) -> None:
        m = AWSVPCSecurityGroupIngressRuleMapper()
        b = FakeBuilder()
        address = "aws_vpc_security_group_ingress_rule.rule1"
        parsed = self._parsed_with_refs(address)
        rd = {
            "address": address,
            "values": {
                "from_port": 443,
                "to_port": 443,
                "ip_protocol": "tcp",
                "description": "https",
                "cidr_ipv4": "0.0.0.0/0",
                "cidr_ipv6": "::/0",
            },
        }

        # Pre-create SG node the mapper will augment
        sg_node_name = "aws_security_group_allow_tls"
        b.add_node(sg_node_name, "Root").with_metadata({})

        context = TerraformMappingContext(parsed_data=parsed, variable_context=None)
        m.map_resource(
            address,
            "aws_vpc_security_group_ingress_rule",
            rd,
            b,
            context,
        )

        node = b.get_node(sg_node_name)
        md = node._data.get("metadata", {})
        rules = md.get("ingress_rules", [])
        assert len(rules) == 1
        rule = rules[0]

        assert rule["rule_id"] == "rule1"
        assert rule["from_port"] == 443
        assert rule["to_port"] == 443
        assert rule["protocol"] == "tcp"
        assert rule["description"] == "https"
        assert rule["cidr_ipv4"] == "0.0.0.0/0"
        assert rule["cidr_ipv6"] == "::/0"
        assert rule["cidr_ipv4_ref"] == "var.world_cidr_v4"
        assert rule["cidr_ipv6_ref"] == "var.world_cidr_v6"

    def test_missing_sg_node_is_warning_and_skips(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        m = AWSVPCSecurityGroupIngressRuleMapper()
        b = FakeBuilder()

        address = "aws_vpc_security_group_ingress_rule.rule1"
        parsed = self._parsed_with_refs(address)
        rd = {
            "address": address,
            "values": {"from_port": 22, "to_port": 22, "ip_protocol": "tcp"},
        }

        # do NOT create the SG node
        context = TerraformMappingContext(parsed_data=parsed, variable_context=None)
        m.map_resource(
            address,
            "aws_vpc_security_group_ingress_rule",
            rd,
            b,
            context,
        )

        assert any("Security group node not found" in r.message for r in caplog.records)
        assert b.nodes == {}
