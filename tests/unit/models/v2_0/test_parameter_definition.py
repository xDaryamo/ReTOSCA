"""Unit tests for ParameterDefinition class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.parameter_definition import ParameterDefinition


class TestParameterDefinitionBasics:
    """Basic behavior and defaults."""

    def test_defaults(self):
        """Optional fields at default."""
        p = ParameterDefinition()
        assert p.type is None
        assert p.value is None
        assert p.mapping is None
        assert p.required is True
        assert p.default is None
        assert p.validation is None
        assert p.key_schema is None
        assert p.entry_schema is None

    def test_set_type_only(self):
        """Set only type."""
        p = ParameterDefinition(type="string")
        assert p.type == "string"
        assert p.required is True

    def test_set_value(self):
        """Set value (output style)."""
        p = ParameterDefinition(type="integer", value=42)
        assert p.type == "integer"
        assert p.value == 42
        assert p.mapping is None

    def test_set_mapping(self):
        """Set mapping (input style)."""
        m = {"get_attribute": ["srv", "ip"]}
        p = ParameterDefinition(type="string", mapping=m)
        assert p.mapping == m
        assert p.value is None

    def test_set_default_and_required_true(self):
        """default allowed with required=True."""
        p = ParameterDefinition(type="string", required=True, default="x")
        assert p.default == "x"
        assert p.required is True


class TestParameterDefinitionValidationRules:
    """Validator: exclusivity and default/required."""

    def test_value_and_mapping_both_set_invalid(self):
        """value and mapping together → ValidationError."""
        with pytest.raises(ValidationError) as exc:
            ParameterDefinition(
                type="string",
                value="v",
                mapping={"get_input": "i"},
            )
        assert "mutually exclusive" in str(exc.value)

    def test_value_only_ok(self):
        """Only value is valid."""
        p = ParameterDefinition(type="string", value="ok")
        assert p.value == "ok"
        assert p.mapping is None

    def test_mapping_only_ok(self):
        """Only mapping is valid."""
        m = {"get_property": ["SELF", "p"]}
        p = ParameterDefinition(type="string", mapping=m)
        assert p.mapping == m
        assert p.value is None

    def test_both_none_ok(self):
        """Both None are allowed."""
        p = ParameterDefinition(type="string", value=None, mapping=None)
        assert p.value is None and p.mapping is None

    def test_default_with_required_false_invalid(self):
        """default with required=False → ValidationError."""
        with pytest.raises(ValidationError) as exc:
            ParameterDefinition(
                type="string",
                required=False,
                default="nope",
            )
        assert "required=False" in str(exc.value)

    def test_default_with_required_none_ok(self):
        """default allowed with required=None."""
        p = ParameterDefinition(type="string", required=None, default="x")
        assert p.default == "x"
        assert p.required is None


class TestParameterDefinitionSchemasAndValidation:
    """key_schema, entry_schema, validation."""

    def test_key_and_entry_schema(self):
        """Setting key_schema and entry_schema."""
        p = ParameterDefinition(
            type="map",
            key_schema={"type": "string"},
            entry_schema={"type": "integer"},
        )
        assert p.key_schema == {"type": "string"}
        assert p.entry_schema == {"type": "integer"}

    def test_validation_clause_passthrough(self):
        """validation is stored as passed."""
        v = {"in_range": [1, 10]}
        p = ParameterDefinition(type="integer", validation=v)
        assert p.validation == v


class TestParameterDefinitionSerialization:
    """model_dump behavior."""

    def test_model_dump_exclude_none_minimal(self):
        """Minimal dump without None."""
        p = ParameterDefinition(type="string")
        dumped = p.model_dump(exclude_none=True)
        assert dumped == {"type": "string", "required": True}

    def test_model_dump_exclude_none_with_fields(self):
        """Dump with some fields set."""
        p = ParameterDefinition(
            type="integer",
            value=7,
            validation={"min": 0},
        )
        dumped = p.model_dump(exclude_none=True)
        exp = {
            "type": "integer",
            "value": 7,
            "required": True,
            "validation": {"min": 0},
        }
        assert dumped == exp

    def test_model_dump_include_none(self):
        """Dump including None."""
        p = ParameterDefinition(type="string")
        dumped = p.model_dump(exclude_none=False)
        assert dumped["type"] == "string"
        assert dumped["required"] is True
        assert dumped["value"] is None
        assert dumped["mapping"] is None
        assert dumped["default"] is None


class TestParameterDefinitionUnicodeAndEdgeCases:
    """Unicode and edge cases."""

    def test_unicode_fields(self):
        """Unicode support in description and values."""
        p = ParameterDefinition(
            type="string",
            value="🚀",
            default="✨",
            description="Param con emoji 🌟",
            metadata={"note": "🧪"},
        )
        assert p.value == "🚀"
        assert p.default == "✨"
        assert "🌟" in p.description
        assert p.metadata["note"] == "🧪"

    def test_empty_string_type(self):
        """Empty type is accepted as string."""
        p = ParameterDefinition(type="")
        assert p.type == ""
