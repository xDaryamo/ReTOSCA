from __future__ import annotations

from typing import Any

import pytest

from src.plugins.terraform.mappers.aws.aws_db_subnet_group import (
    AWSDBSubnetGroupMapper,
)


class FakePolicyBuilder:
    def __init__(self, builder: FakeBuilder, name: str, policy_type: str) -> None:
        self.builder = builder
        self.name = name
        self.policy_type = policy_type
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.targets: list[str] = []

    def with_property(self, key: str, value: Any) -> FakePolicyBuilder:
        self.properties[key] = value
        return self

    def with_metadata(self, md: dict[str, Any]) -> FakePolicyBuilder:
        self.metadata = md
        return self

    def with_targets(self, *targets: str) -> FakePolicyBuilder:
        self.targets.extend(list(targets))
        return self

    def and_service(self) -> FakeBuilder:
        # Persist on the parent builder
        self.builder.policies[self.name] = self
        return self.builder


class FakeBuilder:
    def __init__(self) -> None:
        self.policies: dict[str, FakePolicyBuilder] = {}

    def add_policy(self, name: str, policy_type: str) -> FakePolicyBuilder:
        return FakePolicyBuilder(self, name, policy_type)


class FakeContext:
    """
    Minimal TerraformMappingContext stand-in:
    - get_resolved_values(resource_data, kind: "property" | "metadata")
    - extract_terraform_references(resource_data)
    - parsed_data (dict)
    """

    def __init__(
        self,
        property_values: dict[str, Any],
        metadata_values: dict[str, Any],
        terraform_refs: list[tuple[str, str, str]],
        parsed_data: dict[str, Any],
    ) -> None:
        self._property_values = property_values
        self._metadata_values = metadata_values
        self._terraform_refs = terraform_refs
        self.parsed_data = parsed_data

    def get_resolved_values(
        self, _resource_data: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        if kind == "property":
            return self._property_values
        if kind == "metadata":
            return self._metadata_values
        return {}

    def extract_terraform_references(
        self, _resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        return self._terraform_refs


class TestCanMap:
    def test_true_for_db_subnet_group(self) -> None:
        mapper = AWSDBSubnetGroupMapper()
        assert mapper.can_map("aws_db_subnet_group", {}) is True

    def test_false_for_other(self) -> None:
        mapper = AWSDBSubnetGroupMapper()
        assert mapper.can_map("aws_s3_bucket", {}) is False


class TestGuards:
    def test_skips_when_no_values_without_context(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        mapper = AWSDBSubnetGroupMapper()
        b = FakeBuilder()

        resource_name = "aws_db_subnet_group.default"
        mapper.map_resource(
            resource_name,
            "aws_db_subnet_group",
            resource_data={},  # no "values"
            builder=b,  # type: ignore[arg-type]
            context=None,
        )

        assert b.policies == {}
        assert any("has no 'values' section" in rec.message for rec in caplog.records)


class TestHappyPathWithContext:
    def _make_context(self) -> FakeContext:
        # Resolved values for properties (used for policy properties such as AZ count)
        property_values = {
            "name": "db-subnets-1",
            "description": "Primary RDS subnets",
            # Length is used for 'availability_zones' property
            "subnet_ids": ["subnet-123", "subnet-456"],
        }

        # Fully resolved concrete values for metadata
        metadata_values = {
            "name": "db-subnets-1",
            "description": "Primary RDS subnets",
            "subnet_ids": ["subnet-123", "subnet-456"],
            "region": "eu-west-1",
            "vpc_id": "vpc-000111",
            "tags": {"env": "dev"},
            "tags_all": {"env": "dev", "owner": "team-net"},
            "arn": "arn:aws:rds:eu-west-1:111122223333:subgrp:db-subnets-1",
            "id": "sg-abc",
            "supported_network_types": ["IPV4"],
        }

        # Terraform references found on the resource (for subnet details extraction)
        terraform_refs = [
            ("subnet_ids", "aws_subnet.sub1", "DependsOn"),
            ("subnet_ids", "aws_subnet.sub2", "DependsOn"),
        ]

        # Parsed data with subnet resources + 1 DB instance referencing our subnet group
        parsed_data = {
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_subnet.sub1",
                            "type": "aws_subnet",
                            "values": {
                                "cidr_block": "10.0.1.0/24",
                                "availability_zone": "eu-west-1a",
                                "map_public_ip_on_launch": True,
                                "tags": {"Name": "sub1-name"},
                            },
                        },
                        {
                            "address": "aws_subnet.sub2",
                            "type": "aws_subnet",
                            "values": {
                                "cidr_block": "10.0.2.0/24",
                                "availability_zone": "eu-west-1b",
                                "map_public_ip_on_launch": False,
                                "tags": {"Name": "sub2-name"},
                            },
                        },
                        {
                            "address": "aws_db_instance.db1",
                            "type": "aws_db_instance",
                            "values": {
                                "db_subnet_group_name": "db-subnets-1",
                            },
                        },
                    ]
                }
            }
        }

        return FakeContext(
            property_values=property_values,
            metadata_values=metadata_values,
            terraform_refs=terraform_refs,
            parsed_data=parsed_data,
        )

    def test_creates_policy_with_metadata_properties_and_targets(self) -> None:
        mapper = AWSDBSubnetGroupMapper()
        b = FakeBuilder()
        ctx = self._make_context()

        resource_name = "aws_db_subnet_group.default"
        resource_data = {
            "address": resource_name,
            "type": "aws_db_subnet_group",
            "values": {
                # These are ignored when context is provided for metadata,
                # but property-resolved values are read from ctx.property_values
            },
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }

        mapper.map_resource(
            resource_name,
            "aws_db_subnet_group",
            resource_data,
            b,  # type: ignore[arg-type]
            context=ctx,  # type: ignore[arg-type]
        )

        # Policy name is derived by BaseResourceMapper.generate_tosca_node_name:
        # resource_type + "_" + clean_name
        policy_name = "aws_db_subnet_group_default"
        assert policy_name in b.policies

        policy = b.policies[policy_name]
        # Policy type
        assert policy.policy_type == "Placement"

        # Properties from property-resolved values
        assert policy.properties["placement_zone"] == "subnet_group"
        assert policy.properties["subnet_group_name"] == "db-subnets-1"
        assert policy.properties["availability_zones"] == 2

        # Metadata from metadata-resolved values
        md = policy.metadata
        assert md["original_resource_type"] == "aws_db_subnet_group"
        assert md["original_resource_name"] == "default"
        assert md["aws_component_type"] == "DBSubnetGroup"
        assert md["aws_db_subnet_group_name"] == "db-subnets-1"
        assert md["aws_region"] == "eu-west-1"
        assert md["aws_vpc_id"] == "vpc-000111"
        assert md["aws_tags"] == {"env": "dev"}
        assert md["aws_tags_all"]["owner"] == "team-net"
        assert md["aws_arn"].endswith(":db-subnets-1")
        assert md["aws_db_subnet_group_id"] == "sg-abc"
        assert md["aws_supported_network_types"] == ["IPV4"]

        # Subnet details extracted through references + parsed_data
        assert len(md["aws_subnet_details"]) == 2
        s1 = [
            s
            for s in md["aws_subnet_details"]
            if s["subnet_address"] == "aws_subnet.sub1"
        ][0]
        s2 = [
            s
            for s in md["aws_subnet_details"]
            if s["subnet_address"] == "aws_subnet.sub2"
        ][0]
        assert (
            s1["cidr_block"] == "10.0.1.0/24"
            and s1["availability_zone"] == "eu-west-1a"
            and s1["name"] == "sub1-name"
        )
        assert (
            s2["cidr_block"] == "10.0.2.0/24"
            and s2["availability_zone"] == "eu-west-1b"
            and s2["name"] == "sub2-name"
        )

        # Availability zones list derived from subnet_details
        assert sorted(md["aws_availability_zones"]) == ["eu-west-1a", "eu-west-1b"]

        # Targets include DBMS and Database nodes for the instance referencing
        # this subnet group
        assert set(policy.targets) == {
            "aws_db_instance_db1_dbms",
            "aws_db_instance_db1_database",
        }


