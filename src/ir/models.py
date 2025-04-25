from __future__ import annotations

"""
models.py – Intermediate Representation (IR)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Production‑grade, information‑rich model that bridges TOSCA 2.0, Puccini Clout
and heterogeneous IaC back‑ends.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SCHEMA_VERSION: str = "0.2.0"

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class LifecycleOp(str, Enum):
    """Canonical lifecycle operations (aligned to TOSCA Simple profile)."""

    CREATE = "create"
    CONFIGURE = "configure"
    START = "start"
    STOP = "stop"
    DELETE = "delete"


class NodeCategory(str, Enum):
    """High‑level node taxonomy used for mapping and UI grouping."""

    COMPUTE = "Compute"
    NETWORK = "Network"
    STORAGE = "Storage"
    SOFTWARE = "SoftwareComponent"
    DATABASE = "Database"


# ---------------------------------------------------------------------------
# Core building blocks
# ---------------------------------------------------------------------------


class Artifact(BaseModel):
    """Deployment or implementation artifact associated to a Node/Operation."""

    name: str = Field(
        ...,
        description="Unique artifact identifier (local to the owning Node).",
    )
    type: Optional[str] = Field(
        None,
        description="Artifact classification (e.g. *Script*, *DockerImage*).",
    )
    source: str = Field(
        ..., description="Absolute or relative URI/path to content."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary key/value metadata."
    )

    model_config = ConfigDict(extra="forbid")

    # ----- validators --------------------------------------------------------
    @field_validator("source")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Artifact.source must not be empty")
        return v


class Operation(BaseModel):
    """Lifecycle operation mapped to an artifact and optional timeout."""

    name: str = Field(
        ..., description="Operation name – must map to `LifecycleOp` literal."
    )
    artifact_ref: Optional[str] = Field(
        None, description="`Artifact.name` implementing this operation."
    )
    timeout_s: Optional[int] = Field(
        None, ge=1, description="Execution timeout in seconds (optional)."
    )
    inputs: Dict[str, Any] = Field(
        default_factory=dict, description="Input parameters to the operation."
    )

    model_config = ConfigDict(extra="forbid")

    # ----- validators --------------------------------------------------------
    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        allowed = {op.value for op in LifecycleOp}
        if v not in allowed:
            raise ValueError(
                f"Unsupported operation '{v}'. "
                f"Allowed: {', '.join(sorted(allowed))}."
            )
        return v


class Requirement(BaseModel):
    """Declarative dependency pointing to a target capability."""

    name: str = Field(
        ..., description="Logical requirement name within the node."
    )
    capability: str = Field(
        ..., description="Capability type expected on the target node."
    )
    relationship: Optional[str] = Field(
        None,
        description="Relationship type used when binding this requirement.",
    )
    target_node: Optional[str] = Field(
        None,
        description="ID of the pre‑selected target Node (if already bound).",
    )
    count_min: int = Field(
        1, ge=0, description="Minimum number of target nodes required."
    )
    count_max: int = Field(
        1,
        ge=-1,
        description="Maximum targets allowed; -1 signifies *unbounded*.",
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Map of filter constraints for matching.",
    )
    description: Optional[str] = Field(
        None, description="Human‑readable note."
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _range_ok(self) -> Self:
        if self.count_max != -1 and self.count_max < self.count_min:
            raise ValueError("count_max cannot be smaller than count_min")
        return self


class Capability(BaseModel):
    """Feature exposed by a node; can be targeted by Requirements."""

    name: str = Field(
        ..., description="Capability name unique within the node."
    )
    type: str = Field(
        ..., description="Capability type (TOSCA QName or custom)."
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="Static configuration properties."
    )
    count_min: int = Field(
        0, ge=0, description="Minimum concurrent bindings supported."
    )
    count_max: int = Field(
        -1,
        ge=-1,
        description="Maximum bindings; -1 signifies *unbounded*.",
    )
    description: Optional[str] = Field(
        None, description="Human‑readable note."
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _range_ok(self) -> Self:
        if self.count_max != -1 and self.count_max < self.count_min:
            raise ValueError("count_max cannot be smaller than count_min")
        return self


class Attribute(BaseModel):
    """Runtime data exposed by a node (populated at run‑time)."""

    name: str = Field(..., description="Attribute key.")
    type: str = Field("string", description="Primitive or complex data type.")
    value: Any = Field(None, description="Current runtime value (may change).")
    default: Any = Field(
        None, description="Fallback if `value` is not yet known."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Extra info (units, source, etc.)."
    )

    model_config = ConfigDict(extra="forbid")


class Interface(BaseModel):
    """Collection of operations logically grouped under a name."""

    name: str = Field(..., description="Interface name (e.g. *Standard*).")
    operations: Dict[str, Operation] = Field(
        default_factory=dict, description="Mapping op‑name ➜ Operation object."
    )

    model_config = ConfigDict(extra="forbid")


class Policy(BaseModel):
    """Non‑functional constraint or behaviour attached to nodes/groups."""

    name: str = Field(..., description="Policy identifier.")
    type: str = Field(..., description="Policy type QName.")
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="Static configuration of the policy."
    )
    targets: List[str] = Field(
        default_factory=list,
        description="IDs of Nodes or Groups affected by this policy.",
    )

    model_config = ConfigDict(extra="forbid")


class WorkflowStep(BaseModel):
    target: str = Field(..., description="Node ID on which the step operates.")
    operation: str = Field(
        ..., description="Operation name or interface.op path."
    )
    on_success: List[str] = Field(
        default_factory=list, description="Next steps if this one succeeds."
    )
    on_failure: List[str] = Field(
        default_factory=list, description="Fallback steps if this one fails."
    )

    model_config = ConfigDict(extra="forbid")


class Workflow(BaseModel):
    name: str = Field(..., description="Workflow identifier.")
    steps: Dict[str, WorkflowStep] = Field(
        default_factory=dict, description="Mapping step‑name ➜ WorkflowStep."
    )

    model_config = ConfigDict(extra="forbid")


class Node(BaseModel):
    """Component (vertex) of the service topology graph."""

    id: str = Field(..., description="Unique node identifier within a model.")
    type: str = Field(..., description="Node type QName or IaC resource type.")
    category: Optional[NodeCategory] = Field(
        None, description="High‑level category hint (optional)."
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="Static configuration properties."
    )
    attributes: Dict[str, Attribute] = Field(
        default_factory=dict, description="Runtime attributes keyed by name."
    )
    artifacts: List[Artifact] = Field(
        default_factory=list, description="List of deployment artifacts."
    )
    operations: List[Operation] = Field(
        default_factory=list, description="Node‑level operations (flat list)."
    )
    interfaces: Dict[str, Interface] = Field(
        default_factory=dict, description="Interfaces grouped by name."
    )
    requirements: List[Requirement] = Field(
        default_factory=list, description="Outgoing requirements (unresolved)."
    )
    capabilities: Dict[str, Capability] = Field(
        default_factory=dict, description="Capabilities exposed to others."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Free‑form metadata for plugins/UI."
    )
    tags: Dict[str, str] = Field(
        default_factory=dict,
        description="Simple string tags for search/filter.",
    )
    description: Optional[str] = Field(
        None, description="Long‑form description."
    )
    original_type: Optional[str] = Field(
        None, description="Exact source DSL type for traceability."
    )
    cpu_count: Optional[int] = Field(
        None, ge=1, description="vCPU count (Compute category only)."
    )
    mem_size: Optional[int] = Field(
        None, ge=1, description="Memory in MB (Compute category only)."
    )

    model_config = ConfigDict(extra="forbid")

    # ----- validators --------------------------------------------------------
    @model_validator(mode="after")
    def _compute_resources(self) -> Self:
        if self.category == NodeCategory.COMPUTE:
            if self.cpu_count is not None and self.cpu_count <= 0:
                raise ValueError("Compute nodes require cpu_count > 0")
            if self.mem_size is not None and self.mem_size <= 0:
                raise ValueError("Compute nodes require mem_size > 0")
        return self

    @model_validator(mode="after")
    def _ops_ref_artifacts(self) -> Self:
        artifact_names = {a.name for a in self.artifacts}
        for op in self.operations:
            if op.artifact_ref and op.artifact_ref not in artifact_names:
                raise ValueError(
                    f"Operation '{op.name}' references "
                    f"unknown artifact '{op.artifact_ref}'."
                )
        return self


class Relation(BaseModel):
    """Directed edge in the topology graph (resolved requirement)."""

    source: str = Field(..., description="Source Node ID.")
    target: str = Field(..., description="Target Node ID.")
    type: str = Field(..., description="Relationship type QName.")
    capability: Optional[str] = Field(
        None, description="Capability name targeted on the target node."
    )
    interface: Optional[str] = Field(
        None, description="Relationship interface name (if any)."
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="Static relationship properties."
    )
    description: Optional[str] = Field(
        None, description="Human‑readable note."
    )
    original_type: Optional[str] = Field(
        None, description="Exact relationship type from source DSL."
    )

    model_config = ConfigDict(extra="forbid")


class DeploymentModel(BaseModel):
    """Root container representing an entire service topology."""

    schema_version: str = Field(
        SCHEMA_VERSION,
        frozen=True,
        description="IR schema semantic version for compatibility checks.",
    )
    nodes: List[Node] = Field(
        default_factory=list, description="All nodes (vertices) in the graph."
    )
    relationships: List[Relation] = Field(
        default_factory=list, description="All resolved edges in the graph."
    )
    inputs: Dict[str, Any] = Field(
        default_factory=dict, description="Top‑level inputs (template params)."
    )
    outputs: Dict[str, Any] = Field(
        default_factory=dict, description="Top‑level outputs exported."
    )
    policies: List[Policy] = Field(
        default_factory=list,
        description="Global policies applying to the model.",
    )
    groups: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Groups of Nodes (`group_name ➜ [Node IDs]`).",
    )
    workflows: Dict[str, Workflow] = Field(
        default_factory=dict,
        description="Named workflows attached to the model.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Free‑form metadata (tool version, etc.).",
    )

    model_config = ConfigDict(extra="forbid")

    # ----- validators --------------------------------------------------------
    @model_validator(mode="after")
    def _relations_refer_valid_nodes(self) -> Self:
        node_ids = {n.id for n in self.nodes}
        for rel in self.relationships:
            if rel.source not in node_ids:
                raise ValueError(
                    f"Relation source '{rel.source}' not found in nodes"
                )
            if rel.target not in node_ids:
                raise ValueError(
                    f"Relation target '{rel.target}' not found in nodes"
                )
        return self


__all__ = [
    "SCHEMA_VERSION",
    "LifecycleOp",
    "NodeCategory",
    "Artifact",
    "Operation",
    "Requirement",
    "Capability",
    "Attribute",
    "Interface",
    "Policy",
    "WorkflowStep",
    "Workflow",
    "Node",
    "Relation",
    "DeploymentModel",
]