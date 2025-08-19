"""Unit tests for ArtifactDefinition class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.artifact_definition import ArtifactDefinition


class TestArtifactDefinitionBasics:
    """Basic behavior and required fields."""

    def test_minimal_artifact(self):
        """type and file are required; the rest is None/absent."""
        art = ArtifactDefinition(type="Bash", file="scripts/deploy.sh")
        assert art.type == "Bash"
        assert art.file == "scripts/deploy.sh"
        assert art.repository is None
        assert art.artifact_version is None
        assert art.checksum is None
        assert art.checksum_algorithm is None
        assert art.properties is None

    def test_missing_type_raises(self):
        """Missing type -> ValidationError."""
        with pytest.raises(ValidationError):
            ArtifactDefinition(file="scripts/run.sh")  # type: ignore[arg-type]

    def test_missing_file_raises(self):
        """Missing file -> ValidationError."""
        with pytest.raises(ValidationError):
            ArtifactDefinition(type="Python")  # type: ignore[arg-type]

    def test_full_artifact(self):
        """All optional fields populated."""
        props = {"entrypoint": "run.py", "retries": 3}
        art = ArtifactDefinition(
            type="Python",
            file="tools/run.py",
            repository="internal-repo",
            artifact_version="1.2.3",
            checksum="abc123",
            checksum_algorithm="SHA-256",
            properties=props,
            description="Execution tool",
            metadata={"owner": "platform"},
        )
        assert art.repository == "internal-repo"
        assert art.artifact_version == "1.2.3"
        assert art.checksum == "abc123"
        assert art.checksum_algorithm == "SHA-256"
        assert art.properties == props
        # ToscaBase fields
        assert art.description == "Execution tool"
        assert art.metadata == {"owner": "platform"}


class TestArtifactDefinitionChecksumValidation:
    """Validation rules for checksum_algorithm."""

    @pytest.mark.parametrize("algo", ["MD5", "SHA-1", "SHA-256", "SHA-512"])
    def test_valid_checksum_algorithms(self, algo):
        art = ArtifactDefinition(type="Bash", file="deploy.sh", checksum_algorithm=algo)
        assert art.checksum_algorithm == algo

    @pytest.mark.parametrize("algo", ["sha256", "SHA256", "CRC32", "BLAKE2"])
    def test_invalid_checksum_algorithms(self, algo):
        with pytest.raises(ValidationError) as exc:
            ArtifactDefinition(type="Bash", file="deploy.sh", checksum_algorithm=algo)
        assert "Invalid checksum algorithm" in str(exc.value)

    def test_checksum_without_algorithm_is_allowed(self):
        """The model does not require checksum to have also the algorithm."""
        art = ArtifactDefinition(type="Bash", file="deploy.sh", checksum="deadbeef")
        assert art.checksum == "deadbeef"
        assert art.checksum_algorithm is None

    def test_algorithm_without_checksum_is_allowed(self):
        """
        Having only the algorithm is also allowed according to the current validator.
        """
        art = ArtifactDefinition(
            type="Bash", file="deploy.sh", checksum_algorithm="MD5"
        )
        assert art.checksum is None
        assert art.checksum_algorithm == "MD5"


class TestArtifactDefinitionSerialization:
    """Serialization behavior."""

    def test_model_dump_exclude_none(self):
        art = ArtifactDefinition(type="Bash", file="scripts/setup.sh")
        dumped = art.model_dump(exclude_none=True)
        assert dumped == {"type": "Bash", "file": "scripts/setup.sh"}

    def test_model_dump_with_fields(self):
        art = ArtifactDefinition(
            type="DockerImage",
            file="docker://repo/app:1.0",
            repository="dockerhub",
            artifact_version="1.0",
            properties={"pull_policy": "IfNotPresent"},
        )
        dumped = art.model_dump(exclude_none=True)
        assert dumped["type"] == "DockerImage"
        assert dumped["file"] == "docker://repo/app:1.0"
        assert dumped["repository"] == "dockerhub"
        assert dumped["artifact_version"] == "1.0"
        assert dumped["properties"] == {"pull_policy": "IfNotPresent"}


class TestArtifactDefinitionEdgeCases:
    """Edge cases & extras."""

    def test_relative_and_absolute_file_paths(self):
        rel = ArtifactDefinition(type="Bash", file="scripts/install.sh")
        absu = ArtifactDefinition(type="Bash", file="/opt/scripts/install.sh")
        url = ArtifactDefinition(type="Bash", file="https://example.com/a.tgz")
        assert rel.file.startswith("scripts/")
        assert absu.file.startswith("/")
        assert url.file.startswith("https://")

    def test_empty_properties_map(self):
        art = ArtifactDefinition(type="Bash", file="run.sh", properties={})
        assert art.properties == {}

    def test_unicode_in_fields(self):
        art = ArtifactDefinition(
            type="Python",
            file="tools/analisi_🔥.py",
            description="Artifact with unicode ✨",
            metadata={"note": "🧪"},
        )
        assert "🔥" in art.file
        assert "✨" in art.description
        assert art.metadata["note"] == "🧪"
