"""Concrete Loader that supports local YAML / JSON files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Final

from ruamel.yaml import YAML

from ..exceptions import CloutLoadError

logger = logging.getLogger(__name__)

_YAML_EXTS: Final[set[str]] = {".yaml", ".yml"}
_JSON_EXTS: Final[set[str]] = {".json"}

_yaml_parser = YAML(typ="safe")  # safe loader, YAML 1.2


class FileLoader:
    """Read a clout file from disk and return a Python `dict`."""

    supported_exts: set[str] = _YAML_EXTS | _JSON_EXTS

    @staticmethod
    def load(path: str | Path) -> Dict[str, Any]:
        file_path = Path(path)

        # validation
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            raise CloutLoadError(f"File not found: {file_path}")

        if file_path.suffix.lower() not in FileLoader.supported_exts:
            raise CloutLoadError(
                f"Unsupported extension '{file_path.suffix}'. "
                f"Supported: {', '.join(sorted(FileLoader.supported_exts))}"
            )

        raw_text = file_path.read_text(encoding="utf-8")

        # parse
        try:
            if file_path.suffix.lower() in _YAML_EXTS:
                data: Dict[str, Any] = _yaml_parser.load(raw_text)
            else:  # .json
                data = json.loads(raw_text)
        except Exception as exc:
            raise CloutLoadError(
                f"Cannot parse {file_path.name}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise CloutLoadError("Top-level object must be a mapping")

        logger.debug("Clout file loaded (%d root keys)", len(data))
        return data
