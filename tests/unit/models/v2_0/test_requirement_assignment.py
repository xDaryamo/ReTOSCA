"""Unit tests for RequirementAssignment class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.requirement_assignment import RequirementAssignment


class TestRequirementAssignmentBasics:
    """Test suite for RequirementAssignment basic behavior."""

    def test_empty_requirement_assignment_defaults(self):
        """Empty model should have sane defaults."""
        req = RequirementAssignment()
        assert req.node is None
        assert req.capability is None
        assert req.relationship is None
        assert req.allocation is None
        assert req.count == 1  # default
        assert req.node_filter is None
        assert req.directives is None
        assert req.optional is False  # default

    def test_node_as_string(self):
        """node as symbolic name (string)."""
        req = RequirementAssignment(node="database")
        assert req.node == "database"

    def test_node_as_list_valid(self):
        """node as 2-entry list [name, index]."""
        req = RequirementAssignment(node=["web", 0])
        assert isinstance(req.node, list)
        assert req.node[0] == "web"
        assert req.node[1] == 0

    @pytest.mark.parametrize("bad_list", [[], ["only_name"], ["a", 1, 2]])
    def test_node_as_list_invalid_len(self, bad_list):
        """Invalid list lengths should raise ValidationError."""
        with pytest.raises(ValidationError):
            RequirementAssignment(node=bad_list)

    def test_capability_string(self):
        """capability as name or type name (string)."""
        req = RequirementAssignment(capability="Bindable")
        assert req.capability == "Bindable"

    def test_relationship_as_string(self):
        """relationship can be a string (template or type name)."""
        req = RequirementAssignment(relationship="tosca.relationships.ConnectsTo")
        assert req.relationship == "tosca.relationships.ConnectsTo"

    def test_relationship_as_dict(self):
        """relationship can be a dict with refinements/props."""
        rel = {
            "type": "tosca.relationships.ConnectsTo",
            "properties": {"secure": True},
        }
        req = RequirementAssignment(relationship=rel)
        assert isinstance(req.relationship, dict)
        assert req.relationship["type"] == "tosca.relationships.ConnectsTo"
        assert req.relationship["properties"]["secure"] is True

    def test_allocation_block(self):
        """allocation is a free-form dict of property assignments."""
        alloc = {"target-count": 1, "bandwidth": "100 Mbps"}
        req = RequirementAssignment(allocation=alloc)
        assert req.allocation == alloc

    def test_count_defaults_and_zero(self):
        """count defaults to 1 and accepts 0 (NonNegativeInt)."""
        req_default = RequirementAssignment()
        assert req_default.count == 1

        req_zero = RequirementAssignment(count=0)
        assert req_zero.count == 0

    def test_count_negative_invalid(self):
        """Negative count should raise due to NonNegativeInt."""
        with pytest.raises(ValidationError):
            RequirementAssignment(count=-1)

    def test_node_filter_and_directives_and_optional(self):
        """node_filter map, directives list, optional flag."""
        nf = {"capabilities": {"host": {"properties": {"os": "linux"}}}}
        directives = ["substitute", "select"]
        req = RequirementAssignment(
            node_filter=nf,
            directives=directives,
            optional=True,
        )
        assert req.node_filter == nf
        assert req.directives == directives
        assert req.optional is True


class TestRequirementAssignmentSerialization:
    """Test serialization behaviors."""

    def test_model_dump_exclude_none(self):
        """Dump should include defaults but exclude None fields."""
        req = RequirementAssignment()
        dumped = req.model_dump(exclude_none=True)

        # Defaults should be present
        assert dumped.get("count") == 1
        assert dumped.get("optional") is False

        # Fields not set should be absent
        for key in (
            "node",
            "capability",
            "relationship",
            "allocation",
            "node_filter",
            "directives",
        ):
            assert key not in dumped

    def test_model_dump_include_some_fields(self):
        """Dump with some fields populated."""
        req = RequirementAssignment(
            node=["app", 2],
            capability="Bindable",
            count=3,
            optional=True,
        )
        dumped = req.model_dump(exclude_none=True)
        assert dumped["node"] == ["app", 2]
        assert dumped["capability"] == "Bindable"
        assert dumped["count"] == 3
        assert dumped["optional"] is True


class TestRequirementAssignmentInheritanceAndEdgeCases:
    """Edge cases and ToscaBase fields."""

    def test_inheritance_from_tosca_base(self):
        """ToscaBase fields description & metadata should work."""
        req = RequirementAssignment(
            description="Requirement for DB connectivity",
            metadata={"owner": "unit-test"},
        )
        assert req.description == "Requirement for DB connectivity"
        assert req.metadata == {"owner": "unit-test"}

    def test_directives_empty_list(self):
        """Empty directives list is allowed and preserved."""
        req = RequirementAssignment(directives=[])
        assert req.directives == []

    def test_unicode_values(self):
        """Unicode handling in free-form fields."""
        req = RequirementAssignment(
            node="servizio-🛰️",
            capability="Bindable",
            relationship={
                "type": "tosca.relationships.ConnectsTo",
                "properties": {"descr": "connessione 🔐"},
            },
            allocation={"note": "allocazione 🌟"},
        )
        assert "🛰️" in req.node
        assert req.allocation["note"].endswith("🌟")
