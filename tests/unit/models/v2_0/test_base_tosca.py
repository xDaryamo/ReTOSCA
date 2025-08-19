"""Unit tests for ToscaBase class."""

from src.models.v2_0.base_tosca import ToscaBase


class TestToscaBaseBasics:
    """Basic behavior and defaults for ToscaBase."""

    def test_defaults(self):
        """metadata and description are None by default."""
        tb = ToscaBase()
        assert tb.metadata is None
        assert tb.description is None

    def test_set_fields(self):
        """Explicit setting of optional fields."""
        tb = ToscaBase(
            metadata={"owner": "unit-test"},
            description="Elemento TOSCA di test",
        )
        assert tb.metadata == {"owner": "unit-test"}
        assert tb.description == "Elemento TOSCA di test"

    def test_unicode_values(self):
        """Unicode support in base fields."""
        tb = ToscaBase(
            metadata={"nota": "⭐"},
            description="Descrizione con emoji 🚀",
        )
        assert tb.metadata["nota"] == "⭐"
        assert "🚀" in tb.description


class TestToscaBaseSerialization:
    """Serialization checks for model_dump behavior."""

    def test_model_dump_exclude_none(self):
        """Dump excludes None and keeps valued fields."""
        tb = ToscaBase(description="Solo descrizione")
        dumped = tb.model_dump(exclude_none=True)
        assert dumped == {"description": "Solo descrizione"}

    def test_model_dump_include_none(self):
        """Dump with None includes both keys."""
        tb = ToscaBase()
        dumped = tb.model_dump(exclude_none=False)
        assert "metadata" in dumped and dumped["metadata"] is None
        assert "description" in dumped and dumped["description"] is None


class TestToscaBaseSubclassing:
    """Check that Pydantic inheritance works."""

    class Dummy(ToscaBase):
        extra_field: int | None = None

    def test_subclass_has_base_fields(self):
        """The subclass exposes both base and its own fields."""
        obj = self.Dummy(
            metadata={"k": "v"},
            description="desc",
            extra_field=7,
        )
        assert obj.metadata == {"k": "v"}
        assert obj.description == "desc"
        assert obj.extra_field == 7

    def test_subclass_serialization(self):
        """Subclass dump includes non-None fields."""
        obj = self.Dummy(description="x", extra_field=0)
        dumped = obj.model_dump(exclude_none=True)
        assert dumped == {"description": "x", "extra_field": 0}
