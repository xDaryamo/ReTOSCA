from typing import Any

from pydantic import BaseModel, Field


class ToscaBase(BaseModel):
    """
    Base class for TOSCA 2.0 elements supporting multi-line definitions,
    such as type definitions and templates.
    """

    metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional map for additional information about the element. Not inherited."
        ),
    )
    description: str | None = Field(
        default=None,
        description=("Optional description of the TOSCA element. Not inherited."),
    )
