from __future__ import annotations

import json
from typing import Any

import pytest

from src.plugins.provisioning.terraform.mappers.aws.aws_iam_policy import (
    AWSIAMPolicyMapper,
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


class FakeArtifact:
    def __init__(
        self,
        node: FakeNode,
        name: str,
        artifact_type: str,
        content: str,
    ) -> None:
        self.node = node
        self.name = name
        self.artifact_type = artifact_type
        self.content = content

    def and_node(self) -> FakeNode:
        # Persist artifact on the parent node and return the node
        self.node.artifacts.append((self.name, self.artifact_type, self.content))
        return self.node


class FakeNode:
    def __init__(self, name: str, node_type: str) -> None:
        self.name = name
        self.node_type = node_type
        self.description: str | None = None
        self.properties: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}
        self.artifacts: list[tuple[str, str, str]] = []
        self.requirements: list[tuple[str, str | None, str | None]] = []

    # Chained APIs the mapper uses
    def with_description(self, desc: str) -> FakeNode:
        self.description = desc
        return self

    def with_property(self, name: str, value: Any) -> FakeNode:
        self.properties[name] = value
        return self

    def with_metadata(self, md: dict[str, Any]) -> FakeNode:
        self.metadata = md
        return self

    def add_artifact(self, name: str, artifact_type: str, content: str) -> FakeArtifact:
        return FakeArtifact(self, name, artifact_type, content)

    def add_requirement(self, name: str) -> FakeReq:
        return FakeReq(self, name)


class FakeBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, FakeNode] = {}

    def add_node(self, name: str, node_type: str) -> FakeNode:
        node = FakeNode(name, node_type)
        self.nodes[name] = node
        return node


# ------------------------------ Tests ------------------------------


class TestCanMap:
    def test_true_for_iam_policy(self) -> None:
        mapper = AWSIAMPolicyMapper()
        assert mapper.can_map("aws_iam_policy", {}) is True

    def test_false_for_other_types(self) -> None:
        mapper = AWSIAMPolicyMapper()
        assert mapper.can_map("aws_iam_role", {}) is False


class TestMapBasic:
    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        mapper = AWSIAMPolicyMapper()
        b = FakeBuilder()

        mapper.map_resource("aws_iam_policy.empty", "aws_iam_policy", {}, b)

        assert b.nodes == {}
        assert any("has no 'values' section" in r.message for r in caplog.records)


