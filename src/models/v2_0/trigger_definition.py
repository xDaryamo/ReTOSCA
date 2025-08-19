from typing import Any

from pydantic import Field

from .base_tosca import ToscaBase


class TriggerDefinition(ToscaBase):
    """
    Represents a TOSCA trigger definition for a policy.

    Defines a tuple of event, condition, and action tied to a policy, enabling
    automated reactions to specific situations (TOSCA 2.0 §16.4).
    """

    event: str = Field(
        ...,
        description=(
            "Required name of the event that activates the trigger's action. "
            "Usually associated with an interface notification."
        ),
    )
    action: list[Any] = Field(
        ...,
        description=(
            "Required list of sequential activity definitions to execute when "
            "the event is triggered and the condition is met."
        ),
    )
    condition: Any | None = Field(
        default=None,
        description=(
            "Optional condition that must evaluate to true for the action to "
            "execute. If omitted, the event alone triggers the action."
        ),
    )
