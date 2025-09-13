# tests/test_aws_elasticache_cluster_mapper.py
import pytest

from src.plugins.terraform.mappers.aws.aws_elasticache_cluster import (
    AWSElastiCacheClusterMapper,
)


# ----------------- Minimal Fakes: Builder/Node/Chains -----------------
class FakeCapabilityChain:
    def __init__(self, node, cap_name: str):
        self._node = node
        self._cap_name = cap_name
        self._props = {}

    def with_property(self, key, value):
        self._props[key] = value
        return self

    def and_node(self):
        self._node.capabilities[self._cap_name] = dict(self._props)
        return self._node


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
        self.capabilities = {}

    def with_property(self, key, value):
        self.properties[key] = value
        return self

    def with_metadata(self, metadata: dict):
        self.metadata.update(metadata or {})
        return self

    def add_requirement(self, name: str) -> FakeRequirementChain:
        return FakeRequirementChain(self, name)

    def add_capability(self, name: str) -> FakeCapabilityChain:
        return FakeCapabilityChain(self, name)


class FakeBuilder:
    def __init__(self):
        self.nodes = {}

    def add_node(self, name: str, node_type: str) -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node

    def get_node(self, name: str) -> FakeNode | None:
        return self.nodes.get(name)


# ----------------- Fake context -----------------
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


# ----------------- Fixtures -----------------
@pytest.fixture
def mapper():
    return AWSElastiCacheClusterMapper()


@pytest.fixture
def builder():
    return FakeBuilder()


# ----------------- Tests -----------------
def test_can_map_true(mapper):
    assert mapper.can_map("aws_elasticache_cluster", {}) is True


def test_can_map_false(mapper):
    assert mapper.can_map("aws_elasticache_replication_group", {}) is False


def test_skips_when_no_values(mapper, builder):
    resource_name = "aws_elasticache_cluster.example"
    resource_type = "aws_elasticache_cluster"
    mapper.map_resource(
        resource_name, resource_type, {"values": {}}, builder, context=None
    )
    assert builder.nodes == {}, "Should not create nodes if 'values' is empty"


def test_creates_dbms_and_database_with_defaults_and_relationship(mapper, builder):
    resource_name = "aws_elasticache_cluster.cache"
    resource_type = "aws_elasticache_cluster"
    # Without context: metadata == values; no engine/port -> default 6379
    resource_data = {
        "provider_name": "registry.terraform.io/hashicorp/aws",
        "values": {"cluster_id": "cache1"},
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

    # Database.name from cluster_id
    assert database.properties.get("name") == "cache1"

    # HostedOn relationship from Database to DBMS
    host_reqs = [r for r in database.requirements if r["name"] == "host"]
    assert host_reqs, "Missing 'host' requirement on Database"
    assert host_reqs[0]["relationship"] == "HostedOn"
    assert host_reqs[0]["target"] == dbms_key

    # Added capabilities
    assert "host" in dbms.capabilities
    assert "database_endpoint" in database.capabilities


def test_engine_and_port_from_context(mapper, builder):
    resource_name = "aws_elasticache_cluster.mem"
    resource_type = "aws_elasticache_cluster"
    resource_data = {"provider_name": "aws"}

    # Valid port provided in values; engine/engine_version in metadata
    prop_values = {"cluster_id": "mc1", "port": 11222}
    md_values = {"engine": "memcached", "engine_version": "1.6.21"}
    ctx = FakeContext(props=prop_values, meta=md_values)

    mapper.map_resource(
        resource_name, resource_type, resource_data, builder, context=ctx
    )

    dbms_key = next(name for name in builder.nodes if name.endswith("_dbms"))
    db_key = next(name for name in builder.nodes if name.endswith("_database"))
    dbms = builder.nodes[dbms_key]
    database = builder.nodes[db_key]

    # Ports respect the explicit value
    assert dbms.properties["port"] == 11222
    assert database.properties["port"] == 11222

    # Standardized engine metadata
    assert dbms.metadata.get("aws_engine") == "memcached"
    # In the cluster mapper the standardized alias is in 'engine_type'
    assert dbms.metadata.get("engine_type") == "Memcached"
    assert dbms.metadata.get("aws_engine_version") == "1.6.21"

    # Propagated provider
    assert dbms.metadata.get("aws_provider") == "aws"
    assert database.metadata.get("aws_provider") == "aws"

    # Database.name from cluster_id
    assert database.properties.get("name") == "mc1"


def test_invalid_port_falls_back_to_engine_default(mapper, builder):
    resource_name = "aws_elasticache_cluster.redis_bad_port"
    resource_type = "aws_elasticache_cluster"
    resource_data = {"provider_name": "aws"}

    # Invalid port; engine=redis -> default 6379
    prop_values = {"cluster_id": "redisX", "port": 70000}
    md_values = {"engine": "redis"}
    ctx = FakeContext(props=prop_values, meta=md_values)

    mapper.map_resource(
        resource_name, resource_type, resource_data, builder, context=ctx
    )

    dbms_key = next(name for name in builder.nodes if name.endswith("_dbms"))
    db_key = next(name for name in builder.nodes if name.endswith("_database"))
    dbms = builder.nodes[dbms_key]
    database = builder.nodes[db_key]

    assert dbms.properties["port"] == 6379
    assert database.properties["port"] == 6379
    # The mapper annotates the use of default in the nodes' metadata
    assert dbms.metadata.get("aws_default_port") == 6379
    assert database.metadata.get("aws_default_port") == 6379


def test_dependencies_are_added_on_dbms_only(mapper, builder):
    resource_name = "aws_elasticache_cluster.with_refs"
    resource_type = "aws_elasticache_cluster"
    resource_data = {"provider_name": "aws"}

    prop_values = {"cluster_id": "dep1"}
    md_values = {"engine": "redis"}
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


def test_metadata_flags_on_database(mapper, builder):
    resource_name = "aws_elasticache_cluster.flags"
    resource_type = "aws_elasticache_cluster"
    resource_data = {"provider_name": "aws"}

    prop_values = {"cluster_id": "flags1"}
    md_values = {
        "engine": "redis",
        "transit_encryption_enabled": True,
        "at_rest_encryption_enabled": True,
        "tags": {"Env": "test"},
    }
    ctx = FakeContext(props=prop_values, meta=md_values)

    mapper.map_resource(
        resource_name, resource_type, resource_data, builder, context=ctx
    )

    db_key = next(name for name in builder.nodes if name.endswith("_database"))
    database = builder.nodes[db_key]

    assert database.metadata.get("aws_transit_encryption_enabled") is True
    assert database.metadata.get("aws_at_rest_encryption_enabled") is True
    assert database.metadata.get("aws_tags") == {"Env": "test"}
