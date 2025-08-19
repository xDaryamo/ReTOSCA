"""Unit tests for fluent builders and YAML serialization."""

import re

import pytest
from pydantic import ValidationError

from src.models.v2_0.builder import (
    NodeTemplateBuilder,
    ServiceTemplateBuilder,
    ToscaFileBuilder,
    create_node_template,
    create_service_template,
    create_tosca_file,
)
from src.models.v2_0.node_template import NodeTemplate
from src.models.v2_0.service_template import ServiceTemplate
from src.models.v2_0.tosca_file import ToscaFile


class TestNodeTemplateBuilder:
    """NodeTemplateBuilder happy paths and validation."""

    def test_full_chain_build(self):
        """End-to-end: props, attrs, req, cap, iface, artifact, copy."""
        nb = (
            NodeTemplateBuilder("web", "tosca.nodes.WebServer")
            .with_description("Web node")
            .with_metadata({"owner": "unit-test"})
            .with_directives("create")
            .with_property("cpu", 2)
            .with_properties({"mem": "4 GB"})
            .with_attribute("state", "running")
            .with_attributes({"zone": "eu"})
            .with_count(2)
            .with_copy("base-node")
        )

        # requirement
        (
            nb.add_requirement("dependency")
            .to_node("db")
            .to_capability("Bindable")
            .with_relationship("tosca.relationships.ConnectsTo")
            .with_count(1)
            .optional(True)
            .and_node()
        )

        # capability
        (
            nb.add_capability("host")
            .with_property("mem_size", "4 GB")
            .with_properties({"num_cpus": 2})
            .with_directives("internal")
            .and_node()
        )

        # interface (inputs simplified to dict -> coerced by pydantic)
        (nb.add_interface("Standard").with_input("retries", 3).and_node())

        # artifact
        (
            nb.add_artifact("deploy", "Bash", "scripts/deploy.sh")
            .with_repository("internal")
            .with_version("1.0.0")
            .with_checksum("deadbeef", "SHA-256")
            .and_node()
        )

        node = nb.build()
        assert isinstance(node, NodeTemplate)
        assert node.type == "tosca.nodes.WebServer"
        assert node.description == "Web node"
        assert node.metadata == {"owner": "unit-test"}
        assert node.count == 2
        # alias 'copy' → field 'copy_from'
        assert node.copy_from == "base-node"

        # requirements structure
        assert isinstance(node.requirements, list) and node.requirements
        req = node.requirements[0]["dependency"]
        assert req.node == "db"
        assert req.capability == "Bindable"
        assert req.relationship == "tosca.relationships.ConnectsTo"
        assert req.count == 1
        assert req.optional is True

        # capability structure
        cap = node.capabilities["host"]
        assert cap.properties["mem_size"] == "4 GB"
        assert cap.properties["num_cpus"] == 2
        assert cap.directives == ["internal"]

        # interface inputs coerced to ParameterDefinition
        assert "retries" in node.interfaces["Standard"].inputs

        # artifact
        art = node.artifacts["deploy"]
        assert art.file == "scripts/deploy.sh"
        assert art.repository == "internal"
        assert art.artifact_version == "1.0.0"
        assert art.checksum_algorithm == "SHA-256"

    def test_requirement_negative_count_raises(self):
        nb = NodeTemplateBuilder("n", "X")
        with pytest.raises(ValidationError):
            nb.add_requirement("dep").with_count(-1).and_node()

    def test_capability_invalid_directive_raises(self):
        nb = NodeTemplateBuilder("n", "X")
        with pytest.raises(ValidationError):
            nb.add_capability("host").with_directives("bogus").and_node()

    def test_artifact_invalid_checksum_algo_raises(self):
        nb = NodeTemplateBuilder("n", "X")
        with pytest.raises(ValidationError):
            (
                nb.add_artifact("a", "Bash", "run.sh")
                .with_checksum("deadbeef", "CRC32")
                .and_node()
            )


class TestServiceTemplateBuilder:
    """ServiceTemplateBuilder behavior."""

    def test_build_without_policies_is_ok(self):
        st = ServiceTemplateBuilder().with_description("svc").with_metadata({"k": "v"})
        st.add_node("web", "tosca.nodes.Root")
        model = st.build()
        assert isinstance(model, ServiceTemplate)
        assert "web" in model.node_templates
        assert model.description == "svc"
        assert model.metadata == {"k": "v"}

    def test_to_dict_converts_named_policies(self):
        """Policies kept as {name: PolicyDefinition} are rendered in dict."""
        tfb = ToscaFileBuilder()
        st = tfb.add_service_template()
        st.add_node("web", "tosca.nodes.Root")
        (
            st.add_policy("scale-web", "ScalingPolicy")
            .with_targets("web")
            .with_property("min_instances", 1)
            .and_service()
        )
        d = tfb.to_dict()
        pols = d["service_template"]["policies"]
        assert isinstance(pols, list) and isinstance(pols[0], dict)
        assert "scale-web" in pols[0]
        assert pols[0]["scale-web"]["type"] == "ScalingPolicy"
        assert pols[0]["scale-web"]["targets"] == ["web"]
        assert pols[0]["scale-web"]["properties"]["min_instances"] == 1


class TestToscaFileBuilder:
    """ToscaFileBuilder + YAML serialization."""

    def test_build_returns_pydantic_model(self):
        tfb = create_tosca_file()
        st = tfb.add_service_template()
        st.add_node("db", "tosca.nodes.Database")
        model = tfb.build()
        assert isinstance(model, ToscaFile)
        assert model.tosca_definitions_version == "tosca_2_0"
        assert "db" in model.service_template.node_templates

    def test_to_dict_injects_generation_metadata(self):
        tfb = create_tosca_file()
        st = tfb.add_service_template()
        st.add_node("n1", "X")
        d = tfb.to_dict()
        md = d.get("metadata", {})
        assert md.get("generated_by") == "TOSCA Infrastructure Intent Discovery"
        assert "generator_version" in md
        # timestamp present and ISO-like
        assert re.match(r"\d{4}-\d{2}-\d{2}T", md.get("generation_timestamp", ""))

    def test_to_yaml_contains_core_keys(self):
        tfb = ToscaFileBuilder().with_description("Demo ✨")
        st = tfb.add_service_template()
        st.add_node("web", "tosca.nodes.Root")
        y = tfb.to_yaml()
        assert "tosca_definitions_version: tosca_2_0" in y
        assert "service_template:" in y
        assert "node_templates:" in y
        assert "Demo ✨" in y

    def test_save_yaml_creates_file(self, tmp_path):
        path = tmp_path / "out" / "model.yaml"
        tfb = create_tosca_file()
        st = tfb.add_service_template()
        st.add_node("web", "tosca.nodes.Root")
        content = tfb.save_yaml(str(path))
        assert path.exists()
        assert "tosca_definitions_version: tosca_2_0" in content
        with open(path, encoding="utf-8") as f:
            saved = f.read()
        assert "service_template:" in saved


class TestFactoryHelpers:
    """Factories return ready-to-use builders."""

    def test_factories(self):
        tfb = create_tosca_file()
        stb = create_service_template()
        ntb = create_node_template("x", "X")
        assert isinstance(tfb, ToscaFileBuilder)
        assert isinstance(stb, ServiceTemplateBuilder)
        assert isinstance(ntb, NodeTemplateBuilder)
