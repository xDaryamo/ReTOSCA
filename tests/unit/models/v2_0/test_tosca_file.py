"""Unit tests for ToscaFile class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.service_template import ServiceTemplate
from src.models.v2_0.tosca_file import ToscaFile


class TestToscaFileBasics:
    """Basic behavior and required field."""

    def test_minimal_valid(self):
        """Only tosca_definitions_version is required."""
        tf = ToscaFile(tosca_definitions_version="tosca_2_0")
        assert tf.tosca_definitions_version == "tosca_2_0"
        assert tf.dsl_definitions is None
        assert tf.repositories is None
        assert tf.profile is None
        assert tf.imports is None
        assert tf.service_template is None

    def test_missing_version_raises(self):
        """Omitting tosca_definitions_version should raise."""
        with pytest.raises(ValidationError):
            ToscaFile()  # type: ignore

    def test_invalid_version_raises(self):
        """Version must be 'tosca_2_0'."""
        with pytest.raises(ValidationError) as exc:
            ToscaFile(tosca_definitions_version="tosca_1_3")
        assert "tosca_definitions_version must be one of" in str(exc.value)


class TestToscaFileOptionalFields:
    """dsl_definitions, repositories, profile, imports."""

    def test_with_optional_maps_and_profile(self):
        dsl = {"alias_http": {"get_attribute": ["web", "url"]}}
        repos = {"dockerhub": {"url": "https://index.docker.io"}}
        tf = ToscaFile(
            tosca_definitions_version="tosca_2_0",
            dsl_definitions=dsl,
            repositories=repos,
            profile="simple-✨",
        )
        assert tf.dsl_definitions == dsl
        assert tf.repositories == repos
        assert tf.profile == "simple-✨"

    def test_with_imports(self):
        imps = ["profile.yaml", {"file": "node_types.yaml"}]
        tf = ToscaFile(
            tosca_definitions_version="tosca_2_0",
            imports=imps,
        )
        assert tf.imports == imps


class TestToscaFileServiceTemplate:
    """Nested ServiceTemplate handling."""

    def test_with_service_template_instance(self):
        st = ServiceTemplate(node_templates={"web": {"type": "Web"}})
        tf = ToscaFile(
            tosca_definitions_version="tosca_2_0",
            service_template=st,
        )
        assert isinstance(tf.service_template, ServiceTemplate)
        assert "web" in tf.service_template.node_templates

    def test_with_service_template_as_dict(self):
        """Pydantic should coerce dict to ServiceTemplate."""
        tf = ToscaFile(
            tosca_definitions_version="tosca_2_0",
            service_template={"node_templates": {"db": {"type": "DB"}}},
        )
        assert isinstance(tf.service_template, ServiceTemplate)
        assert tf.service_template.node_templates["db"].type == "DB"


class TestToscaFileSerialization:
    """model_dump behavior."""

    def test_model_dump_exclude_none(self):
        tf = ToscaFile(
            tosca_definitions_version="tosca_2_0",
            service_template={"node_templates": {"n": {"type": "X"}}},
        )
        dumped = tf.model_dump(exclude_none=True)
        assert dumped["tosca_definitions_version"] == "tosca_2_0"
        assert "service_template" in dumped
        assert "imports" not in dumped

    def test_model_dump_include_none(self):
        tf = ToscaFile(tosca_definitions_version="tosca_2_0")
        dumped = tf.model_dump(exclude_none=False)
        for k in (
            "dsl_definitions",
            "repositories",
            "profile",
            "imports",
            "service_template",
        ):
            assert k in dumped


class TestToscaFileUnicodeAndEdgeCases:
    """Unicode and edge cases."""

    def test_unicode_in_profile_and_imports(self):
        tf = ToscaFile(
            tosca_definitions_version="tosca_2_0",
            profile="profilo✨",
            imports=["a.yaml", "b-🚀.yaml"],
        )
        assert "✨" in tf.profile
        assert "🚀" in tf.imports[1]
