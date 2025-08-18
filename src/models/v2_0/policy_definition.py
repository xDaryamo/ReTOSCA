from typing import Any

from pydantic import Field

from .base_tosca import ToscaBase
from .trigger_definition import TriggerDefinition


class PolicyDefinition(ToscaBase):
    """
    Represents a TOSCA policy definition.

    Defines a policy that can be associated with a service, group, or node
    template. Policies describe non-functional behaviors or QoS objectives and
    are not topology dependencies (TOSCA 2.0 §16.4).
    """

    type: str = Field(
        ...,
        description="Required name of the policy type this definition is based on.",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description=("Optional map of property assignments for the policy definition."),
    )
    targets: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of node template or group names to which the "
            "policy applies."
        ),
    )
    triggers: dict[str, TriggerDefinition] | None = Field(
        default=None,
        description="Optional map of trigger definitions for the policy.",
    )
