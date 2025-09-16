from __future__ import annotations

from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper
from src.plugins.provisioning.terraform.mappers.aws.aws_route53_record import (
    AWSRoute53RecordMapper,
)


class FakeCap:
    def __init__(self, node: FakeNode, name: str) -> None:
        self.node = node
        self.name = name
        self.properties: dict[str, Any] = {}

    def with_property(self, key: str, value: Any) -> FakeCap:
        self.properties[key] = value
        return self

    def and_node(self) -> FakeNode:
        self.node.capabilities[self.name] = self.properties
        return self


class FakeReq:
    def __init__(self, node: FakeNode, name: str) -> None:
        self.node = node
        self.name = name
        self.target: str | None = None
        self.relationship: str | None = None
        self.target_cap: str | None = None

    def to_node(self, target: str) -> FakeReq:
        self.target = target
        return self

    def to_capability(self, cap: str) -> FakeReq:
        # store, in case tests want to inspect it
        self.target_cap = cap
        return self

    def with_relationship(self, rel: str) -> FakeReq:
        self.relationship = rel
        return self

    def and_node(self) -> FakeNode:
        self.node.requirements.append(
            (self.name, self.target, self.relationship, self.target_cap)
        )
        return self.node


class FakeNode:
    def __init__(self, name: str, node_type: str) -> None:
        self.name = name
        self.node_type = node_type
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.capabilities: dict[str, dict[str, Any]] = {}
        self.requirements: list[tuple[str, str | None, str | None, str | None]] = []

    # builder-like API used by the mapper
    def with_property(self, key: str, value: Any) -> FakeNode:
        self.properties[key] = value
        return self

    def with_properties(self, props: dict[str, Any]) -> FakeNode:
        self.properties.update(props)
        return self

    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self.metadata = md
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
        if name not in self.nodes:
            raise KeyError(name)
        return self.nodes[name]


class DummyCtx:
    """
    - get_resolved_values: returns raw values
    - extract_terraform_references: returns synthetic references
    """

    def __init__(self, zone_ref: str | None = None) -> None:
        self._zone_ref = zone_ref

    def get_resolved_values(
        self, resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        # In these tests we don't distinguish "property" vs "metadata"
        return resource_data.get("values", {})

    def extract_terraform_references(
        self, resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        # If we find a zone_id, return a ref to the provided zone
        values = resource_data.get("values", {})
        zid = values.get("zone_id")
        if zid and self._zone_ref:
            return [("zone_id", self._zone_ref, "DependsOn")]
        return []


class TestCanMap:
    def test_true_for_route53_record(self) -> None:
        m = AWSRoute53RecordMapper()
        assert m.can_map("aws_route53_record", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSRoute53RecordMapper()
        assert m.can_map("aws_route53_zone", {}) is False


class TestGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSRoute53RecordMapper()
        b = FakeBuilder()
        m.map_resource(
            "aws_route53_record.www", "aws_route53_record", {}, b, context=None
        )
        # No node created
        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)


class TestEndpointMapping:
    def test_public_endpoint_a_record_with_zone_link(self) -> None:
        m = AWSRoute53RecordMapper()
        b = FakeBuilder()

        zone_ref = "aws_route53_zone.main"
        ctx = DummyCtx(zone_ref=zone_ref)

        resource = {
            "values": {
                "name": "www",
                "type": "A",
                "zone_id": "Z12345",
                "ttl": 60,
                "records": ["1.2.3.4"],
                "fqdn": "www.example.com",
                "id": "Z12345_www_A",
            }
        }

        m.map_resource(
            "aws_route53_record.www", "aws_route53_record", resource, b, context=ctx
        )

        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route53_record.www", "aws_route53_record"
        )
        node = b.get_node(node_name)

        # Node type and basic property
        assert node.node_type == "Network"
        assert node.properties.get("network_type") == "dns_record"

        # Requirement to zone with DependsOn
        zone_node_name = BaseResourceMapper.generate_tosca_node_name(
            zone_ref, "aws_route53_zone"
        )
        assert ("zone", zone_node_name, "DependsOn", None) in node.requirements

        # Metadata essentials
        md = node.metadata
        assert md["aws_record_name"] == "www"
        assert md["aws_record_type"] == "A"
        assert md["aws_zone_id"] == "Z12345"
        assert md["aws_ttl"] == 60
        assert md["aws_records"] == ["1.2.3.4"]
        assert md["aws_fqdn"] == "www.example.com"
        assert md["aws_record_id"] == "Z12345_www_A"

    def test_private_endpoint_cname_no_context(self) -> None:
        m = AWSRoute53RecordMapper()
        b = FakeBuilder()

        # Name not in public_patterns and CNAME type -> Endpoint (not Public)
        resource = {
            "values": {
                "name": "db-internal",
                "type": "CNAME",
                "zone_id": "Z99999",
                "ttl": 300,
                "records": ["internal.elb.amazonaws.com"],
            }
        }

        m.map_resource(
            "aws_route53_record.db", "aws_route53_record", resource, b, context=None
        )

        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route53_record.db", "aws_route53_record"
        )
        node = b.get_node(node_name)

        assert node.node_type == "Network"
        assert node.properties.get("network_type") == "dns_record"
        # no link requirement without context
        assert node.requirements == []


class TestLoadBalancerMapping:
    def test_lb_when_weighted_policy_present(self) -> None:
        m = AWSRoute53RecordMapper()
        b = FakeBuilder()

        resource = {
            "values": {
                "name": "api",
                "type": "A",
                "zone_id": "Z1",
                "weighted_routing_policy": [{"weight": 50}],
            }
        }

        m.map_resource(
            "aws_route53_record.api",
            "aws_route53_record",
            resource,
            b,
            context=DummyCtx(),
        )

        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route53_record.api", "aws_route53_record"
        )
        node = b.get_node(node_name)

        assert node.node_type == "Network"
        # Check network properties
        assert node.properties.get("network_type") == "dns_record"
        assert node.properties.get("network_name") == "api"
        # For Network nodes representing DNS records, routing policies are in metadata
        assert "aws_weighted_routing_policy" in node.metadata

    def test_lb_when_only_set_identifier(self) -> None:
        m = AWSRoute53RecordMapper()
        b = FakeBuilder()

        resource = {
            "values": {
                "name": "geo",
                "type": "A",
                "zone_id": "Z1",
                "set_identifier": "eu-west-1a",
            }
        }

        m.map_resource(
            "aws_route53_record.geo",
            "aws_route53_record",
            resource,
            b,
            context=DummyCtx(),
        )

        node_name = BaseResourceMapper.generate_tosca_node_name(
            "aws_route53_record.geo", "aws_route53_record"
        )
        node = b.get_node(node_name)
        assert node.node_type == "Network"
        # Check network properties
        assert node.properties.get("network_type") == "dns_record"
