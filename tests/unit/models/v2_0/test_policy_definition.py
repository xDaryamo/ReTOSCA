"""Unit tests for PolicyDefinition class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.policy_definition import PolicyDefinition
from src.models.v2_0.trigger_definition import TriggerDefinition


class TestPolicyDefinitionBasics:
    """Basic behavior and required fields."""

    def test_minimal_policy(self):
        """Only type is required."""
        p = PolicyDefinition(type="tosca.policies.Root")
        assert p.type == "tosca.policies.Root"
        assert p.properties is None
        assert p.targets is None
        assert p.triggers is None

    def test_missing_type_raises(self):
        """Omitting type should raise ValidationError."""
        with pytest.raises(ValidationError):
            PolicyDefinition()  # type: ignore


class TestPolicyDefinitionPropertiesTargets:
    """Properties and targets behavior."""

    def test_with_properties(self):
        props = {"threshold": 80, "metric": "cpu"}
        p = PolicyDefinition(type="Scaling", properties=props)
        assert p.properties == props

    def test_with_targets(self):
        targets = ["web_group", "db_node"]
        p = PolicyDefinition(type="Placement", targets=targets)
        assert p.targets == targets

    def test_empty_targets(self):
        p = PolicyDefinition(type="Placement", targets=[])
        assert p.targets == []


class TestPolicyDefinitionTriggers:
    """Triggers field behavior."""

    def test_with_triggers(self):
        trg = TriggerDefinition(event="cpu_high", action=[{"call": "scale_out"}])
        p = PolicyDefinition(type="Scaling", triggers={"high_cpu": trg})
        assert "high_cpu" in p.triggers
        assert isinstance(p.triggers["high_cpu"], TriggerDefinition)
        assert p.triggers["high_cpu"].event == "cpu_high"

    def test_empty_triggers(self):
        p = PolicyDefinition(type="Scaling", triggers={})
        assert p.triggers == {}


class TestPolicyDefinitionSerialization:
    """model_dump behavior."""

    def test_model_dump_exclude_none(self):
        p = PolicyDefinition(type="X", properties={"k": "v"})
        dumped = p.model_dump(exclude_none=True)
        assert dumped["type"] == "X"
        assert dumped["properties"] == {"k": "v"}
        assert "targets" not in dumped
        assert "triggers" not in dumped

    def test_model_dump_include_none(self):
        p = PolicyDefinition(type="X")
        dumped = p.model_dump(exclude_none=False)
        for k in ("properties", "targets", "triggers"):
            assert k in dumped


class TestPolicyDefinitionInheritanceAndUnicode:
    """ToscaBase fields and unicode support."""

    def test_inheritance_fields(self):
        p = PolicyDefinition(
            type="X",
            description="A test policy",
            metadata={"owner": "unit-test"},
        )
        assert p.description == "A test policy"
        assert p.metadata == {"owner": "unit-test"}

    def test_unicode_values(self):
        trg = TriggerDefinition(event="⚡", action=[{"call": "scale_🚀"}])
        p = PolicyDefinition(
            type="Policy✨",
            properties={"descr": "🔥"},
            targets=["web✨"],
            triggers={"t": trg},
            description="Policy 🌟",
        )
        assert "✨" in p.type
        assert p.properties["descr"] == "🔥"
        assert "✨" in p.targets[0]
        assert p.triggers["t"].event == "⚡"
        assert "🌟" in p.description
