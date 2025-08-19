"""Unit tests for NodeTemplate class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.artifact_definition import ArtifactDefinition
from src.models.v2_0.capability_assignment import CapabilityAssignment
from src.models.v2_0.interface_assignment import InterfaceAssignment
from src.models.v2_0.node_template import NodeTemplate
from src.models.v2_0.requirement_assignment import RequirementAssignment


class TestNodeTemplateBasics:
    """Basic behavior and required fields."""

    def test_minimal_node(self):
        """Only type is required."""
        nt = NodeTemplate(type="tosca.nodes.Root")
        assert nt.type == "tosca.nodes.Root"
        assert nt.directives is None
        assert nt.properties is None
        assert nt.attributes is None
        assert nt.requirements is None
        assert nt.capabilities is None
        assert nt.interfaces is None
        assert nt.artifacts is None
        assert nt.count is None
        assert nt.node_filter is None
        assert nt.copy_from is None

    def test_missing_type_raises(self):
        """Omitting type should raise."""
        with pytest.raises(ValidationError):
            NodeTemplate()  # type: ignore


class TestNodeTemplateDirectives:
    """Validation of directives."""

    def test_valid_directives(self):
        nt = NodeTemplate(type="X", directives=["create", "select", "substitute"])
        assert nt.directives == ["create", "select", "substitute"]

    def test_invalid_directive_raises(self):
        with pytest.raises(ValidationError) as exc:
            NodeTemplate(type="X", directives=["bad"])
        assert "Invalid directive" in str(exc.value)

    def test_empty_directives_allowed(self):
        nt = NodeTemplate(type="X", directives=[])
        assert nt.directives == []


class TestNodeTemplateCompositeFields:
    """properties, attributes, reqs, caps, ifaces, artifacts."""

    def test_properties_and_attributes(self):
        props = {"cpu": 2}
        attrs = {"state": "running"}
        nt = NodeTemplate(type="X", properties=props, attributes=attrs)
        assert nt.properties == props
        assert nt.attributes == attrs

    def test_requirements_structure(self):
        req = RequirementAssignment(node="db")
        nt = NodeTemplate(type="X", requirements=[{"dependency": req}])
        assert isinstance(nt.requirements, list)
        assert "dependency" in nt.requirements[0]
        assert nt.requirements[0]["dependency"].node == "db"

    def test_capabilities_map(self):
        cap = CapabilityAssignment(properties={"mem_size": "2 GB"})
        nt = NodeTemplate(type="X", capabilities={"host": cap})
        assert "host" in nt.capabilities
        assert nt.capabilities["host"].properties["mem_size"] == "2 GB"

    def test_interfaces_map(self):
        iface = InterfaceAssignment()
        nt = NodeTemplate(type="X", interfaces={"Standard": iface})
        assert "Standard" in nt.interfaces

    def test_artifacts_map(self):
        art = ArtifactDefinition(type="Bash", file="scripts/deploy.sh")
        nt = NodeTemplate(type="X", artifacts={"deploy": art})
        assert nt.artifacts["deploy"].file == "scripts/deploy.sh"


class TestNodeTemplateCountAndFilter:
    """count and node_filter behavior."""

    def test_count_none_ok_and_non_negative(self):
        nt_none = NodeTemplate(type="X", count=None)
        assert nt_none.count is None
        nt_zero = NodeTemplate(type="X", count=0)
        assert nt_zero.count == 0
        nt_many = NodeTemplate(type="X", count=5)
        assert nt_many.count == 5

    def test_count_negative_raises(self):
        with pytest.raises(ValidationError):
            NodeTemplate(type="X", count=-1)  # type: ignore

    def test_node_filter_pass_through(self):
        nf = {"capabilities": {"host": {"properties": {"os": "linux"}}}}
        nt = NodeTemplate(type="X", directives=["select"], node_filter=nf)
        assert nt.node_filter == nf


class TestNodeTemplateCopyAlias:
    """Alias 'copy' → field 'copy_from' and serialization."""

    def test_copy_alias_on_input(self):
        nt = NodeTemplate(type="X", copy="base-node")  # alias
        assert nt.copy_from == "base-node"

    def test_copy_in_dump_by_alias(self):
        nt = NodeTemplate(type="X", copy="base-node")
        dumped = nt.model_dump(exclude_none=True, by_alias=True)
        assert dumped["copy"] == "base-node"
        assert "copy_from" not in dumped


class TestNodeTemplateSerialization:
    """model_dump behavior."""

    def test_model_dump_exclude_none(self):
        nt = NodeTemplate(type="X", properties={"k": "v"})
        dumped = nt.model_dump(exclude_none=True)
        assert dumped["type"] == "X"
        assert dumped["properties"] == {"k": "v"}
        assert "attributes" not in dumped

    def test_model_dump_include_none(self):
        nt = NodeTemplate(type="X")
        dumped = nt.model_dump(exclude_none=False)
        for k in (
            "directives",
            "properties",
            "attributes",
            "requirements",
            "capabilities",
            "interfaces",
            "artifacts",
            "count",
            "node_filter",
            "copy_from",
        ):
            assert k in dumped


class TestNodeTemplateInheritanceAndUnicode:
    """ToscaBase fields and unicode."""

    def test_toscabase_fields(self):
        nt = NodeTemplate(
            type="X",
            description="A test node",
            metadata={"owner": "unit-test"},
        )
        assert nt.description == "A test node"
        assert nt.metadata == {"owner": "unit-test"}

    def test_unicode_values(self):
        nt = NodeTemplate(
            type="svc.✨",
            properties={"descr": "🔥"},
            attributes={"state": "🚀"},
            interfaces={"Std": InterfaceAssignment(description="iface 🌟")},
            artifacts={"a": ArtifactDefinition(type="Bash", file="run_🎯.sh")},
        )
        assert "✨" in nt.type
        assert nt.properties["descr"] == "🔥"
        assert nt.attributes["state"] == "🚀"
        assert "🌟" in nt.interfaces["Std"].description
        assert "🎯" in nt.artifacts["a"].file
