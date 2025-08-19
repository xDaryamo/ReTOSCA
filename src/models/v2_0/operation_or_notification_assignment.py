from enum import Enum
from typing import Any

from pydantic import Field, PrivateAttr, model_validator

from .base_tosca import ToscaBase
from .parameter_definition import ParameterDefinition


class AssignmentType(str, Enum):
    OPERATION = "operation"
    NOTIFICATION = "notification"


class OperationOrNotificationAssignment(ToscaBase):
    """
    Represents an assignment for operations or notifications.

    Used to assign input parameters, specify output mappings, and define or
    override the implementation for an operation/notification in a given
    context. The private field `_assignment_type` distinguishes between
    operation and notification and is not serialized.
    """

    implementation: Any | None = Field(
        default=None,
        description=(
            "Optional implementation definition. Overrides any implementation "
            "in the original definition."
        ),
    )
    inputs: dict[str, ParameterDefinition] | None = Field(
        default=None,
        description=(
            "Optional map of input parameter assignments (ParameterDefinition)."
        ),
    )
    outputs: dict[str, ParameterDefinition] | None = Field(
        default=None,
        description=(
            "Optional map of output parameter assignments (ParameterDefinition)."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Optional description for the assignment.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description=("Optional map for additional information about the assignment."),
    )

    # Non-serializable, used internally to distinguish the kind of assignment
    _assignment_type: AssignmentType | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate_and_set_assignment_type(self) -> "OperationOrNotificationAssignment":
        """
        Post-validation hook.

        If `_assignment_type` is set externally, validate it.
        Accepts an `AssignmentType` directly or attempts to coerce from a string.
        """

        if self._assignment_type is None:
            return self

        if isinstance(self._assignment_type, AssignmentType):
            return self

        try:
            self._assignment_type = AssignmentType(self._assignment_type)
        except Exception as err:
            valid = [e.value for e in AssignmentType]
            raise ValueError(
                f"Invalid assignment type '{self._assignment_type}'. "
                f"Valid values: {valid}"
            ) from err

        return self
