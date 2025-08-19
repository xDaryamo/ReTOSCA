"""Unit tests for GroupDefinition class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.group_definition import GroupDefinition


class TestGroupDefinitionBasics:
    """Basic behavior and required fields."""

    def test_minimal_group(self):
        """Only type is required."""
        g = GroupDefinition(type="tosca.groups.Root")
        assert g.type == "tosca.groups.Root"
        assert g.properties is None
        assert g.attributes is None
        assert g.members is None

    def test_missing_type_raises(self):
        """Omitting type should raise ValidationError."""
        with pytest.raises(ValidationError):
            GroupDefinition()  # type: ignore

    def test_with_properties_and_attributes(self):
        """Setting properties and attributes."""
        props = {"size": 3, "env": "prod"}
        attrs = {"status": "active"}
        g = GroupDefinition(type="my.Group", properties=props, attributes=attrs)
        assert g.properties == props
        assert g.attributes == attrs

    def test_with_members(self):
        """Setting members list."""
        g = GroupDefinition(type="my.Group", members=["web1", "db1"])
        assert g.members == ["web1", "db1"]


class TestGroupDefinitionSerialization:
    """Serialization behavior."""

    def test_model_dump_exclude_none(self):
        """Dump excludes None fields."""
        g = GroupDefinition(
            type="g.Type",
            properties={"k": "v"},
            members=["n1"],
        )
        dumped = g.model_dump(exclude_none=True)
        assert dumped["type"] == "g.Type"
        assert "properties" in dumped
        assert "members" in dumped
        assert "attributes" not in dumped

    def test_model_dump_include_none(self):
        """Dump includes None fields."""
        g = GroupDefinition(type="tosca.groups.Root")
        dumped = g.model_dump(exclude_none=False)
        assert "type" in dumped
        assert "properties" in dumped
        assert "attributes" in dumped
        assert "members" in dumped


class TestGroupDefinitionInheritance:
    """Ensure ToscaBase inheritance works."""

    def test_description_and_metadata(self):
        """ToscaBase fields are supported."""
        g = GroupDefinition(
            type="g.Type",
            description="A test group",
            metadata={"owner": "unit-test"},
        )
        assert g.description == "A test group"
        assert g.metadata == {"owner": "unit-test"}


class TestGroupDefinitionEdgeCases:
    """Edge cases and unicode."""

    def test_empty_dicts_and_lists(self):
        """Empty dicts/lists are accepted."""
        g = GroupDefinition(type="g.Type", properties={}, attributes={}, members=[])
        assert g.properties == {}
        assert g.attributes == {}
        assert g.members == []

    def test_unicode_values(self):
        """Unicode is supported in all fields."""
        g = GroupDefinition(
            type="g.Type✨",
            properties={"descr": "🔥"},
            attributes={"state": "🚀"},
            members=["m1", "m2✨"],
            description="Group 🌟",
        )
        assert "✨" in g.type
        assert g.properties["descr"] == "🔥"
        assert g.attributes["state"] == "🚀"
        assert "🌟" in g.description
