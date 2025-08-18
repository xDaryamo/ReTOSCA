from pydantic import Field, model_validator

from .base_tosca import ToscaBase
from .operation_or_notification_assignment import (
    AssignmentType,
    OperationOrNotificationAssignment,
)
from .parameter_definition import ParameterDefinition


class InterfaceAssignment(ToscaBase):
    """
    Represents a TOSCA interface assignment.

    Used in node/relationship templates to assign inputs, operations,
    and notifications defined in an interface. The symbolic name of
    the interface is used as the key for these assignments.
    """

    inputs: dict[str, ParameterDefinition] | None = Field(
        default=None,
        description=(
            "Optional map of input parameter assignments for the interface, "
            "using ParameterDefinition."
        ),
    )
    operations: dict[str, OperationOrNotificationAssignment] | None = Field(
        default=None,
        description="Optional map of operation assignments for the interface.",
    )
    notifications: dict[str, OperationOrNotificationAssignment] | None = Field(
        default=None,
        description="Optional map of notification assignments for the interface.",
    )

    @model_validator(mode="after")
    def assign_types(self):
        if self.operations:
            for op in self.operations.values():
                op._assignment_type = AssignmentType.OPERATION
        if self.notifications:
            for notif in self.notifications.values():
                notif._assignment_type = AssignmentType.NOTIFICATION
        return self
