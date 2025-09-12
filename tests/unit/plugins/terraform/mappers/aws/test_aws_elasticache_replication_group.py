# tests/test_aws_elasticache_replication_group_mapper.py
import pytest

from src.plugins.provisioning.terraform.exceptions import TerraformDataError
from src.plugins.terraform.mappers.aws.aws_elasticache_replication_group import (
    AWSElastiCacheReplicationGroupMapper,
)


class FakeRequirementChain:
    def __init__(self, node, req_name: str):
        self._node = node
        self._req = {"name": req_name, "target": None, "relationship": None}

    def to_node(self, target: str):
        self._req["target"] = target
        return self

    def with_relationship(self, relationship: str):
        self._req["relationship"] = relationship
        return self

    def and_node(self):
        self._node.requirements.append(self._req)
        return self._node


class FakeNode:
    def __init__(self, name: str, node_type: str):
        self.name = name
        self.node_type = node_type
        self.properties = {}
        self.metadata = {}
        self.requirements = []

    def with_property(self, key, value):
        self.properties[key] = value
        return self

    def with_metadata(self, metadata: dict):
        self.metadata.update(metadata or {})
        return self

    def add_requirement(self, name: str) -> FakeRequirementChain:
        return FakeRequirementChain(self, name)


class FakeBuilder:
    def __init__(self):
        self.nodes = {}

    def add_node(self, name: str, node_type: str) -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node

    def get_node(self, name: str) -> FakeNode | None:
        return self.nodes.get(name)


class FakeContext:
    def __init__(self, props=None, meta=None, refs=None):
        self._props = props or {}
        self._meta = meta or {}
        self._refs = refs or []

    def get_resolved_values(self, resource_data: dict, value_type: str) -> dict:
        if value_type == "property":
            return self._props
        if value_type == "metadata":
            return self._meta
        return {}

    def extract_terraform_references(self, resource_data: dict):
        # List of tuples (prop_name, target_ref, relationship_type)
        return list(self._refs)


@pytest.fixture
def mapper():
    return AWSElastiCacheReplicationGroupMapper()


@pytest.fixture
def builder():
    return FakeBuilder()


def test_can_map_true(mapper):
    assert mapper.can_map("aws_elasticache_replication_group", {}) is True


def test_can_map_false(mapper):
    assert mapper.can_map("aws_elasticache_cluster", {}) is False


def test_raises_when_no_values(mapper, builder):
    resource_name = "aws_elasticache_replication_group.example"
    with pytest.raises(TerraformDataError):
        mapper.map_resource(
            resource_name,
            "aws_elasticache_replication_group",
            {"values": {}},
            builder,
            context=None,
        )
    assert builder.nodes == {}, "Should not create nodes if 'values' is empty"


def test_creates_dbms_and_database_with_defaults_and_relationship(mapper, builder):
    resource_name = "aws_elasticache_replication_group.rg"
    resource_type = "aws_elasticache_replication_group"
    # Without context: metadata == values; no engine/port -> default 6379
    resource_data = {
        "provider_name": "registry.terraform.io/hashicorp/aws",
        "values": {"replication_group_id": "rg-1"},
    }

    mapper.map_resource(
        resource_name, resource_type, resource_data, builder, context=None
    )

    dbms_key = next(name for name in builder.nodes if name.endswith("_dbms"))
    db_key = next(name for name in builder.nodes if name.endswith("_database"))

    dbms = builder.nodes[dbms_key]
    database = builder.nodes[db_key]

    assert dbms.node_type == "DBMS"
    assert database.node_type == "Database"

    # Default ports to 6379
    assert dbms.properties.get("port") == 6379
    assert database.properties.get("port") == 6379

    # Database.name from replication_group_id
    assert database.properties.get("name") == "rg-1"

    # HostedOn relationship from Database to DBMS
    host_reqs = [r for r in database.requirements if r["name"] == "host"]
    assert host_reqs, "Missing 'host' requirement on Database"
    assert host_reqs[0]["relationship"] == "HostedOn"
    assert host_reqs[0]["target"] == dbms_key

    # Provider propagated in metadata
    assert dbms.metadata.get("aws_provider")
    assert database.metadata.get("aws_provider")


