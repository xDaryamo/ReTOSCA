"""Unit tests for InterfaceAssignment class."""

from src.models.v2_0.interface_assignment import InterfaceAssignment
from src.models.v2_0.operation_or_notification_assignment import (
    AssignmentType,
    OperationOrNotificationAssignment,
)
from src.models.v2_0.parameter_definition import ParameterDefinition


class TestInterfaceAssignmentBasics:
    """Basic behavior and defaults."""

    def test_defaults(self):
        """inputs, operations, notifications are None by default."""
        ia = InterfaceAssignment()
        assert ia.inputs is None
        assert ia.operations is None
        assert ia.notifications is None

    def test_with_inputs(self):
        """Map of inputs with ParameterDefinition."""
        inputs = {
            "timeout": ParameterDefinition(type="integer", default=30),
            "url": ParameterDefinition(type="string", default="http://x"),
        }
        ia = InterfaceAssignment(inputs=inputs)
        assert "timeout" in ia.inputs
        assert ia.inputs["timeout"].default == 30
        assert ia.inputs["url"].type == "string"

    def test_with_empty_maps(self):
        """Empty maps are accepted."""
        ia = InterfaceAssignment(inputs={}, operations={}, notifications={})
        assert ia.inputs == {}
        assert ia.operations == {}
        assert ia.notifications == {}


class TestInterfaceAssignmentOperationsNotifications:
    """Ops/Notifs assignment typing and validation."""

    def test_operations_assignment_type_is_set(self):
        """_assignment_type must become OPERATION."""
        ops = {
            "create": OperationOrNotificationAssignment(implementation="create.sh"),
            "configure": OperationOrNotificationAssignment(implementation="cfg.sh"),
        }
        ia = InterfaceAssignment(operations=ops)
        # il validator 'after' deve impostare i tipi
        for op in ia.operations.values():
            assert op._assignment_type == AssignmentType.OPERATION

    def test_notifications_assignment_type_is_set(self):
        """_assignment_type must become NOTIFICATION."""
        notifs = {
            "on_success": OperationOrNotificationAssignment(
                implementation="notify_ok.sh"
            ),
            "on_failure": OperationOrNotificationAssignment(
                implementation="notify_ko.sh"
            ),
        }
        ia = InterfaceAssignment(notifications=notifs)
        for nf in ia.notifications.values():
            assert nf._assignment_type == AssignmentType.NOTIFICATION

    def test_wrong_pre_set_type_gets_overridden(self):
        """If preset incorrectly, the validator corrects it."""
        op = OperationOrNotificationAssignment(implementation="do.sh")
        op._assignment_type = AssignmentType.NOTIFICATION
        ia = InterfaceAssignment(operations={"do": op})
        assert ia.operations["do"]._assignment_type == AssignmentType.OPERATION

        nf = OperationOrNotificationAssignment(implementation="ev.sh")
        nf._assignment_type = AssignmentType.OPERATION
        ia2 = InterfaceAssignment(notifications={"ev": nf})
        assert ia2.notifications["ev"]._assignment_type == (AssignmentType.NOTIFICATION)


class TestInterfaceAssignmentSerialization:
    """Serialization checks."""

    def test_model_dump_exclude_none(self):
        """Dump excludes None and keeps valued fields."""
        ia = InterfaceAssignment(
            inputs={"retries": ParameterDefinition(type="integer", default=2)},
            operations={
                "start": OperationOrNotificationAssignment(implementation="start.sh")
            },
        )
        dumped = ia.model_dump(exclude_none=True)
        assert "inputs" in dumped
        assert "operations" in dumped
        assert "notifications" not in dumped
        # _assignment_type è privato, non va nel dump
        assert "_assignment_type" not in str(dumped)

    def test_empty_dump(self):
        """Dump with only defaults."""
        ia = InterfaceAssignment()
        dumped = ia.model_dump(exclude_none=True)
        assert dumped == {}


class TestInterfaceAssignmentInheritance:
    """ToscaBase fields inheritance."""

    def test_inheritance_fields(self):
        """description and metadata work from ToscaBase."""
        ia = InterfaceAssignment(
            description="Interfaccia di test",
            metadata={"owner": "unit-test"},
        )
        assert ia.description == "Interfaccia di test"
        assert ia.metadata == {"owner": "unit-test"}


class TestInterfaceAssignmentEdgeCases:
    """Edge cases."""

    def test_unicode(self):
        """Unicode support in description and impl."""
        ia = InterfaceAssignment(
            operations={
                "deploy": OperationOrNotificationAssignment(
                    implementation="deploy_🚀.sh"
                )
            },
            description="Interfaccia ✨",
        )
        assert "🚀" in ia.operations["deploy"].implementation
        assert "✨" in ia.description
