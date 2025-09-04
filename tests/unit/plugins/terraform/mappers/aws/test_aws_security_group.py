from __future__ import annotations

from typing import Any

import pytest

from src.plugins.terraform.mapper import TerraformMapper
from src.plugins.terraform.mappers.aws.aws_security_group import (
    AWSSecurityGroupMapper,
)
from src.plugins.terraform.mappers.aws.aws_vpc_security_group_egress_rule import (
    AWSVPCSecurityGroupEgressRuleMapper,
)
from src.plugins.terraform.mappers.aws.aws_vpc_security_group_ingress_rule import (
    AWSVPCSecurityGroupIngressRuleMapper,
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
        # Add _data attribute that rule mappers expect
        self._data: dict[str, Any] = {"metadata": self.metadata}

    # Mapper APIs used
    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        # Store by reference so later mutations are reflected
        self.metadata = md
        # Also update _data to match
        self._data["metadata"] = md
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

    def get_node(self, name: str) -> FakeNode:
        """Get a node by name (needed by rule mappers)."""
        if name not in self.nodes:
            raise KeyError(f"Node '{name}' not found")
        return self.nodes[name]


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

    def map(
        self,
        parsed_data: dict[str, Any],
        builder: FakeBuilder,
    ) -> None:
        """Override map to use our test harness logic."""
        self._current_parsed_data = parsed_data

        # Extract resources using parent logic
        for (
            resource_name,
            resource_type,
            resource_data,
        ) in self._extract_resources(parsed_data):
            self._process_single_resource(
                resource_name, resource_type, resource_data, builder
            )

    def _process_single_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder,  # Accept any builder type to match parent signature
    ) -> None:
        """
        Process a single resource using the appropriate mapper with proper context.
        """
        from src.plugins.terraform.context import TerraformMappingContext

        mapper_strategy = self._mappers.get(resource_type)

        if mapper_strategy:
            # Uses can_map for a finer check
            if mapper_strategy.can_map(resource_type, resource_data):
                self._logger.debug(
                    f"Mapping resource '{resource_name}' ({resource_type})"
                )

                # Create context object for dependency injection
                context = TerraformMappingContext(
                    parsed_data=self._current_parsed_data or {},
                    variable_context=None,  # Not needed for this test
                )

                # Call the resource mapper with proper context
                mapper_strategy.map_resource(
                    resource_name, resource_type, resource_data, builder, context
                )
            else:
                self._logger.debug(
                    f"Skipping resource '{resource_name}' "
                    f"({resource_type}) - cannot map"
                )
        else:
            self._logger.debug(
                f"No mapper registered for resource type '{resource_type}'"
            )


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


class TestSeparateRulesAndDependencies:
    def test_collects_separate_rule_resources(self) -> None:
        sg = AWSSecurityGroupMapper()
        ingress_mapper = AWSVPCSecurityGroupIngressRuleMapper()
        egress_mapper = AWSVPCSecurityGroupEgressRuleMapper()
        b = FakeBuilder()
        harness = Harness()

        # Register all three mappers
        harness.register_mapper("aws_security_group", sg)
        harness.register_mapper("aws_vpc_security_group_ingress_rule", ingress_mapper)
        harness.register_mapper("aws_vpc_security_group_egress_rule", egress_mapper)

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
                        },
                        {
                            "address": "aws_vpc.main",
                            "name": "main",
                            "type": "aws_vpc",
                            "values": {"id": "vpc-123", "cidr_block": "10.0.0.0/16"},
                        },
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
        assert ("vpc_id", "aws_vpc_main", "DependsOn") in node.requirements
