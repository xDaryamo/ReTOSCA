"""Unit tests for OperationOrNotificationAssignment class."""

import pytest

from src.models.v2_0.operation_or_notification_assignment import (
    AssignmentType,
    OperationOrNotificationAssignment,
)
from src.models.v2_0.parameter_definition import ParameterDefinition


class TestOperationOrNotificationAssignmentBasics:
    """Basic behavior and defaults."""

    def test_defaults(self):
        """All optional fields are None by default."""
        ass = OperationOrNotificationAssignment()
        assert ass.implementation is None
        assert ass.inputs is None
        assert ass.outputs is None
        assert ass.description is None
        assert ass.metadata is None
        assert ass._assignment_type is None

    def test_with_basic_fields(self):
        """Main fields set."""
        ass = OperationOrNotificationAssignment(
            implementation="deploy.sh",
            description="Deploy operation",
            metadata={"version": "1.0"},
        )
        assert ass.implementation == "deploy.sh"
        assert ass.description == "Deploy operation"
        assert ass.metadata == {"version": "1.0"}


class TestOperationOrNotificationAssignmentInputsOutputs:
    """Inputs and outputs parameter definition."""

    def test_with_inputs(self):
        """inputs as dict of ParameterDefinition."""
        inputs = {
            "cfg": ParameterDefinition(type="string", default="conf.yml"),
            "timeout": ParameterDefinition(type="integer", default=60),
        }
        ass = OperationOrNotificationAssignment(inputs=inputs)
        assert "cfg" in ass.inputs
        assert ass.inputs["timeout"].default == 60

    def test_with_outputs(self):
        """outputs as dict of ParameterDefinition."""
        outputs = {
            "status": ParameterDefinition(type="string"),
            "url": ParameterDefinition(type="string"),
        }
        ass = OperationOrNotificationAssignment(outputs=outputs)
        assert "status" in ass.outputs
        assert ass.outputs["url"].type == "string"


class TestOperationOrNotificationAssignmentImplementation:
    """Different implementation formats."""

    def test_with_string_implementation(self):
        """implementation as simple string."""
        ass = OperationOrNotificationAssignment(implementation="run.sh")
        assert ass.implementation == "run.sh"

    def test_with_dict_implementation(self):
        """implementation as complex dict."""
        impl = {
            "primary": "backup.sh",
            "env": {"DIR": "/backups"},
            "timeout": 120,
        }
        ass = OperationOrNotificationAssignment(implementation=impl)
        assert ass.implementation["primary"] == "backup.sh"
        assert ass.implementation["timeout"] == 120


class TestOperationOrNotificationAssignmentAssignmentType:
    """Assignment type validation."""

    def test_assignment_type_valid(self):
        """OPERATION and NOTIFICATION allowed."""
        ass1 = OperationOrNotificationAssignment()
        ass1._assignment_type = AssignmentType.OPERATION
        out1 = ass1._validate_and_set_assignment_type()
        assert out1._assignment_type == AssignmentType.OPERATION

        ass2 = OperationOrNotificationAssignment()
        ass2._assignment_type = AssignmentType.NOTIFICATION
        out2 = ass2._validate_and_set_assignment_type()
        assert out2._assignment_type == AssignmentType.NOTIFICATION

    def test_assignment_type_invalid(self):
        """Invalid value raises ValueError."""
        ass = OperationOrNotificationAssignment()
        ass._assignment_type = "wrong"  # type: ignore
        with pytest.raises(ValueError):
            ass._validate_and_set_assignment_type()


class TestOperationOrNotificationAssignmentSerialization:
    """Serialization checks."""

    def test_model_dump_exclude_none(self):
        """Dump excludes None and the private field."""
        ass = OperationOrNotificationAssignment(
            implementation="do.sh",
            description="Operation",
        )
        ass._assignment_type = AssignmentType.OPERATION
        dumped = ass.model_dump(exclude_none=True)
        assert "implementation" in dumped
        assert "description" in dumped
        assert "_assignment_type" not in str(dumped)

    def test_empty_dump(self):
        """Empty dump with defaults."""
        ass = OperationOrNotificationAssignment()
        dumped = ass.model_dump(exclude_none=True)
        assert dumped == {}


class TestOperationOrNotificationAssignmentEdgeCases:
    """Edge cases."""

    def test_empty_inputs_outputs(self):
        """Empty dicts accepted."""
        ass = OperationOrNotificationAssignment(inputs={}, outputs={})
        assert ass.inputs == {}
        assert ass.outputs == {}

    def test_unicode_values(self):
        """Unicode support in text fields."""
        ass = OperationOrNotificationAssignment(
            implementation="script_🚀.sh",
            description="Operazione con emoji ✨",
            metadata={"note": "🧪"},
        )
        assert "🚀" in ass.implementation
        assert "✨" in ass.description
        assert ass.metadata["note"] == "🧪"
