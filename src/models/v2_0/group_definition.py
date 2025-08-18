from typing import Any

from pydantic import Field

from .base_tosca import ToscaBase


class GroupDefinition(ToscaBase):
    """
    Represents a TOSCA group definition.

    Groups node templates for uniform policy application and management.
    Memberships are logical (not deployment dependencies).
    Based on TOSCA 2.0 Section 16.2.
    """

    type: str = Field(
        ..., description="Required name of the group type this definition is based on."
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description="Optional map of property assignments for the group definition.",
    )
    attributes: dict[str, Any] | None = Field(
        default=None,
        description="Optional map of attribute assignments for the group definition.",
    )
    members: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of node template or group symbolic names "
            "that are members of this group."
        ),
    )
