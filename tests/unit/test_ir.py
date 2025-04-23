import pytest
from pydantic import ValidationError
from src.ir.models import (
    Artifact,
    Operation,
    ComputeNode,
    SoftwareComponentNode,
    Relation,
    DeploymentModel,
)


class TestArtifact:
    def test_artifact_valid(self, tmp_path):
        file = tmp_path / "script.sh"
        file.write_text("#!/bin/bash\necho Hello")
        artifact = Artifact(name="install_script", source=str(file))
        assert artifact.source.endswith("script.sh")

    def test_artifact_missing_source(self):
        with pytest.raises(ValidationError):
            Artifact(name="test", source="")


class TestOperation:
    def test_operation_valid(self):
        op = Operation(name="create", artifact_ref="install_script")
        assert op.name == "create"

    def test_operation_invalid_name(self):
        with pytest.raises(ValidationError):
            Operation(name="deploy")


class TestNode:
    def test_compute_node_valid(self):
        node = ComputeNode(id="vm1", cpu_count=2, mem_size=4096)
        assert node.type == "Compute"
        assert node.cpu_count == 2

    def test_compute_node_invalid_resources(self):
        with pytest.raises(ValidationError):
            ComputeNode(id="bad_vm", cpu_count=0, mem_size=1024)
        with pytest.raises(ValidationError):
            ComputeNode(id="bad_vm2", cpu_count=2, mem_size=-1)

    def test_software_node_valid(self):
        node = SoftwareComponentNode(id="web_app")
        assert node.type == "SoftwareComponent"

    def test_operation_artifact_ref_validation(self, tmp_path):
        script = tmp_path / "install.sh"
        script.write_text("echo Install")
        artifact = Artifact(name="script", source=str(script))
        operation = Operation(name="create", artifact_ref="nonexistent")
        with pytest.raises(ValidationError):
            SoftwareComponentNode(
                id="app", artifacts=[artifact], operations=[operation]
            )


class TestRelation:
    def test_relation_valid(self):
        rel = Relation(source="web", target="vm", type="HostedOn")
        assert rel.type == "HostedOn"


class TestDeploymentModel:
    def test_deployment_model_valid(self, tmp_path):
        f = tmp_path / "setup.sh"
        f.write_text("#!/bin/bash")
        art = Artifact(name="setup", source=str(f))
        op = Operation(name="create", artifact_ref="setup")
        compute = ComputeNode(id="vm1", cpu_count=2, mem_size=2048)
        software = SoftwareComponentNode(
            id="web", artifacts=[art], operations=[op]
        )
        rel = Relation(source="web", target="vm1", type="HostedOn")
        model = DeploymentModel(nodes=[compute, software], relationships=[rel])
        assert len(model.nodes) == 2
        assert model.relationships[0].type == "HostedOn"

    def test_invalid_relation_reference(self):
        compute = ComputeNode(id="vm1", cpu_count=2, mem_size=2048)
        rel = Relation(source="web", target="vm1", type="HostedOn")
        with pytest.raises(ValidationError):
            DeploymentModel(nodes=[compute], relationships=[rel])
