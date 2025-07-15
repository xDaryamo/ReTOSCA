"""
ConversionPipeline – high-level orchestration from clout to IR.

Responsibilities
----------------
1.   Accept either a filesystem path (str/Path) or a pre-parsed dict.
2.   Invoke the I/O layer to obtain a Python dict.
3.   Invoke the mapping layer to build a validated DeploymentModel.
4.   Surface all domain-specific exceptions unchanged so that callers
     can handle them in a single try/except.

This is intentionally lightweight: if you ever introduce multiple mapping
strategies (deterministic vs LLM) you can extend the class without touching
client code (Open/Closed Principle).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from ir.models import DeploymentModel

from .exceptions import CloutError
from .io.loader_factory import LoaderFactory
from .conversion import process_clout_to_ir

logger = logging.getLogger(__name__)


class ConversionPipeline:
    """End-to-end converter clout → IR DeploymentModel."""

    def __init__(
        self,
        source: str | Path | Dict[str, Any],
        keep_metadata: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        source
            Path/str to .yaml, .yml, .json or an in-memory dict.
        keep_metadata
            If True, clout-level metadata is copied to the IR.
        """
        if isinstance(source, (str, Path)):
            logger.debug("Loading clout file: %s", source)
            loader_cls = LoaderFactory.resolve(source)
            self._clout_dict = loader_cls.load(source)
        elif isinstance(source, dict):
            logger.debug("Using in-memory clout dictionary")
            self._clout_dict = source
        else:
            raise CloutError(
                "ConversionPipeline: source must be Path | str | dict"
            )

        self._keep_meta = keep_metadata

    def run(self) -> DeploymentModel:
        """Return a fully-validated `DeploymentModel` (raises on failure)."""
        logger.debug("Building DeploymentModel from clout dict")
        model = process_clout_to_ir(self._clout_dict, keep_meta=self._keep_meta)

        logger.info(
            "Conversion succeeded – %d node(s), %d relationship(s)",
            len(model.nodes),
            len(model.relationships),
        )
        return model
