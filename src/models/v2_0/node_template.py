from typing import Any

from pydantic import Field, NonNegativeInt, field_validator

from .artifact_definition import ArtifactDefinition
from .base_tosca import ToscaBase
from .capability_assignment import CapabilityAssignment
from .interface_assignment import InterfaceAssignment
from .requirement_assignment import RequirementAssignment


class NodeTemplate(ToscaBase):
    """
    Represents a TOSCA node template instance.

    Defines one or more instances of a component of a given type. Allows
    overriding or augmenting properties, relationships, interfaces, and
    artifacts as defined by its node type (TOSCA 2.0 §7.2).
    """

    type: str = Field(
        ...,
        description="Required name of the node type this template is based on.",
    )
    directives: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of directive values for orchestration processing. "
            "Valid values: 'create', 'select', 'substitute'. Default is 'create'."
        ),
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description=("Optional map of property assignments for this node template."),
    )
    attributes: dict[str, Any] | None = Field(
        default=None,
        description=("Optional map of attribute assignments for this node template."),
    )
    requirements: list[dict[str, RequirementAssignment]] | None = Field(
        default=None,
        description=(
            "Optional list of requirement assignments. Each item is a dict "
            "whose key is the requirement name."
        ),
    )
    capabilities: dict[str, CapabilityAssignment] | None = Field(
        default=None,
        description=("Optional map of capability assignments for this node template."),
    )
    interfaces: dict[str, InterfaceAssignment] | None = Field(
        default=None,
        description=("Optional map of interface assignments for this node template."),
    )
    artifacts: dict[str, ArtifactDefinition] | None = Field(
        default=None,
        description=("Optional map of artifact definitions for this node template."),
    )
    count: NonNegativeInt | None = Field(
        default=None,
        description=(
            "Optional non-negative integer specifying how many node instances "
            "to create. Default is 1."
        ),
    )
    node_filter: Any | None = Field(
        default=None,
        description=(
            "Optional node filter definition, used only with the 'select' directive."
        ),
    )
    copy_from: str | None = Field(
        default=None,
        alias="copy",
        description=(
            "Optional symbolic name of another node template to copy all "
            "keynames and values from."
        ),
    )

    @field_validator("directives")
    def validate_directives(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            valid = {"create", "select", "substitute"}
            for directive in v:
                if directive not in valid:
                    raise ValueError(
                        f"Invalid directive '{directive}'. "
                        f"Valid values: {sorted(valid)}"
                    )
        return v
