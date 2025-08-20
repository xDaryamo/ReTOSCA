from __future__ import annotations

import logging
from typing import Any

import pytest

from src.plugins.terraform.mappers.aws.aws_vpc import AWSVPCMapper


class FakeCap:
    def __init__(self, node: FakeNode) -> None:
        self.node = node

    def and_node(self) -> FakeNode:
        return self.node


class FakeNode:
    def __init__(self) -> None:
        self.type: str | None = None
        self.props: dict[str, Any] = {}
        self.meta: dict[str, Any] = {}
        self.caps: set[str] = set()

    def with_property(self, k: str, v: Any) -> FakeNode:
        self.props[k] = v
        return self

    def with_metadata(self, m: dict[str, Any]) -> FakeNode:
        self.meta.update(m)
        return self

    def add_capability(self, name: str) -> FakeCap:
        self.caps.add(name)
        return FakeCap(self)


class FakeBuilder:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.nodes: list[FakeNode] = []

    def add_node(self, name: str, node_type: str) -> FakeNode:
        n = FakeNode()
        n.type = node_type
        self.created.append((name, node_type))
        self.nodes.append(n)
        return n


def _vals(**kw: Any) -> dict[str, Any]:
    return {"values": kw, "provider_name": "registry.terraform.io/hashicorp/aws"}


class TestCanMap:
    def test_true_only_for_vpc(self) -> None:
        m = AWSVPCMapper()
        assert m.can_map("aws_vpc", {}) is True
        assert m.can_map("aws_subnet", {}) is False


class TestMap:
    def test_maps_basic(self) -> None:
        m = AWSVPCMapper()
        b = FakeBuilder()
        data = _vals(
            cidr_block="10.0.0.0/16",
            instance_tenancy="default",
            enable_dns_hostnames=True,
            enable_dns_support=True,
            tags={"env": "dev"},
        )
        m.map_resource("aws_vpc.main", "aws_vpc", data, b)
        assert b.created and b.created[0][1] == "Network"
        n = b.nodes[0]
        assert n.props["cidr"] == "10.0.0.0/16"
        assert n.props["ip_version"] == 4
        assert n.props["dhcp_enabled"] is True
        assert "link" in n.caps
        md = n.meta
        assert md["original_resource_type"] == "aws_vpc"
        assert md["original_resource_name"] == "main"
        assert md["aws_provider"]
        assert md["aws_instance_tenancy"] == "default"
        assert md["aws_enable_dns_hostnames"] is True
        assert md["aws_enable_dns_support"] is True
        assert md["terraform_tags"] == {"env": "dev"}

    def test_ipv6_only_sets_v6(self) -> None:
        m = AWSVPCMapper()
        b = FakeBuilder()
        data = _vals(
            assign_generated_ipv6_cidr_block=True,
            ipv6_cidr_block="2600:1::/56",
        )
        m.map_resource("aws_vpc.v6", "aws_vpc", data, b)
        n = b.nodes[0]
        assert n.props["ip_version"] == 6

    def test_dual_stack_keeps_v4(self) -> None:
        m = AWSVPCMapper()
        b = FakeBuilder()
        data = _vals(
            cidr_block="10.1.0.0/16",
            ipv6_cidr_block="2600:2::/56",
        )
        m.map_resource("aws_vpc.ds", "aws_vpc", data, b)
        n = b.nodes[0]
        assert n.props["ip_version"] == 4

    def test_tags_all_only_when_diff(self) -> None:
        m = AWSVPCMapper()
        b = FakeBuilder()
        data = _vals(tags={"a": "1"}, tags_all={"a": "1", "b": "2"})
        m.map_resource("aws_vpc.t", "aws_vpc", data, b)
        n = b.nodes[0]
        assert n.meta.get("terraform_tags_all") == {"a": "1", "b": "2"}

    def test_default_ids_to_meta(self) -> None:
        m = AWSVPCMapper()
        b = FakeBuilder()
        data = _vals(
            default_security_group_id="sg-1",
            default_network_acl_id="acl-1",
            default_route_table_id="rtb-1",
            main_route_table_id="rtb-main",
            owner_id="123",
        )
        m.map_resource("aws_vpc.ids", "aws_vpc", data, b)
        md = b.nodes[0].meta
        assert md["aws_default_security_group_id"] == "sg-1"
        assert md["aws_default_network_acl_id"] == "acl-1"
        assert md["aws_default_route_table_id"] == "rtb-1"
        assert md["aws_main_route_table_id"] == "rtb-main"
        assert md["aws_owner_id"] == "123"

    def test_no_values_skips(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSVPCMapper()
        b = FakeBuilder()
        data = {"values": {}}
        m.map_resource("aws_vpc.x", "aws_vpc", data, b)
        assert b.created == []
        assert any("no 'values'" in r.getMessage() for r in caplog.records)
