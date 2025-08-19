"""Unit tests for TriggerDefinition class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.trigger_definition import TriggerDefinition


class TestTriggerDefinitionBasics:
    """Basic behavior and required fields."""

    def test_minimal_ok(self):
        """event and action are required, condition is optional."""
        trg = TriggerDefinition(event="on_success", action=[{"call": "notify"}])
        assert trg.event == "on_success"
        assert trg.action == [{"call": "notify"}]
        assert trg.condition is None

    def test_missing_event_raises(self):
        """Missing event -> ValidationError."""
        with pytest.raises(ValidationError):
            TriggerDefinition(action=[{"call": "x"}])  # type: ignore[arg-type]

    def test_missing_action_raises(self):
        """Missing action -> ValidationError."""
        with pytest.raises(ValidationError):
            TriggerDefinition(event="on_fail")  # type: ignore[arg-type]

    def test_action_must_be_list(self):
        """action not a list -> Type ValidationError."""
        with pytest.raises(ValidationError):
            TriggerDefinition(
                event="on_start",
                action={"call": "do"},  # type: ignore[arg-type]
            )

    def test_empty_action_list_allowed(self):
        """Empty list is accepted by the current model."""
        trg = TriggerDefinition(event="noop", action=[])
        assert trg.action == []


class TestTriggerDefinitionOptionalCondition:
    """Condition field behavior."""

    def test_with_condition(self):
        """Free setting of condition."""
        cond = {"and": [{"greater_than": 0}, {"less_than": 10}]}
        trg = TriggerDefinition(
            event="metric", action=[{"call": "scale"}], condition=cond
        )
        assert trg.condition == cond


class TestTriggerDefinitionSerialization:
    """model_dump behavior."""

    def test_model_dump_exclude_none(self):
        """Dump without None."""
        trg = TriggerDefinition(event="e", action=[{"op": "x"}])
        dumped = trg.model_dump(exclude_none=True)
        assert dumped == {"event": "e", "action": [{"op": "x"}]}

    def test_model_dump_include_none(self):
        """Dump including None."""
        trg = TriggerDefinition(event="e", action=[{"op": "x"}])
        dumped = trg.model_dump(exclude_none=False)
        assert "condition" in dumped and dumped["condition"] is None


class TestTriggerDefinitionInheritance:
    """ToscaBase fields inheritance."""

    def test_description_and_metadata(self):
        """ToscaBase fields work."""
        trg = TriggerDefinition(
            event="notify",
            action=[{"call": "send"}],
            description="Trigger di test",
            metadata={"owner": "unit-test"},
        )
        assert trg.description == "Trigger di test"
        assert trg.metadata == {"owner": "unit-test"}


class TestTriggerDefinitionUnicode:
    """Unicode handling."""

    def test_unicode_values(self):
        """Unicode support in all fields."""
        trg = TriggerDefinition(
            event="on_✨",
            action=[{"call": "notify_🚀"}],
            condition={"msg": "ok ✅"},
            description="Trig con emoji 🌟",
        )
        assert "✨" in trg.event
        assert "🚀" in trg.action[0]["call"]
        assert "✅" in trg.condition["msg"]
        assert "🌟" in trg.description
