from __future__ import annotations

import logging
from typing import Any

import pytest

from src.plugins.terraform.mappers.aws.aws_db_instance import (
    AWSDBInstanceMapper,
)


class FakeRequirementBuilder:
    def __init__(
        self,
        parent: FakeNodeBuilder,
        sink: dict[str, Any],
        node_name: str,
        req_name: str,
    ) -> None:
        self._parent = parent
        self._sink = sink
        self._node_name = node_name
        self._req_name = req_name
        self._req: dict[str, Any] = {}

    def to_node(self, target: str) -> FakeRequirementBuilder:
        self._req["node"] = target
        return self

    def with_relationship(self, rel: str) -> FakeRequirementBuilder:
        self._req["relationship"] = rel
        return self

    def and_node(self) -> FakeNodeBuilder:
        self._sink[self._node_name]["requirements"].append({self._req_name: self._req})
        return self._parent


class FakeCapabilityBuilder:
    def __init__(
        self,
        parent: FakeNodeBuilder,
        sink: dict[str, Any],
        node_name: str,
        cap_name: str,
    ) -> None:
        self._parent = parent
        sink[node_name]["capabilities"].append(cap_name)

    def and_node(self) -> FakeNodeBuilder:
        return self._parent


class FakeNodeBuilder:
    def __init__(self, name: str, node_type: str, sink: dict[str, Any]) -> None:
        self.name = name
        self.node_type = node_type
        self._sink = sink
        sink[self.name] = {
            "type": node_type,
            "properties": {},
            "metadata": {},
            "capabilities": [],
            "requirements": [],
        }

    def with_property(self, name: str, value: Any) -> FakeNodeBuilder:
        self._sink[self.name]["properties"][name] = value
        return self

    def with_metadata(self, metadata: dict[str, Any]) -> FakeNodeBuilder:
        self._sink[self.name]["metadata"].update(metadata)
        return self

    def add_capability(self, cap_name: str) -> FakeCapabilityBuilder:
        return FakeCapabilityBuilder(self, self._sink, self.name, cap_name)

    def add_requirement(self, req_name: str) -> FakeRequirementBuilder:
        return FakeRequirementBuilder(self, self._sink, self.name, req_name)


