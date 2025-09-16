import pytest

from src.plugins.provisioning.terraform.mappers.aws.aws_rds_cluster import (
    AWSRDSClusterMapper,
)


class _ReqBuilder:
    def __init__(self, node, name):
        self._node = node
        self._req = {
            "name": name,
            "target": None,
            "capability": None,
            "relationship": None,
            "rel_properties": {},
        }

    def to_node(self, target):
        self._req["target"] = target
        return self

    def to_capability(self, capability):
        self._req["capability"] = capability
        return self

    def with_relationship(self, rel):
        self._req["relationship"] = rel
        if (
            isinstance(rel, dict)
            and "properties" in rel
            and isinstance(rel["properties"], dict)
        ):
            self._req["rel_properties"].update(rel["properties"])
        return self

    def with_properties(self, **props):
        self._req["rel_properties"].update(props)
        return self

    def and_node(self):
        self._node.requirements.append(self._req)
        return self._node


class _Node:
    def __init__(self, name, node_type):
        self.name = name
        self.node_type = node_type
        self.properties = {}
        self.metadata = {}
        self.capabilities = {}
        self.requirements = []

    def add_requirement(self, name):
        return _ReqBuilder(self, name)

    def add_capability(self, name):
        self.capabilities.setdefault(name, {})

        class _CapProxy:
            def __init__(self, node, capname):
                self._node = node
                self._capname = capname

            def with_property(self, k, v):
                self._node.capabilities[self._capname][k] = v
                return self

            def and_node(self):
                return self._node

        return _CapProxy(self, name)

    def with_property(self, k, v):
        self.properties[k] = v
        return self

    def with_metadata(self, md):
        self.metadata.update(md or {})
        return self


class FakeBuilder:
    def __init__(self):
        self.nodes = {}

    def add_node(self, name: str, node_type: str):
        n = _Node(name, node_type)
        self.nodes[name] = n
        return n

    def get_node(self, name: str):
        return self.nodes.get(name)


class FakeVariableContext:
    def __init__(self, concrete_map=None, resolved_map=None):
        # map: (resource_address, prop) -> concrete value
        self._concrete_map = concrete_map or {}
        # map: (resource_address, prop) -> resolved value (e.g. {"$get_input": "x"})
        self._resolved_map = resolved_map or {}

    def get_concrete_value(self, resource_address, property_name):
        return self._concrete_map.get((resource_address, property_name))

    def resolve_property(self, resource_address, property_name, context="property"):
        return self._resolved_map.get((resource_address, property_name))


class FakeContext:
    def __init__(
        self,
        parsed_data=None,
        refs=None,
        prop_values=None,
        meta_values=None,
        variable_context=None,
    ):
        self.parsed_data = parsed_data or {}
        self._refs = refs or []
        self._prop_values = prop_values or {}
        self._meta_values = meta_values or {}
        self.variable_context = variable_context

    def get_resolved_values(self, _resource_data: dict, which: str = "property"):
        return self._prop_values if which == "property" else self._meta_values

    def extract_terraform_references(self, _resource_data: dict):
        # Returns list of tuples (prop_name, target_ref, relationship_type)
        return list(self._refs)


def make_resource(address="aws_rds_cluster.aurora_cluster", values=None):
    return {
        "address": address,
        "values": values or {},
        "provider_name": "registry.terraform.io/hashicorp/aws",
    }


@pytest.fixture
def mapper():
    return AWSRDSClusterMapper()


def test_can_map_true_false(mapper):
    assert mapper.can_map("aws_rds_cluster", {}) is True
    assert mapper.can_map("aws_db_instance", {}) is False