class TestMapHappyPath:
    def test_policy_as_json_string_creates_node_and_artifact(self) -> None:
        mapper = AWSIAMPolicyMapper()
        b = FakeBuilder()

        resource_name = "aws_iam_policy.my_policy"
        values = {
            "name": "MyPolicy",
            "description": "Allow listing buckets",
            "path": "/service/",
            "name_prefix": "pref-",
            "policy": json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": ["s3:ListAllMyBuckets"],
                            "Resource": "*",
                        }
                    ],
                }
            ),
            "arn": "arn:aws:iam::123456789012:policy/MyPolicy",
            "policy_id": "PABCDEFGHIJK",
            "attachment_count": 2,
            "tags": {"env": "dev"},
            "tags_all": {"env": "dev", "team": "platform"},
            "region": "eu-west-1",
        }
        resource_data = {
            "values": values,
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }

        mapper.map_resource(resource_name, "aws_iam_policy", resource_data, b)

        # Node presence and type
        assert "aws_iam_policy_my_policy" in b.nodes
        node = b.nodes["aws_iam_policy_my_policy"]
        assert node.node_type == "SoftwareComponent"

        # Description and basic property set by the mapper
        assert (
            node.description == "AWS IAM Policy defining permissions and access rules"
        )
        assert node.properties.get("component_version") == "1.0"

        # Metadata checks
        md = node.metadata
        assert md["original_resource_type"] == "aws_iam_policy"
        assert md["original_resource_name"] == "my_policy"
        assert md["aws_component_type"] == "IAMPolicy"
        assert (
            md["description"] == "AWS IAM Policy defining permissions and access rules"
        )
        assert md["terraform_provider"] == "registry.terraform.io/hashicorp/aws"
        assert md["aws_policy_name"] == "MyPolicy"
        assert md["aws_policy_description"] == "Allow listing buckets"
        assert md["aws_policy_path"] == "/service/"
        assert md["aws_policy_name_prefix"] == "pref-"
        assert md["aws_arn"].endswith(":policy/MyPolicy")
        assert md["aws_policy_id"] == "PABCDEFGHIJK"
        assert md["aws_attachment_count"] == 2
        assert md["aws_tags"] == {"env": "dev"}
        assert md["aws_tags_all"]["team"] == "platform"
        assert md["aws_region"] == "eu-west-1"

        # Policy document stored as structured dict in metadata
        meta_doc = md["aws_policy_document"]
        assert isinstance(meta_doc, dict)
        assert meta_doc["Statement"][0]["Action"][0] == "s3:ListAllMyBuckets"

        # Artifact added with pretty-printed JSON
        assert len(node.artifacts) == 1
        art_name, art_type, art_content = node.artifacts[0]
        assert art_name == "policy_document"
        assert art_type == "application/json"
        parsed_art = json.loads(art_content)
        assert parsed_art["Version"] == "2012-10-17"
        assert parsed_art["Statement"][0]["Effect"] == "Allow"

        # No requirements are expected from _add_dependencies (for now)
        assert node.requirements == []

    def test_policy_as_dict_creates_node_and_artifact(self) -> None:
        mapper = AWSIAMPolicyMapper()
        b = FakeBuilder()

        policy_dict = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "Stmt1",
                    "Effect": "Allow",
                    "Action": ["s3:GetObject"],
                    "Resource": ["arn:aws:s3:::my-bucket/*"],
                }
            ],
        }

        resource_name = "aws_iam_policy.data_access"
        values = {
            "name": "DataAccessPolicy",
            "policy": policy_dict,
        }
        resource_data = {"values": values}

        mapper.map_resource(resource_name, "aws_iam_policy", resource_data, b)

        assert "aws_iam_policy_data_access" in b.nodes
        node = b.nodes["aws_iam_policy_data_access"]
        assert node.node_type == "SoftwareComponent"

        md = node.metadata
        # Metadata document should be the same dict content
        assert md["aws_policy_document"]["Statement"][0]["Sid"] == "Stmt1"

        # Artifact exists and is valid JSON mirroring the dict
        assert len(node.artifacts) == 1
        _, _, art_content = node.artifacts[0]
        parsed = json.loads(art_content)
        assert parsed["Statement"][0]["Action"] == ["s3:GetObject"]
        assert parsed["Statement"][0]["Resource"][0].endswith("my-bucket/*")


class TestEdgeCases:
    def test_policy_with_invalid_json_string_falls_back_to_str(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        mapper = AWSIAMPolicyMapper()
        b = FakeBuilder()

        values = {
            "name": "Broken",
            "policy": "{not-json: true",  # malformed JSON
        }
        resource_data = {"values": values}

        mapper.map_resource("aws_iam_policy.broken", "aws_iam_policy", resource_data, b)

        node = b.nodes["aws_iam_policy_broken"]
        md = node.metadata
        # Stored under a dict wrapper from _format_policy_for_yaml_literal
        assert "policy" in md["aws_policy_document"]
        assert "not-json" in md["aws_policy_document"]["policy"]

        # Artifact content should be the raw string (since parsing failed)
        assert len(node.artifacts) == 1
        _, _, art_content = node.artifacts[0]
        assert "{not-json: true" in art_content
        assert any("Failed to format policy" in r.message for r in caplog.records)

    def test_minimal_values_only_policy(self) -> None:
        mapper = AWSIAMPolicyMapper()
        b = FakeBuilder()

        # Only required bits: a policy JSON and no other fields
        policy = {"Version": "2012-10-17", "Statement": []}
        resource_data = {"values": {"policy": policy}}

        mapper.map_resource("aws_iam_policy.min", "aws_iam_policy", resource_data, b)

        node = b.nodes["aws_iam_policy_min"]
        assert node.node_type == "SoftwareComponent"

        # Has artifact and metadata document
        assert len(node.artifacts) == 1
        md = node.metadata
        assert md["aws_policy_document"]["Version"] == "2012-10-17"
