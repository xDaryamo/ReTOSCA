"""
Conversion package

Transforms a normalised clout dictionary into IR primitives
without performing any I/O.

Public helpers
--------------
convert_clout_to_ir(clout, keep_meta=False) -> DeploymentModel
    Convenience wrapper that instantiates the clout converter
    and assembles a ready–validated DeploymentModel.
"""

from __future__ import annotations
from typing import Any, Dict

from src.ir.models import DeploymentModel
from .converter import CloutToIRConverter


def process_clout_to_ir(
    clout: Dict[str, Any], *, keep_meta: bool = False
) -> DeploymentModel:
    """High-level helper used by the conversion pipeline."""
    converter = CloutToIRConverter(clout, keep_meta=keep_meta)
    return converter.convert()