def test_map_creates_dbms_and_database_with_hostedon(monkeypatch, mapper):
    # Normalize the generated names
    from src.core.common import base_mapper as bm

    def _fake_gen(name, rtype=None):
        return "TOSCA_" + name.replace(".", "_")

    monkeypatch.setattr(
        bm.BaseResourceMapper, "generate_tosca_node_name", staticmethod(_fake_gen)
    )

    resource_name = "aws_rds_cluster.aurora_cluster"
    base_name = _fake_gen(resource_name, "aws_rds_cluster")
    dbms_name = f"{base_name}_dbms"
    db_name = f"{base_name}_database"

    values = {
        "port": 3306,
        "master_username": "admin",
        "master_password": "secret",
        "database_name": "appdb",
    }
    metadata_vals = {
        "engine": "aurora-mysql",
        "engine_version": "8.0.mysql_aurora",
        "db_subnet_group_name": "subnet-grp",
        "cluster_identifier": "aurora-cl",
        "tags": {"env": "dev"},
    }

    # a typical dependency from subnet group
    refs = [
        (
            "db_subnet_group_name",
            "aws_db_subnet_group.cluster_subnet_group",
            "DependsOn",
        )
    ]

    ctx = FakeContext(refs=refs, prop_values=values, meta_values=metadata_vals)
    b = FakeBuilder()
    res = make_resource(values=values)

    mapper.map_resource(resource_name, "aws_rds_cluster", res, b, ctx)

    # Node existence
    assert dbms_name in b.nodes and db_name in b.nodes

    dbms = b.get_node(dbms_name)
    db = b.get_node(db_name)

    # HostedOn relationship
    found = [
        r for r in db.requirements if r["name"] == "host" and r["target"] == dbms_name
    ]
    assert found and found[0]["relationship"] == "HostedOn"

    # DBMS / Database properties
    assert dbms.properties.get("port") == 3306
    assert db.properties.get("name") == "appdb"
    assert db.properties.get("user") == "admin"
    assert db.properties.get("password") == "secret"
    assert db.properties.get("port") == 3306

    # Main metadata
    assert dbms.metadata.get("aws_engine") == "aurora-mysql"
    assert dbms.metadata.get("engine_type") == "Aurora MySQL"
    assert dbms.metadata.get("aws_engine_version") == "8.0.mysql_aurora"
    assert dbms.metadata.get("aws_db_subnet_group_name") == "subnet-grp"
    assert dbms.metadata.get("aws_cluster_identifier") == "aurora-cl"
    assert b.get_node(db_name).metadata.get("aws_database_name") == "appdb"

    # Requirement from refs ends up on DBMS node
    dep = [r for r in dbms.requirements if r["name"] == "db_subnet_group_name"]
    assert dep and dep[0]["relationship"] == "DependsOn"


def test_default_ports_for_engine(monkeypatch, mapper):
    from src.core.common import base_mapper as bm

    def _fake_gen(name, rtype=None):
        return "TOSCA_" + name.replace(".", "_")

    monkeypatch.setattr(
        bm.BaseResourceMapper, "generate_tosca_node_name", staticmethod(_fake_gen)
    )

    resource_name = "aws_rds_cluster.pg_cluster"
    base_name = _fake_gen(resource_name, "aws_rds_cluster")
    dbms_name = f"{base_name}_dbms"
    db_name = f"{base_name}_database"

    # At least one base value, no explicit port
    values = {"master_username": "admin"}
    metadata_vals = {"engine": "aurora-postgresql"}

    ctx = FakeContext(prop_values=values, meta_values=metadata_vals)
    b = FakeBuilder()
    res = make_resource(address=resource_name, values=values)

    mapper.map_resource(resource_name, "aws_rds_cluster", res, b, ctx)

    dbms = b.get_node(dbms_name)
    db = b.get_node(db_name)

    # DBMS: default 5432 + default port metadata
    assert dbms.properties.get("port") == 5432
    assert dbms.metadata.get("aws_default_port") == 5432

    # Database: inherits default based on engine
    assert db.properties.get("port") == 5432
    assert db.metadata.get("aws_default_port") == 5432


