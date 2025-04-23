from pathlib import Path

import pytest
from pydantic import ValidationError

from src.ir.models import (
    Artifact,
    ComputeNode,
    DeploymentModel,
    Operation,
    Relation,
    SoftwareComponentNode,
)


class TestArtifact:
    def test_artifact_valid(self, tmp_path: Path) -> None:
        file = tmp_path / "script.sh"
        file.write_text("#!/bin/bash\necho Hello")
        artifact = Artifact(
            name="install_script", type="Script", source=str(file)
        )
        assert artifact.source.endswith("script.sh")

    def test_artifact_missing_source(self) -> None:
        with pytest.raises(ValidationError):
            Artifact(name="test", type="Script", source="")


class TestOperation:
    def test_operation_valid(self) -> None:
        op = Operation(name="create", artifact_ref="install_script")
        assert op.name == "create"

    def test_operation_invalid_name(self) -> None:
        with pytest.raises(ValidationError):
            Operation(name="deploy", artifact_ref=None)


class TestNode:
    def test_compute_node_valid(self) -> None:
        node = ComputeNode(
            id="vm1",
            description="Compute node",
            cpu_count=2,
            mem_size=4096,
            original_type="tosca.nodes.Compute",
        )
        assert node.type == "Compute"
        assert node.cpu_count == 2

    def test_compute_node_invalid_resources(self) -> None:
        with pytest.raises(ValidationError):
            ComputeNode(
                id="bad_vm",
                description="Compute node",
                cpu_count=0,
                mem_size=1024,
                original_type="tosca.nodes.Compute",
            )
        with pytest.raises(ValidationError):
            ComputeNode(
                id="bad_vm2",
                description="Compute node",
                cpu_count=2,
                mem_size=-1,
                original_type="tosca.nodes.Compute",
            )

    def test_software_node_valid(self) -> None:
        node = SoftwareComponentNode(
            id="web_app",
            description="Software component",
            original_type="tosca.nodes.WebServer",
            cpu_count=None,
            mem_size=None,
        )
        assert node.type == "SoftwareComponent"

    def test_operation_artifact_ref_validation(self, tmp_path: Path) -> None:
        script = tmp_path / "install.sh"
        script.write_text("echo Install")
        artifact = Artifact(name="script", type="Script", source=str(script))
        operation = Operation(name="create", artifact_ref="nonexistent")
        with pytest.raises(ValidationError):
            SoftwareComponentNode(
                id="app",
                description="Software component",
                original_type="tosca.nodes.WebServer",
                artifacts=[artifact],
                operations=[operation],
                cpu_count=None,
                mem_size=None,
            )


class TestRelation:
    def test_relation_valid(self) -> None:
        rel = Relation(
            source="web",
            target="vm",
            type="HostedOn",
            description="Relation description",
            original_type="tosca.relationships.HostedOn",
        )
        assert rel.type == "HostedOn"


class TestDeploymentModel:
    def test_deployment_model_valid(self, tmp_path: Path) -> None:
        f = tmp_path / "setup.sh"
        f.write_text("#!/bin/bash")
        art = Artifact(name="setup", type="Script", source=str(f))
        op = Operation(name="create", artifact_ref="setup")
        compute = ComputeNode(
            id="vm1",
            cpu_count=2,
            mem_size=2048,
            description="Compute node",
            original_type="tosca.nodes.Compute",
        )
        software = SoftwareComponentNode(
            id="web",
            artifacts=[art],
            operations=[op],
            description="Web application",
            original_type="tosca.nodes.WebServer",
            cpu_count=None,
            mem_size=None,
        )
        rel = Relation(
            source="web",
            target="vm1",
            type="HostedOn",
            description="Software hosted on compute",
            original_type="tosca.relationships.HostedOn",
        )
        model = DeploymentModel(nodes=[compute, software], relationships=[rel])
        assert len(model.nodes) == 2
        assert model.relationships[0].type == "HostedOn"

    def test_invalid_relation_reference(self) -> None:
        compute = ComputeNode(
            id="vm1",
            cpu_count=2,
            mem_size=2048,
            description="Compute node",
            original_type="tosca.nodes.Compute",
        )
        rel = Relation(
            source="web",
            target="vm1",
            type="HostedOn",
            description="Invalid relation",
            original_type="tosca.relationships.HostedOn",
        )
        with pytest.raises(ValidationError):
            DeploymentModel(nodes=[compute], relationships=[rel])