class TestFallbackWithoutContext:
    def test_creates_policy_with_basic_metadata_and_no_targets(self) -> None:
        mapper = AWSDBSubnetGroupMapper()
        b = FakeBuilder()

        resource_name = "aws_db_subnet_group.default"
        resource_data = {
            "address": resource_name,
            "type": "aws_db_subnet_group",
            "values": {
                "name": "plain-subnets",
                "subnet_ids": ["subnet-a", "subnet-b"],
                "region": "eu-south-1",
                "vpc_id": "vpc-xyz",
                "tags": {"team": "db"},
                "arn": "arn:aws:rds:eu-south-1:111122223333:subgrp:plain-subnets",
            },
        }

        mapper.map_resource(
            resource_name,
            "aws_db_subnet_group",
            resource_data,
            b,  # type: ignore[arg-type]
            context=None,  # fallback to resource_data["values"]
        )

        policy_name = "aws_db_subnet_group_default"
        assert policy_name in b.policies

        policy = b.policies[policy_name]
        # Properties
        assert policy.properties["placement_zone"] == "subnet_group"
        assert policy.properties["subnet_group_name"] == "plain-subnets"
        assert policy.properties["availability_zones"] == 2

        # Metadata (no subnet_details/targets because no context)
        md = policy.metadata
        assert md["aws_db_subnet_group_name"] == "plain-subnets"
        assert md["aws_region"] == "eu-south-1"
        assert md["aws_vpc_id"] == "vpc-xyz"
        assert md["aws_tags"] == {"team": "db"}
        assert "aws_subnet_details" not in md
        assert policy.targets == []


class TestEdgeCasesWithContext:
    def test_no_references_or_parsed_data_yields_no_subnet_details(self) -> None:
        mapper = AWSDBSubnetGroupMapper()
        b = FakeBuilder()

        # Context without refs and without parsed_data
        ctx = FakeContext(
            property_values={"name": "sg-1", "subnet_ids": ["x"]},
            metadata_values={"name": "sg-1", "subnet_ids": ["x"]},
            terraform_refs=[],  # no subnet refs
            parsed_data={},  # no planned_values
        )

        resource_name = "aws_db_subnet_group.default"
        resource_data = {
            "address": resource_name,
            "type": "aws_db_subnet_group",
            "values": {},
        }

        mapper.map_resource(
            resource_name,
            "aws_db_subnet_group",
            resource_data,
            b,  # type: ignore[arg-type]
            context=ctx,  # type: ignore[arg-type]
        )

        policy = b.policies["aws_db_subnet_group_default"]
        assert "aws_subnet_details" not in policy.metadata
        assert "aws_availability_zones" not in policy.metadata
