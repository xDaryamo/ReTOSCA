from __future__ import annotations

from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper
from src.plugins.terraform.mappers.aws.aws_elasticache_replication_group import (
    AWSElastiCacheReplicationGroupMapper,
)


class FakeReq:
    def __init__(self, node: FakeNode, name: str) -> None:
        self.node = node
        self.name = name
        self.target: str | None = None
        self.relationship: Any | None = None

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
        # ensure the capability exists even before setting properties
        if name not in self.node.capabilities:
            self.node.capabilities[name] = {}

    def with_property(self, k: str, v: Any) -> FakeCap:
        self.node.capabilities[self.name][k] = v
        return self

    def and_node(self) -> FakeNode:
        return self.node


class FakeNode:
    def __init__(self, name: str, node_type: str) -> None:
        self.name = name
        self.node_type = node_type
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.capabilities: dict[str, dict[str, Any]] = {}
        self.requirements: list[tuple[str, str | None, Any | None]] = []

    # Mapper APIs used
    def with_property(self, k: str, v: Any) -> FakeNode:
        self.properties[k] = v
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
        return self.nodes[name]


class DummyCtx:
    """Minimal context used by the mapper in tests."""

    def __init__(self, refs: list[tuple[str, str, str]] | None = None) -> None:
        # list of (prop_name, target_ref, relationship_type)
        self._refs = refs or []

    def get_resolved_values(
        self, resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        # For tests, return the raw values regardless of "kind"
        return resource_data.get("values", {})

    def extract_terraform_references(
        self, resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        return list(self._refs)


class TestCanMap:
    def test_true_for_elasticache_rg(self) -> None:
        m = AWSElastiCacheReplicationGroupMapper()
        assert m.can_map("aws_elasticache_replication_group", {}) is True

    def test_false_for_other_type(self) -> None:
        m = AWSElastiCacheReplicationGroupMapper()
        assert m.can_map("aws_db_instance", {}) is False


class TestValidationGuards:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        m = AWSElastiCacheReplicationGroupMapper()
        b = FakeBuilder()

        m.map_resource(
            "aws_elasticache_replication_group.empty",
            "aws_elasticache_replication_group",
            {},
            b,
        )

        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)


class TestHappyPathNoContext:
    def test_sets_name_from_replication_group_id_and_default_port(self) -> None:
        m = AWSElastiCacheReplicationGroupMapper()
        b = FakeBuilder()

        resource_name = "aws_elasticache_replication_group.example"
        values = {
            "replication_group_id": "rg-main",
            # no explicit port -> should default to 6379
            "tags": {"env": "test"},
        }
        resource = {
            "values": values,
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }

        m.map_resource(resource_name, "aws_elasticache_replication_group", resource, b)

        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, "aws_elasticache_replication_group"
        )
        node = b.nodes[node_name]

        assert node.node_type == "Database"
        assert node.properties["name"] == "rg-main"
        assert node.properties["port"] == 6379  # default for Redis
        assert "database_endpoint" in node.capabilities

        md = node.metadata
        assert md["original_resource_type"] == "aws_elasticache_replication_group"
        assert md["original_resource_name"] == "example"
        assert md["aws_component_type"] == "ElastiCacheReplicationGroup"
        assert md["aws_provider"].endswith("/aws")
        # when default port is used, mapper records it in metadata
        assert md["aws_default_port"] == 6379
        assert md["aws_tags"] == {"env": "test"}

    def test_auth_token_sets_password_and_flag(self) -> None:
        m = AWSElastiCacheReplicationGroupMapper()
        b = FakeBuilder()

        resource_name = "aws_elasticache_replication_group.secure"
        resource = {
            "values": {
                "replication_group_id": "rg-secure",
                "auth_token": "super-secret",
            }
        }

        m.map_resource(resource_name, "aws_elasticache_replication_group", resource, b)

        node = b.nodes[
            BaseResourceMapper.generate_tosca_node_name(
                resource_name, "aws_elasticache_replication_group"
            )
        ]
        assert node.properties["password"] == "super-secret"
        assert node.metadata["aws_auth_token_enabled"] is True


