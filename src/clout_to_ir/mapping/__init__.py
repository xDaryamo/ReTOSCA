"""
Mapping package

Transforms a normalised clout dictionary into IR primitives
without performing any I/O.

Public helpers
--------------
build_ir(nodes_raw, keep_meta=False) -> DeploymentModel
    Convenience wrapper that instantiates all concrete strategies
    and assembles a ready–validated DeploymentModel.
"""

from __future__ import annotations

from typing import Any, Dict

from src.ir.models import DeploymentModel

from .strategy_factory import StrategyFactory


def build_ir(
    clout: Dict[str, Any], *, keep_meta: bool = False
) -> DeploymentModel:
    """High-level helper used by the conversion pipeline."""
    factory = StrategyFactory(clout, keep_meta=keep_meta)
    return factory.build_ir()