def test_uses_metadata_engine_port_version(mapper, builder):
    resource_name = "aws_elasticache_replication_group.mem"
    resource_type = "aws_elasticache_replication_group"
    resource_data = {"provider_name": "aws"}

    prop_values = {"replication_group_id": "mem-rg"}
    md_values = {"engine": "memcached", "engine_version": "1.6.21", "port": 11222}
    ctx = FakeContext(props=prop_values, meta=md_values)

    mapper.map_resource(
        resource_name, resource_type, resource_data, builder, context=ctx
    )

    dbms_key = next(name for name in builder.nodes if name.endswith("_dbms"))
    db_key = next(name for name in builder.nodes if name.endswith("_database"))
    dbms = builder.nodes[dbms_key]
    database = builder.nodes[db_key]

    # Ports taken from metadata
    assert dbms.properties["port"] == 11222
    assert database.properties["port"] == 11222

    # Standardized engine metadata on DBMS
    assert dbms.metadata.get("aws_engine") == "memcached"
    assert dbms.metadata.get("aws_engine_type") == "Memcached"
    assert dbms.metadata.get("aws_engine_version") == "1.6.21"

    # Database.name from replication_group_id
    assert database.properties.get("name") == "mem-rg"


def test_dependencies_are_added_on_dbms_only(mapper, builder):
    resource_name = "aws_elasticache_replication_group.with_refs"
    resource_type = "aws_elasticache_replication_group"
    resource_data = {"provider_name": "aws"}

    prop_values = {"replication_group_id": "dep-rg"}
    md_values = {"engine": "redis", "port": 6379}
    refs = [
        ("subnet_group_name", "aws_elasticache_subnet_group.sg", "DependsOn"),
        ("security_group_ids", "aws_security_group.cache", "DependsOn"),
    ]
    ctx = FakeContext(props=prop_values, meta=md_values, refs=refs)

    mapper.map_resource(
        resource_name, resource_type, resource_data, builder, context=ctx
    )

    dbms_key = next(name for name in builder.nodes if name.endswith("_dbms"))
    db_key = next(name for name in builder.nodes if name.endswith("_database"))
    dbms = builder.nodes[dbms_key]
    database = builder.nodes[db_key]

    # DBMS has requirements from references
    req_pairs = {(r["name"], r["relationship"]) for r in dbms.requirements}
    assert ("subnet_group_name", "DependsOn") in req_pairs
    assert ("security_group_ids", "DependsOn") in req_pairs

    # Database only has HostedOn
    db_req_names = {r["name"] for r in database.requirements}
    assert db_req_names == {"host"}


def test_security_flags_on_dbms(mapper, builder):
    resource_name = "aws_elasticache_replication_group.sec"
    resource_type = "aws_elasticache_replication_group"
    resource_data = {"provider_name": "aws"}

    prop_values = {"replication_group_id": "sec-rg"}
    md_values = {
        "engine": "redis",
        "auth_token": "****",
        "at_rest_encryption_enabled": True,
        "transit_encryption_enabled": True,
    }
    ctx = FakeContext(props=prop_values, meta=md_values)

    mapper.map_resource(
        resource_name, resource_type, resource_data, builder, context=ctx
    )

    dbms_key = next(name for name in builder.nodes if name.endswith("_dbms"))
    dbms = builder.nodes[dbms_key]

    assert dbms.metadata.get("aws_auth_token_enabled") is True
    assert dbms.metadata.get("aws_at_rest_encryption_enabled") is True
    assert dbms.metadata.get("aws_transit_encryption_enabled") is True


def test_description_on_database_metadata(mapper, builder):
    resource_name = "aws_elasticache_replication_group.desc"
    resource_type = "aws_elasticache_replication_group"
    resource_data = {"provider_name": "aws"}

    prop_values = {"replication_group_id": "rgd"}
    md_values = {"engine": "redis", "description": "My RG"}
    ctx = FakeContext(props=prop_values, meta=md_values)

    mapper.map_resource(
        resource_name, resource_type, resource_data, builder, context=ctx
    )

    db_key = next(name for name in builder.nodes if name.endswith("_database"))
    database = builder.nodes[db_key]

    assert database.metadata.get("aws_description") == "My RG"
