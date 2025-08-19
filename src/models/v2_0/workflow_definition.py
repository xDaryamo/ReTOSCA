from typing import Any, Self

from pydantic import Field, model_validator

from .base_tosca import ToscaBase
from .parameter_definition import ParameterDefinition


class WorkflowDefinition(ToscaBase):
    """
    Represents a TOSCA workflow definition for a service template.

    Defines an imperative workflow instance/configuration for a service,
    including steps, inputs, outputs, and implementation details (TOSCA 2.0 §7.5).
    """

    inputs: dict[str, ParameterDefinition] | None = Field(
        default=None,
        description=("Optional map of input parameter definitions for the workflow."),
    )
    precondition: Any | None = Field(
        default=None,
        description=(
            "Optional condition that must evaluate to true before the workflow "
            "can be processed."
        ),
    )
    steps: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map of imperative workflow step definitions. "
            "Mutually exclusive with 'implementation'."
        ),
    )
    implementation: Any | None = Field(
        default=None,
        description=(
            "Optional definition of an external workflow implementation. "
            "Mutually exclusive with 'steps'."
        ),
    )
    outputs: dict[str, ParameterDefinition] | None = Field(
        default=None,
        description=(
            "Optional map of attribute mappings specifying workflow outputs and "
            "their mappings to node or relationship attributes."
        ),
    )

    @model_validator(mode="after")
    def _validate_steps_vs_implementation(self) -> Self:
        if self.steps is not None and self.implementation is not None:
            raise ValueError("'steps' and 'implementation' are mutually exclusive")
        return self
