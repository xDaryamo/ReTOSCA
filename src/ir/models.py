"""
ir/models.py

Intermediate Representation (IR) models for round-trip engineering
between TOSCA 2.0 and various IaC technologies. Uses Pydantic v2
for schema validation, serialization to JSON, and ensuring data
consistency. Includes validators to enforce:
  - Standard lifecycle operation names
  - Cross-field consistency between operations and artifacts
  - Positive compute resource specifications
  - Referential integrity of relationships within the model
"""

from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional, Self, Set

from pydantic import BaseModel, Field, field_validator, model_validator


class Artifact(BaseModel):
    """
    Represents a deployment artifact such as a file, script, or image.

    Attributes:
        name: Unique identifier for the artifact within its node.
        type: Informational label (e.g., "Script", "File", "Image").
        source: File path or URL where the artifact content resides.
    """

    name: str = Field(..., description="Unique name of the artifact.")
    type: Optional[str] = Field(
        None, description="Type label for artifact (Script, File, etc.)."
    )
    source: str = Field(
        ..., description="Path or URL to the artifact content."
    )

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        """
        Ensure the source path is non-empty and points to an existing file.
        """
        if not v:
            raise ValueError("Artifact.source must not be empty.")
        if not Path(v).exists():
            raise ValueError(f"Artifact source file not found: {v}")
        return v


class Operation(BaseModel):
    """
    Represents a lifecycle operation for managing a node or relation.

    Attributes:
        name: Name of the operation (e.g., create, configure, start).
        artifact_ref: Optional reference to an Artifact name implementing
                      this operation.
    """

    # Allowed default operation names. Can extend if needed.
    ALLOWED_NAMES: ClassVar[Set[str]] = {
        "create",
        "configure",
        "start",
        "stop",
        "delete",
    }

    name: str = Field(..., description="Lifecycle operation name.")
    artifact_ref: Optional[str] = Field(
        None,
        description="Name of Artifact that implements this operation.",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Ensure operation name is one of the allowed defaults.
        """
        if v not in cls.ALLOWED_NAMES:
            allowed = ", ".join(sorted(cls.ALLOWED_NAMES))
            raise ValueError(
                f"Unsupported operation name '{v}'. Allowed names: {allowed}."
            )
        return v


class Node(BaseModel):
    """
    Core representation of a deployable component in the topology.

    Attributes:
        id: Optional unique identifier for referencing in relations.
        type: General category of the node (Compute, SoftwareComponent, etc.).
        properties: Arbitrary key-value settings for the node.
        artifacts: List of Artifact instances required by this node.
        operations: List of lifecycle operations for this node.
        description: Optional human-readable description.
        original_type: Source model type (e.g., full TOSCA type name).
        cpu_count: Optional compute-specific property (for Compute nodes).
        mem_size: Optional compute-specific property (for Compute nodes).
    """

    id: Optional[str] = Field(
        None, description="Unique identifier for node referencing."
    )
    type: str = Field(..., description="Node category or type label.")
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration key-value map for the node.",
    )
    artifacts: List[Artifact] = Field(
        default_factory=list,
        description="Artifacts (scripts, files) associated with the node.",
    )
    operations: List[Operation] = Field(
        default_factory=list,
        description="Lifecycle operations defined for this node.",
    )
    description: Optional[str] = Field(
        None, description="Optional explanatory text for the node."
    )
    original_type: Optional[str] = Field(
        None,
        description="Original TOSCA or source model type for traceability.",
    )
    cpu_count: Optional[int] = Field(
        None,
        description="CPU count (positive integer) for Compute nodes.",
    )
    mem_size: Optional[int] = Field(
        None,
        description="Memory size in MB or GB (positive integer) for Compute.",
    )

    @model_validator(mode="after")
    def validate_compute_resources(self) -> Self:
        """
        Enforce positive cpu_count and mem_size for Compute nodes.
        """
        if self.type.lower() == "compute":
            if self.cpu_count is not None and self.cpu_count <= 0:
                raise ValueError("Compute nodes require cpu_count > 0.")
            if self.mem_size is not None and self.mem_size <= 0:
                raise ValueError("Compute nodes require mem_size > 0.")
        return self

    @model_validator(mode="after")
    def validate_operation_artifacts(self) -> Self:
        """
        Ensure each Operation.artifact_ref refers to an existing Artifact name.
        """
        artifact_names = {a.name for a in self.artifacts}
        for op in self.operations:
            if op.artifact_ref and op.artifact_ref not in artifact_names:
                raise ValueError(
                    f"Operation '{op.name}' references unknown artifact '"
                    f"{op.artifact_ref}'."
                )
        return self


class ComputeNode(Node):
    """
    Specialized Node representing a compute resource (e.g., VM, server).
    """

    type: Literal["Compute"] = "Compute"


class SoftwareComponentNode(Node):
    """
    Specialized Node representing a software component.
    """

    type: Literal["SoftwareComponent"] = "SoftwareComponent"


class Relation(BaseModel):
    """
    Directed connection between two nodes, capturing dependencies.

    Attributes:
        source: Node.id of the relationship source.
        target: Node.id of the relationship target.
        type: Label describing the relation kind (DependsOn, HostedOn, etc.).
        properties: Additional parameters for the relation.
        description: Human-readable explanation.
        original_type: Source model relationship type for traceability.
    """

    source: Optional[str] = Field(
        None, description="ID of the source node in the relation."
    )
    target: Optional[str] = Field(
        None, description="ID of the target node in the relation."
    )
    type: str = Field(..., description="Type label for the connection.")
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value map for relation-specific settings.",
    )
    description: Optional[str] = Field(
        None, description="Optional explanation of the relationship."
    )
    original_type: Optional[str] = Field(
        None,
        description="Original TOSCA relationship type for round-trip.",
    )


class DeploymentModel(BaseModel):
    """
    Entire deployment topology: list of nodes and their relations.

    Attributes:
        nodes: Collection of Node instances in the model.
        relationships: Collection of Relation instances.
    """

    nodes: List[Node] = Field(
        default_factory=list,
        description="All components in the deployment model.",
    )
    relationships: List[Relation] = Field(
        default_factory=list,
        description="All directed dependencies between nodes.",
    )

    @model_validator(mode="after")
    def validate_relations_reference_nodes(self) -> Self:
        """
        Ensure that each relation's source/target refer to an existing Node.id.
        """
        valid_ids = {n.id for n in self.nodes if n.id}
        for rel in self.relationships:
            if rel.source and rel.source not in valid_ids:
                raise ValueError(
                    f"Relation source '{rel.source}'"
                    " not found among Node.id values."
                )
            if rel.target and rel.target not in valid_ids:
                raise ValueError(
                    f"Relation target '{rel.target}'"
                    " not found among Node.id values."
                )
        return self
