from typing import Any

from pydantic import Field, field_validator

from .base_tosca import ToscaBase


class CapabilityAssignment(ToscaBase):
    """
    Represents a TOSCA capability assignment.

    Used in node templates to assign values to properties and
    attributes of a capability defined in the node type.
    """

    properties: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map of property assignments for the capability " "definition."
        ),
    )

    attributes: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map of attribute assignments for the capability " "definition."
        ),
    )

    directives: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of directive values for processing instructions "
            "to orchestrators and tools. Valid values: 'internal', 'external'."
        ),
    )

    @field_validator("directives")
    def validate_directives(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            valid_directives = {"internal", "external"}
            for directive in v:
                if directive not in valid_directives:
                    raise ValueError(
                        f"Invalid directive '{directive}'. "
                        f"Valid values: {sorted(valid_directives)}"
                    )
        return v