class TestHappyPathWithContext:
    def test_dependencies_added_from_context(self) -> None:
        m = AWSElastiCacheReplicationGroupMapper()
        b = FakeBuilder()

        # Two references coming from the context:
        # - subnet group
        # - security group
        refs = [
            ("subnet_group_name", "aws_elasticache_subnet_group.main", "DependsOn"),
            ("security_group_ids", "aws_security_group.sg", "DependsOn"),
        ]
        ctx = DummyCtx(refs=refs)

        resource_name = "aws_elasticache_replication_group.cluster"
        resource = {
            "values": {
                "replication_group_id": "rg-cluster",
                "port": 6380,
            },
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }

        m.map_resource(
            resource_name, "aws_elasticache_replication_group", resource, b, context=ctx
        )

        node = b.nodes[
            BaseResourceMapper.generate_tosca_node_name(
                resource_name, "aws_elasticache_replication_group"
            )
        ]

        # Expect two requirements pointing to generated TOSCA node names from refs
        expected_targets = {
            BaseResourceMapper.generate_tosca_node_name(
                "aws_elasticache_subnet_group.main", "aws_elasticache_subnet_group"
            ),
            BaseResourceMapper.generate_tosca_node_name(
                "aws_security_group.sg", "aws_security_group"
            ),
        }
        actual_targets = {t for (_name, t, _rel) in node.requirements}
        assert expected_targets.issubset(actual_targets)

        # Requirement names should match prop names
        assert ("subnet_group_name", next(iter(expected_targets)), "DependsOn") in {
            (n, t, r) for (n, t, r) in node.requirements if t in expected_targets
        } or ("security_group_ids", next(iter(expected_targets)), "DependsOn") in {
            (n, t, r) for (n, t, r) in node.requirements if t in expected_targets
        }

    def test_respects_explicit_port_when_present(self) -> None:
        m = AWSElastiCacheReplicationGroupMapper()
        b = FakeBuilder()
        ctx = DummyCtx()

        resource_name = "aws_elasticache_replication_group.withport"
        resource = {"values": {"replication_group_id": "rg", "port": 6390}}

        m.map_resource(
            resource_name, "aws_elasticache_replication_group", resource, b, context=ctx
        )

        node = b.nodes[
            BaseResourceMapper.generate_tosca_node_name(
                resource_name, "aws_elasticache_replication_group"
            )
        ]
        assert node.properties["port"] == 6390


class TestMetadataMapping:
    def test_maps_common_metadata_fields(self) -> None:
        m = AWSElastiCacheReplicationGroupMapper()
        b = FakeBuilder()

        resource_name = "aws_elasticache_replication_group.meta"
        resource = {
            "values": {
                "replication_group_id": "rg-meta",
                "engine": "redis",
                "engine_version": "7.0",
                "node_type": "cache.t3.small",
                "num_node_groups": 2,
                "replicas_per_node_group": 1,
                "automatic_failover_enabled": True,
                "multi_az_enabled": True,
                "preferred_cache_cluster_azs": ["eu-west-1a", "eu-west-1b"],
                "parameter_group_name": "default.redis7",
                "subnet_group_name": "cache-subnets",
                "security_group_ids": ["sg-123"],
                "at_rest_encryption_enabled": True,
                "transit_encryption_enabled": True,
                "kms_key_id": "arn:aws:kms:region:acct:key/abc",
                "snapshot_retention_limit": 7,
                "maintenance_window": "sun:05:00-sun:06:00",
                "apply_immediately": False,
                "notification_topic_arn": "arn:sns:...",
                "tags": {"service": "cache"},
                "arn": "arn:aws:elasticache:...",
                "cluster_enabled": True,
                "primary_endpoint_address": "cache-primary.example",
                "reader_endpoint_address": "cache-read.example",
                "member_clusters": ["cluster-0001-001", "cluster-0001-002"],
            }
        }

        m.map_resource(resource_name, "aws_elasticache_replication_group", resource, b)

        node = b.nodes[
            BaseResourceMapper.generate_tosca_node_name(
                resource_name, "aws_elasticache_replication_group"
            )
        ]
        md = node.metadata

        assert md["aws_engine"] == "redis"
        assert md["aws_engine_version"] == "7.0"
        assert md["aws_node_type"] == "cache.t3.small"
        assert md["aws_num_node_groups"] == 2
        assert md["aws_replicas_per_node_group"] == 1
        assert md["aws_automatic_failover_enabled"] is True
        assert md["aws_multi_az_enabled"] is True
        assert md["aws_preferred_cache_cluster_azs"] == ["eu-west-1a", "eu-west-1b"]
        assert md["aws_parameter_group_name"] == "default.redis7"
        assert md["aws_subnet_group_name"] == "cache-subnets"
        assert md["aws_security_group_ids"] == ["sg-123"]
        assert md["aws_at_rest_encryption_enabled"] is True
        assert md["aws_transit_encryption_enabled"] is True
        assert md["aws_kms_key_id"].startswith("arn:")
        assert md["aws_snapshot_retention_limit"] == 7
        assert md["aws_maintenance_window"].startswith("sun:")
        assert md["aws_apply_immediately"] is False
        assert md["aws_tags"] == {"service": "cache"}
        assert md["aws_arn"].startswith("arn:")
        assert md["aws_cluster_enabled"] is True
        assert md["aws_primary_endpoint_address"] == "cache-primary.example"
        assert md["aws_reader_endpoint_address"] == "cache-read.example"
        assert md["aws_member_clusters"] == ["cluster-0001-001", "cluster-0001-002"]
