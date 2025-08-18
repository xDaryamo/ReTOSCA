from typing import Any

from pydantic import Field, field_validator

from .base_tosca import ToscaBase


class ArtifactDefinition(ToscaBase):
    """
    Represents a TOSCA artifact definition for a node template.

    Artifacts provide the content required for implementing interface operations
    or for deployment. They can be executables, configuration files, data files,
    or any resource needed for node instantiation or operation.

    This class supports all standard TOSCA artifact definition fields as per
    the specification.
    """

    type: str = Field(
        ..., description="Required artifact type (e.g., Bash, Python, DockerImage)."
    )
    file: str = Field(
        ...,
        description="Required URI (relative or absolute) to locate the artifact file.",
    )
    repository: str | None = Field(
        default=None,
        description=(
            "Optional name of the external repository used to retrieve the " "artifact."
        ),
    )

    artifact_version: str | None = Field(
        default=None, description="Optional version of the artifact."
    )
    checksum: str | None = Field(
        default=None, description="Optional checksum to validate artifact integrity."
    )
    checksum_algorithm: str | None = Field(
        default=None, description="Optional algorithm used for checksum validation."
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map of property assignments associated with the " "artifact."
        ),
    )

    @field_validator("checksum_algorithm")
    def validate_checksum_algorithm(cls, v):
        if v is not None:
            valid_algorithms = ["MD5", "SHA-1", "SHA-256", "SHA-512"]
            if v not in valid_algorithms:
                raise ValueError(
                    f"Invalid checksum algorithm. Valid values: {valid_algorithms}"
                )
        return v
