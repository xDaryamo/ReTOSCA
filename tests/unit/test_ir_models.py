# tests/test_ir_models.py
"""
Unit tests for IR models (src/ir/models.py)
"""


import pytest
from pydantic import ValidationError

from src.ir.models import (
    Artifact,
    Capability,
    DeploymentModel,
    Node,
    NodeCategory,
    Operation,
    Relation,
    Requirement,
)

# ---------------------------------------------------------------------------
#                                FIXTURES
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_artifact() -> Artifact:
    """A reusable, valid Artifact."""
    return Artifact(
        name="deploy_script", type="Script", source="scripts/deploy.sh"
    )


@pytest.fixture
def sample_operation(sample_artifact: Artifact) -> Operation:
    """A valid Operation referencing the fixture Artifact."""
    return Operation(
        name="create",
        artifact_ref=sample_artifact.name,
        timeout_s=30,
        inputs={"var": "value"},
    )


@pytest.fixture
def server_node(
    sample_artifact: Artifact, sample_operation: Operation
) -> Node:
    """Minimal server Node of category SOFTWARE."""
    return Node(
        id="srv-1",
        type="MyAppServer",
        category=NodeCategory.SOFTWARE,
        properties={"version": "1.0"},
        artifacts=[sample_artifact],
        operations=[sample_operation],
    )


@pytest.fixture
def client_node() -> Node:
    """Simple client Node used for relationship tests."""
    return Node(id="cli-1", type="MyAppClient", category=NodeCategory.SOFTWARE)


# ---------------------------------------------------------------------------
#                                TESTS
# ---------------------------------------------------------------------------


def test_artifact_valid(sample_artifact: Artifact) -> None:
    """A valid Artifact builds without raising."""
    assert sample_artifact.source == "scripts/deploy.sh"


def test_operation_binds_existing_artifact(
    sample_operation: Operation, server_node: Node
) -> None:
    """Operation must reference an Artifact present in the Node."""
    assert sample_operation.name == "create"
    assert sample_operation.artifact_ref in {
        a.name for a in server_node.artifacts
    }


def test_deployment_model_valid(server_node: Node, client_node: Node) -> None:
    """
    DeploymentModel with two Nodes and
    one coherent Relation should validate.
    """
    rel = Relation(
        source=client_node.id,
        target=server_node.id,
        type="ConnectsTo",
        properties={"protocol": "http"},
    )
    model = DeploymentModel(
        nodes=[server_node, client_node], relationships=[rel]
    )
    # Pydantic returns exactly the objects we passed, counts match
    assert len(model.nodes) == 2
    assert model.relationships[0].type == "ConnectsTo"


@pytest.mark.parametrize(
    "invalid_name",
    ["invalid", "", "CREATE"],  # not in LifecycleOp enum (case-sensitive)
)
def test_operation_invalid_lifecycle_name_raises(
    invalid_name: str, sample_artifact: Artifact
) -> None:
    """Unsupported lifecycle operation names must trigger ValidationError."""
    with pytest.raises(ValidationError):
        Operation(name=invalid_name, artifact_ref=sample_artifact.name)


def test_artifact_empty_source_raises() -> None:
    """Empty 'source' must trigger ValidationError (covers _not_empty)."""
    with pytest.raises(ValidationError):
        Artifact(name="bad", source="")


def test_operation_points_to_unknown_artifact_raises(
    sample_operation: Operation,
) -> None:
    """
    If Operation references an Artifact not
    present in the Node, validation must fail.
    """
    with pytest.raises(ValidationError):
        Node(
            id="n1",
            type="Bad",
            operations=[sample_operation],  # Artifact is missing in .artifacts
        )


@pytest.mark.parametrize("cpu,mem", [(-1, 512), (2, 0)])
def test_compute_node_negative_specs_raise(cpu: int, mem: int) -> None:
    """cpu_count <= 0 or mem_size <= 0 should raise ValidationError."""
    with pytest.raises(ValidationError):
        Node(
            id="c1",
            type="VM",
            category=NodeCategory.COMPUTE,
            cpu_count=cpu,
            mem_size=mem,
        )


def test_requirement_count_bounds() -> None:
    """count_max smaller than count_min must raise."""
    with pytest.raises(ValidationError):
        Requirement(
            name="bad",
            capability="cap",
            count_min=3,
            count_max=2,
        )


def test_capability_count_bounds() -> None:
    """Capability with max < min must raise."""
    with pytest.raises(ValidationError):
        Capability(name="cap", type="Capa", count_min=5, count_max=1)


def test_relation_references_missing_node_raises(server_node: Node) -> None:
    """Relation pointing to non-existent nodes must fail model validation."""
    rel = Relation(source="notexists", target=server_node.id, type="Link")
    with pytest.raises(ValidationError):
        DeploymentModel(nodes=[server_node], relationships=[rel])