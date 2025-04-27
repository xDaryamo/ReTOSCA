"""
Package façade – a single import gives users everything they need:


Design
------
* Thin wrapper around ConversionPipeline (keeps public API tiny).
* Re-exports only what external callers should see (encapsulation).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from ir.models import DeploymentModel

from .conversion_pipeline import ConversionPipeline

__all__ = ["convert_clout_to_ir"]

logger = logging.getLogger(__name__)


def convert_clout_to_ir(
    source: str | Path | Dict[str, Any],
    *,
    keep_metadata: bool = False,
) -> DeploymentModel:
    """
    Convenience helper that hides the internal pipeline machinery.

    Parameters
    ----------
    source
        Path/str to a clout file or an already-loaded dict.
    keep_metadata
        Forwarded to ConversionPipeline (default False).
    """
    return ConversionPipeline(source, keep_metadata=keep_metadata).run()
