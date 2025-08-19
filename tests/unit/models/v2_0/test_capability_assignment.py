"""Unit tests for CapabilityAssignment class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.capability_assignment import CapabilityAssignment


class TestCapabilityAssignmentBasics:
    """Basic behavior and defaults."""

    def test_defaults(self):
        """properties, attributes, directives are None by default."""
        cap = CapabilityAssignment()
        assert cap.properties is None
        assert cap.attributes is None
        assert cap.directives is None

    def test_with_properties_and_attributes(self):
        """Assignment of properties and attributes."""
        props = {"cpu": 4, "mem_size": "8 GB"}
        attrs = {"state": "running"}
        cap = CapabilityAssignment(properties=props, attributes=attrs)
        assert cap.properties == props
        assert cap.attributes == attrs

    def test_with_directives_valid(self):
        """Valid directives: internal, external."""
        cap = CapabilityAssignment(directives=["internal", "external"])
        assert cap.directives == ["internal", "external"]

    def test_with_invalid_directive(self):
        """Invalid directive raises ValidationError."""
        with pytest.raises(ValidationError) as exc:
            CapabilityAssignment(directives=["invalid"])
        assert "Invalid directive" in str(exc.value)


class TestCapabilityAssignmentSerialization:
    """Serialization checks."""

    def test_model_dump_exclude_none(self):
        """Dump excludes None, keeps valued fields."""
        cap = CapabilityAssignment(properties={"key": "val"}, directives=["internal"])
        dumped = cap.model_dump(exclude_none=True)
        assert "properties" in dumped
        assert "directives" in dumped
        assert "attributes" not in dumped

    def test_model_dump_include_none(self):
        """Dump also includes None fields."""
        cap = CapabilityAssignment()
        dumped = cap.model_dump(exclude_none=False)
        assert "properties" in dumped
        assert "attributes" in dumped
        assert "directives" in dumped


class TestCapabilityAssignmentEdgeCases:
    """Edge cases."""

    def test_empty_properties_and_attributes(self):
        """Empty maps are accepted and preserved."""
        cap = CapabilityAssignment(properties={}, attributes={})
        assert cap.properties == {}
        assert cap.attributes == {}

    def test_empty_directives_list(self):
        """Empty directives list is accepted."""
        cap = CapabilityAssignment(directives=[])
        assert cap.directives == []

    def test_unicode_values(self):
        """Unicode support in properties and attributes."""
        cap = CapabilityAssignment(
            properties={"descr": "abilità 🔥"},
            attributes={"stato": "attivo 🚀"},
        )
        assert "🔥" in cap.properties["descr"]
        assert "🚀" in cap.attributes["stato"]


class TestCapabilityAssignmentInheritance:
    """ToscaBase fields inheritance."""

    def test_inheritance_fields(self):
        """description and metadata work from ToscaBase."""
        cap = CapabilityAssignment(
            description="Capabilità di test",
            metadata={"source": "unit-test"},
        )
        assert cap.description == "Capabilità di test"
        assert cap.metadata == {"source": "unit-test"}
