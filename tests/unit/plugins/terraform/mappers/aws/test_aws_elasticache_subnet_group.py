from __future__ import annotations

from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper
from src.plugins.provisioning.terraform.mappers.aws.aws_elasticache_subnet_group import (  # noqa: E501
    AWSElastiCacheSubnetGroupMapper,
)


class FakePolicy:
    def __init__(self, name: str, policy_type: str, builder: FakeBuilder) -> None:
        self.name = name
        self.policy_type = policy_type
        self.builder = builder
        self.metadata: dict[str, Any] = {}
        self.properties: dict[str, Any] = {}
        self.targets: list[str] = []

    def with_metadata(self, md: dict[str, Any]) -> FakePolicy:
        self.metadata = md
        return self

    def with_property(self, key: str, value: Any) -> FakePolicy:
        self.properties[key] = value
        return self

    def with_targets(self, *targets: str) -> FakePolicy:
        self.targets.extend(list(targets))
        return self

    def and_service(self) -> FakeBuilder:
        return self.builder


class FakeBuilder:
    def __init__(self) -> None:
        self.policies: dict[str, FakePolicy] = {}

    def add_policy(self, name: str, policy_type: str) -> FakePolicy:
        pol = FakePolicy(name, policy_type, self)
        self.policies[name] = pol
        return pol


class DummyCtx:
    """Minimal context to satisfy mapper calls in tests."""

    def __init__(
        self,
        refs: list[tuple[str, str, str]] | None = None,
        parsed_data: dict[str, Any] | None = None,
    ) -> None:
        # list of (prop_name, target_ref, relationship_type)
        self._refs = refs or []
        self.parsed_data = parsed_data or {}

    def get_resolved_values(
        self, resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        # return the raw values for test purposes
        return resource_data.get("values", {})

    def extract_terraform_references(
        self, resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        return list(self._refs)


class TestCanMap:
    def test_true_for_elasticache_subnet_group(self) -> None:
        m = AWSElastiCacheSubnetGroupMapper()
        assert m.can_map("aws_elasticache_subnet_group", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSElastiCacheSubnetGroupMapper()
        assert m.can_map("aws_db_subnet_group", {}) is False


class TestValidationGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSElastiCacheSubnetGroupMapper()
        b = FakeBuilder()

        m.map_resource(
            "aws_elasticache_subnet_group.empty",
            "aws_elasticache_subnet_group",
            {},
            b,
        )

        assert b.policies == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)

    def test_skips_when_missing_subnet_ids_and_no_refs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("ERROR")
        m = AWSElastiCacheSubnetGroupMapper()
        b = FakeBuilder()

        resource_name = "aws_elasticache_subnet_group.sg"
        resource = {"values": {"name": "cache-subnets"}}
        ctx = DummyCtx(refs=[], parsed_data={})

        m.map_resource(
            resource_name, "aws_elasticache_subnet_group", resource, b, context=ctx
        )

        assert b.policies == {}
        assert any(
            "missing required field 'subnet_ids'" in r.message for r in caplog.records
        )


class TestHappyPathWithConcreteSubnetIds:
    def test_policy_created_with_metadata_and_counts(self) -> None:
        m = AWSElastiCacheSubnetGroupMapper()
        b = FakeBuilder()

        resource_name = "aws_elasticache_subnet_group.bar"
        values = {
            "name": "cache-subnets",
            "description": "subnets for cache",
            "subnet_ids": ["subnet-1", "subnet-2"],
            "region": "eu-west-1",
            "tags": {"env": "dev"},
            "arn": "arn:aws:elasticache:...",
            "id": "sg-123",
            "vpc_id": "vpc-aaa",
        }
        resource = {
            "values": values,
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }

        # context present but not strictly needed here;
        # it enables AZ enrichment if parsed_data provided
        parsed_data = {
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_subnet.app1",
                            "type": "aws_subnet",
                            "values": {
                                "cidr_block": "10.0.1.0/24",
                                "availability_zone": "eu-west-1a",
                                "tags": {"Name": "app-1"},
                                "map_public_ip_on_launch": False,
                            },
                        },
                        {
                            "address": "aws_subnet.app2",
                            "type": "aws_subnet",
                            "values": {
                                "cidr_block": "10.0.2.0/24",
                                "availability_zone": "eu-west-1b",
                                "map_public_ip_on_launch": True,
                            },
                        },
                    ]
                }
            }
        }
        # we won’t rely on refs for enrichment here
        ctx = DummyCtx(parsed_data=parsed_data)

        m.map_resource(
            resource_name, "aws_elasticache_subnet_group", resource, b, context=ctx
        )

        pol_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, "aws_elasticache_subnet_group"
        )
        assert pol_name in b.policies
        pol = b.policies[pol_name]

        md = pol.metadata
        assert md["original_resource_type"] == "aws_elasticache_subnet_group"
        assert md["original_resource_name"] == "bar"
        assert md["aws_component_type"] == "ElastiCacheSubnetGroup"
        assert md["terraform_provider"].endswith("/aws")
        assert md["aws_cache_subnet_group_name"] == "cache-subnets"
        assert md["aws_cache_subnet_group_description"] == "subnets for cache"
        assert md["aws_subnet_ids"] == ["subnet-1", "subnet-2"]
        assert md["aws_subnet_count"] == 2
        assert md["aws_region"] == "eu-west-1"
        assert md["aws_tags"] == {"env": "dev"}
        assert md["aws_arn"].startswith("arn:")
        assert md["aws_cache_subnet_group_id"] == "sg-123"
        assert md["aws_vpc_id"] == "vpc-aaa"
        # placement hints
        assert md["placement_zone"] == "cache_subnet_group"
        assert md["subnet_group_name"] == "cache-subnets"
        # targets not set automatically here (no matching ElastiCache in parsed_data)
        assert pol.targets == []


