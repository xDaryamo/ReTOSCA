from typing import Any

from pydantic import Field

from .base_tosca import ToscaBase
from .group_definition import GroupDefinition
from .node_template import NodeTemplate
from .policy_definition import PolicyDefinition
from .workflow_definition import WorkflowDefinition


class ServiceTemplate(ToscaBase):
    """
    Represents a TOSCA service template.

    Defines the complete structure and management logic for a cloud service
    or complex system, including node templates, groups, policies, workflows,
    inputs, and outputs.

    All fields are modeled according to TOSCA 2.0, excluding
    `relationship_templates` and `substitution_mappings` as requested.
    """

    inputs: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map of input parameter definitions for the service template."
        ),
    )
    outputs: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map of output parameter definitions for the service template."
        ),
    )
    node_templates: dict[str, NodeTemplate] = Field(
        ...,
        description=(
            "Required map of node template definitions for the service template."
        ),
    )
    groups: dict[str, GroupDefinition] | None = Field(
        default=None,
        description=("Optional map of group definitions for the service template."),
    )
    policies: list[PolicyDefinition] | None = Field(
        default=None,
        description=("Optional list of policy definitions for the service template."),
    )
    workflows: dict[str, WorkflowDefinition] | None = Field(
        default=None,
        description=("Optional map of workflow definitions for the service template."),
    )
