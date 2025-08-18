from typing import Any

from pydantic import Field, model_validator

from .base_tosca import ToscaBase


class ParameterDefinition(ToscaBase):
    """
    Represents a TOSCA parameter definition (input or output).

    All keynames are available for both input and output parameters, but
    their usage differs by context.
    """

    type: str | None = Field(
        default=None,
        description="Optional data type of the parameter. Recommended for clarity.",
    )
    value: Any | None = Field(
        default=None,
        description=(
            "Assigns a value compatible with the parameter type. Relevant "
            "for output parameters; mutually exclusive with mapping."
        ),
    )
    mapping: Any | None = Field(
        default=None,
        description=(
            "Specifies a mapping for a node or relationship attribute. "
            "Relevant for input parameters; mutually exclusive with value."
        ),
    )
    required: bool | None = Field(
        default=True,
        description=(
            "Whether the parameter is required. Defaults to True if not " "specified."
        ),
    )
    default: Any | None = Field(
        default=None,
        description=(
            "Optional default value for the parameter if not provided "
            "by other means."
        ),
    )
    validation: Any | None = Field(
        default=None,
        description=(
            "Optional validation clause that must evaluate to True for the "
            "parameter value to be valid."
        ),
    )
    key_schema: Any | None = Field(
        default=None,
        description=(
            "Optional schema for keys if the parameter type is or derives "
            "from map. Defaults to string if not specified."
        ),
    )
    entry_schema: Any | None = Field(
        default=None,
        description=(
            "Optional schema for entries if the parameter type is or derives "
            "from list or map. Required in those cases."
        ),
    )

    @model_validator(mode="after")
    def _check_constraints(self) -> "ParameterDefinition":
        # value and mapping are mutually exclusive
        if self.value is not None and self.mapping is not None:
            raise ValueError(
                "'value' and 'mapping' are mutually exclusive and "
                "cannot both be set."
            )
        # your business rule: no default when required=False
        if self.required is False and self.default is not None:
            raise ValueError("default value should not be provided when required=False")
        return self
