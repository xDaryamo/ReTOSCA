from typing import Any, Self

from pydantic import Field, NonNegativeInt, model_validator

from .base_tosca import ToscaBase


class RequirementAssignment(ToscaBase):
    """
    Represents a TOSCA requirement assignment.

    Used in node templates to provide assignments for the corresponding
    requirement definitions in the node type.
    """

    node: str | list[Any] | None = Field(
        default=None,
        description=(
            "Identifies the target node. Can be a symbolic node template "
            "name, a 2-entry list [name, index], or a node type name."
        ),
    )
    capability: str | None = Field(
        default=None,
        description=(
            "Identifies the target capability. Can be a capability name "
            "or capability type name."
        ),
    )
    relationship: str | dict[str, Any] | None = Field(
        default=None,
        description=(
            "Provides values for the relationship definition, or references a "
            "relationship template/type by name."
        ),
    )
    allocation: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Block of property assignments representing allocations for the "
            "target capability."
        ),
    )
    count: NonNegativeInt | None = Field(
        default=1,
        description=(
            "Non-negative integer setting the cardinality of the requirement "
            "assignment. Defaults to 1."
        ),
    )
    node_filter: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Node filter definition for selecting a compatible target node at runtime."
        ),
    )
    directives: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of directive values for processing instructions "
            "to orchestrators/tools."
        ),
    )
    optional: bool | None = Field(
        default=False,
        description=(
            "Indicates if this requirement assignment is optional. Defaults to "
            "False (must be satisfied)."
        ),
    )

    @model_validator(mode="after")
    def _validate_node_format(self) -> Self:
        if self.node is not None and isinstance(self.node, list):
            if len(self.node) != 2:
                raise ValueError(
                    "node as list must have exactly 2 elements [name, index]"
                )
        return self
