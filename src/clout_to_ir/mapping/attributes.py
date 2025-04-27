"""Strategy dedicated to Attribute conversion."""

from __future__ import annotations

from typing import Any, Dict

from src.ir.models import Attribute


class AttributeMapper:
    """Stateless converter for the attributes section"""

    @staticmethod
    def map(raw: Dict[str, Any] | None) -> Dict[str, Attribute]:
        raw = raw or {}
        return {k: Attribute(name=k, value=v) for k, v in raw.items()}