class FakeBuilder:
    """Collects created nodes."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}

    def add_node(self, name: str, node_type: str) -> FakeNodeBuilder:
        return FakeNodeBuilder(name, node_type, self.nodes)


class TestCanMap:
    def test_can_map_true_for_db_instance(self) -> None:
        m = AWSDBInstanceMapper()
        assert m.can_map("aws_db_instance", {"values": {}}) is True

    def test_can_map_false_for_other(self) -> None:
        m = AWSDBInstanceMapper()
        assert m.can_map("aws_instance", {"values": {}}) is False


class TestMapResourceHappyPath:
    def test_creates_dbms_and_database_with_relationship(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        m = AWSDBInstanceMapper()
        b = FakeBuilder()

        res_name = "aws_db_instance.main[0]"
        res_type = "aws_db_instance"
        data = {
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "values": {
                "engine": "mysql",
                "engine_version": "8.0.36",
                "instance_class": "db.t3.micro",
                "license_model": "general-public-license",
                "multi_az": True,
                "allocated_storage": 20,
                "storage_type": "gp3",
                "storage_encrypted": True,
                "backup_retention_period": 7,
                "backup_window": "04:00-05:00",
                "maintenance_window": "Sun:05:00-Sun:06:00",
                "monitoring_interval": 60,
                "performance_insights_enabled": True,
                "port": 3306,
                "db_name": "appdb",
                "username": "admin",
                "password": "secret",
                "vpc_security_group_ids": ["sg-1", "sg-2"],
                "db_subnet_group_name": "default",
                "availability_zone": "eu-west-1a",
                "tags": {"env": "prod"},
                "identifier": "rds-main-0",
                "publicly_accessible": False,
                "iam_database_authentication_enabled": False,
            },
        }

        m.map_resource(res_name, res_type, data, b)

        dbms_key = "aws_db_instance_main_0_dbms"
        db_key = "aws_db_instance_main_0_database"
        assert dbms_key in b.nodes
        assert db_key in b.nodes

        dbms = b.nodes[dbms_key]
        db = b.nodes[db_key]

        # Types
        assert dbms["type"] == "DBMS"
        assert db["type"] == "Database"

        # Capabilities
        assert "host" in dbms["capabilities"]
        assert "database_endpoint" in db["capabilities"]

        # DBMS properties and metadata
        assert dbms["properties"]["port"] == 3306
        md1 = dbms["metadata"]
        assert md1["original_resource_type"] == "aws_db_instance"
        assert md1["original_resource_name"] == "main[0]"
        assert md1["aws_provider"].startswith("registry.terraform.io")
        assert md1["aws_engine"] == "mysql"
        assert md1["engine_type"] == "MySQL"
        assert md1["aws_engine_version"] == "8.0.36"
        assert md1["aws_instance_class"] == "db.t3.micro"
        assert md1["aws_multi_az"] is True
        assert md1["aws_allocated_storage"] == 20
        assert md1["aws_storage_type"] == "gp3"
        assert md1["aws_storage_encrypted"] is True
        assert md1["aws_backup_retention_period"] == 7
        assert md1["aws_backup_window"] == "04:00-05:00"
        assert md1["aws_maintenance_window"] == "Sun:05:00-Sun:06:00"
        assert md1["aws_monitoring_interval"] == 60
        assert md1["aws_performance_insights_enabled"] is True
        assert md1["aws_vpc_security_group_ids"] == ["sg-1", "sg-2"]
        assert md1["aws_db_subnet_group_name"] == "default"
        assert md1["aws_availability_zone"] == "eu-west-1a"
        assert md1["aws_tags"] == {"env": "prod"}

        # DBMS sensitive property written (since not managed password)
        assert dbms["properties"]["root_password"] == "secret"

        # Database properties and metadata
        props = db["properties"]
        assert props["name"] == "appdb"
        assert props["port"] == 3306
        assert props["user"] == "admin"
        assert props["password"] == "secret"  # not managed

        md2 = db["metadata"]
        assert md2["original_resource_type"] == "aws_db_instance"
        assert md2["original_resource_name"] == "main[0]"
        assert md2["aws_provider"].startswith("registry.terraform.io")
        assert md2["aws_identifier"] == "rds-main-0"
        assert md2["aws_publicly_accessible"] is False
        assert md2["aws_iam_database_authentication_enabled"] is False
        assert md2["aws_tags"] == {"env": "prod"}

        # Relationship: Database 'host' -> DBMS with HostedOn
        reqs = db["requirements"]
        assert len(reqs) == 1
        host_req = reqs[0]["host"]
        assert host_req["node"] == dbms_key
        assert host_req["relationship"] == "HostedOn"

        # Logging
        assert any("Mapping DB Instance resource" in r.message for r in caplog.records)


class TestManagedPasswordAndDefaults:
    def test_managed_password_avoids_setting_passwords(self) -> None:
        m = AWSDBInstanceMapper()
        b = FakeBuilder()
        data = {
            "values": {
                "engine": "mysql",
                "manage_master_user_password": True,
                "password": "should-not-be-used",
                "username": "admin",
                "db_name": "db",
            }
        }
        m.map_resource("aws_db_instance.managed", "aws_db_instance", data, b)

        dbms = b.nodes["aws_db_instance_managed_dbms"]
        db = b.nodes["aws_db_instance_managed_database"]

        # DBMS metadata flag and no root_password property
        assert dbms["metadata"]["aws_managed_master_password"] is True
        assert "root_password" not in dbms["properties"]

        # Database should not contain password
        assert "password" not in db["properties"]

    def test_default_ports_applied_for_known_engine(self) -> None:
        m = AWSDBInstanceMapper()
        b = FakeBuilder()
        data = {"values": {"engine": "postgres"}}
        m.map_resource("aws_db_instance.pg", "aws_db_instance", data, b)

        dbms = b.nodes["aws_db_instance_pg_dbms"]
        db = b.nodes["aws_db_instance_pg_database"]

        # Known engine -> DBMS and Database default to 5432
        assert dbms["properties"]["port"] == 5432
        assert db["properties"]["port"] == 5432
        assert dbms["metadata"]["aws_default_port"] == 5432
        assert db["metadata"]["aws_default_port"] == 5432
        assert dbms["metadata"]["engine_type"] == "PostgreSQL"

    def test_unknown_engine_db_defaults_to_3306(self) -> None:
        m = AWSDBInstanceMapper()
        b = FakeBuilder()
        data = {"values": {"engine": "unknown"}}
        m.map_resource("aws_db_instance.unk", "aws_db_instance", data, b)

        dbms = b.nodes["aws_db_instance_unk_dbms"]
        db = b.nodes["aws_db_instance_unk_database"]

        # DBMS has no port (engine not in defaults)
        assert "port" not in dbms["properties"]
        # Database falls back to 3306
        assert db["properties"]["port"] == 3306
        assert db["metadata"]["aws_default_port"] == 3306


class TestNoValues:
    def test_no_values_skips_mapping(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSDBInstanceMapper()
        b = FakeBuilder()
        m.map_resource("aws_db_instance.empty", "aws_db_instance", {}, b)

        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)