class TestHappyPathWithReferencesAndTargets:
    def test_accepts_refs_when_no_subnet_ids_and_targets_elasticache(self) -> None:
        m = AWSElastiCacheSubnetGroupMapper()
        b = FakeBuilder()

        resource_name = "aws_elasticache_subnet_group.cache"
        resource = {
            "values": {
                "name": "cache-subnets",
                # intentionally no "subnet_ids" -> will rely on refs
            },
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }

        # Terraform references mention subnets; parsed_data includes those subnets
        refs = [
            ("subnet_ids", "aws_subnet.app1", "DependsOn"),
            ("subnet_ids", "aws_subnet.app2", "DependsOn"),
        ]
        parsed_data = {
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_subnet.app1",
                            "type": "aws_subnet",
                            "values": {
                                "cidr_block": "10.0.1.0/24",
                                "availability_zone": "eu-west-1a",
                                "map_public_ip_on_launch": False,
                            },
                        },
                        {
                            "address": "aws_subnet.app2",
                            "type": "aws_subnet",
                            "values": {
                                "cidr_block": "10.0.2.0/24",
                                "availability_zone": "eu-west-1b",
                                "map_public_ip_on_launch": True,
                            },
                        },
                        # An ElastiCache resource that uses this subnet group
                        # -> should become a target
                        {
                            "address": "aws_elasticache_replication_group.main",
                            "type": "aws_elasticache_replication_group",
                            "values": {"subnet_group_name": "cache-subnets"},
                        },
                    ]
                }
            }
        }
        ctx = DummyCtx(refs=refs, parsed_data=parsed_data)

        m.map_resource(
            resource_name, "aws_elasticache_subnet_group", resource, b, context=ctx
        )

        pol_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, "aws_elasticache_subnet_group"
        )
        pol = b.policies[pol_name]

        md = pol.metadata
        # Since subnet_ids absent, we expect "availability_zones" sentinel
        # and placement set
        assert md["placement_zone"] == "cache_subnet_group"
        assert md["availability_zones"] == "referenced"
        # Subnet details filled from parsed_data
        assert "aws_subnet_details" in md and len(md["aws_subnet_details"]) == 2
        azs = md.get("aws_availability_zones", [])
        assert set(azs) == {"eu-west-1a", "eu-west-1b"}

        # Targets include the ElastiCache replication group node name (with _dbms)
        expected_target = BaseResourceMapper.generate_tosca_node_name(
            "aws_elasticache_replication_group.main_dbms",
            "aws_elasticache_replication_group",
        )
        assert expected_target in pol.targets
