from typing import Any

from pydantic import Field, field_validator

from .base_tosca import ToscaBase
from .service_template import ServiceTemplate


class ToscaFile(ToscaBase):
    """
    Represents a TOSCA file (root document).

    Container for service templates, type definitions, repositories,
    functions, profiles, imports, and related metadata. Based on TOSCA 2.0.
    Relationship templates and substitution mappings are excluded.
    """

    tosca_definitions_version: str = Field(
        ...,
        description=(
            "Required TOSCA specification version. Must be the first line in "
            "the TOSCA file (e.g., 'tosca_2_0')."
        ),
    )
    dsl_definitions: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map of YAML-style macros (aliases) for reuse throughout "
            "the TOSCA file."
        ),
    )
    repositories: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map of external repository definitions referenced or "
            "imported in this TOSCA file."
        ),
    )
    profile: str | None = Field(
        default=None,
        description=(
            "Optional profile name for the collection of type definitions, "
            "repositories, and functions in this TOSCA file."
        ),
    )
    imports: list[Any] | None = Field(
        default=None,
        description=(
            "Optional list of import statements referencing external TOSCA "
            "files or known profiles."
        ),
    )
    service_template: ServiceTemplate | None = Field(
        default=None,
        description=(
            "Optional complete service template definition for the application "
            "or service."
        ),
    )

    @field_validator("tosca_definitions_version")
    def validate_tosca_version(cls, v: str) -> str:
        valid_versions = ["tosca_2_0"]  # extend in future if needed
        if v not in valid_versions:
            raise ValueError(
                "tosca_definitions_version must be one of: " f"{valid_versions}"
            )
        return v