def test_managed_master_password_skips_password(monkeypatch, mapper):
    from src.core.common import base_mapper as bm

    def _fake_gen(name, rtype=None):
        return "TOSCA_" + name.replace(".", "_")

    monkeypatch.setattr(
        bm.BaseResourceMapper, "generate_tosca_node_name", staticmethod(_fake_gen)
    )

    resource_name = "aws_rds_cluster.mmup"
    base_name = _fake_gen(resource_name, "aws_rds_cluster")
    dbms_name = f"{base_name}_dbms"
    db_name = f"{base_name}_database"

    values = {"master_password": "secret", "database_name": "x"}
    metadata_vals = {"engine": "aurora-mysql", "manage_master_user_password": True}

    ctx = FakeContext(prop_values=values, meta_values=metadata_vals)
    b = FakeBuilder()
    res = make_resource(address=resource_name, values=values)

    mapper.map_resource(resource_name, "aws_rds_cluster", res, b, ctx)

    db = b.get_node(db_name)
    dbms = b.get_node(dbms_name)

    # Should not set password on Database
    assert "password" not in db.properties
    # Metadata indicating managed password
    assert dbms.metadata.get("aws_managed_master_password") is True


def test_dependencies_added_on_dbms(monkeypatch, mapper):
    from src.core.common import base_mapper as bm

    def _fake_gen(name, rtype=None):
        return "TOSCA_" + name.replace(".", "_")

    monkeypatch.setattr(
        bm.BaseResourceMapper, "generate_tosca_node_name", staticmethod(_fake_gen)
    )

    resource_name = "aws_rds_cluster.deps"
    base_name = _fake_gen(resource_name, "aws_rds_cluster")
    dbms_name = f"{base_name}_dbms"

    values = {"database_name": "app"}
    metadata_vals = {"engine": "aurora"}

    refs = [
        ("db_subnet_group_name", "aws_db_subnet_group.sg", "DependsOn"),
        ("vpc_security_group_ids", "aws_security_group.db", "DependsOn"),
        ("kms_key_id", "aws_kms_key.db", "DependsOn"),
    ]

    ctx = FakeContext(prop_values=values, meta_values=metadata_vals, refs=refs)
    b = FakeBuilder()
    res = make_resource(address=resource_name, values=values)

    mapper.map_resource(resource_name, "aws_rds_cluster", res, b, ctx)

    dbms = b.get_node(dbms_name)
    names = {r["name"] for r in dbms.requirements}
    assert {"db_subnet_group_name", "vpc_security_group_ids", "kms_key_id"} <= names


def test_variable_backed_database_name(monkeypatch, mapper):
    from src.core.common import base_mapper as bm

    def _fake_gen(name, rtype=None):
        return "TOSCA_" + name.replace(".", "_")

    monkeypatch.setattr(
        bm.BaseResourceMapper, "generate_tosca_node_name", staticmethod(_fake_gen)
    )

    resource_name = "aws_rds_cluster.vardb"
    base_name = _fake_gen(resource_name, "aws_rds_cluster")
    db_name = f"{base_name}_database"

    values = {"database_name": "placeholder"}
    metadata_vals = {"engine": "aurora-mysql"}

    # The mapper will ask:
    # - resolve_property(..., "database_name", "property") -> {"$get_input": "db_name"}
    # - get_concrete_value(..., "database_name") -> "mydb"
    fvc = FakeVariableContext(
        concrete_map={(resource_name, "database_name"): "mydb"},
        resolved_map={(resource_name, "database_name"): {"$get_input": "db_name"}},
    )

    ctx = FakeContext(
        prop_values=values, meta_values=metadata_vals, variable_context=fvc
    )
    b = FakeBuilder()
    res = make_resource(address=resource_name, values=values)

    mapper.map_resource(resource_name, "aws_rds_cluster", res, b, ctx)

    db = b.get_node(db_name)
    # Property as get_input
    assert isinstance(db.properties.get("name"), dict)
    assert db.properties["name"].get("$get_input") == "db_name"
    # Metadata with concrete value
    assert db.metadata.get("aws_database_name") == "mydb"
