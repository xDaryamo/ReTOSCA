"""Choose the appropriate concrete loader (file, URL, …)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Dict, Protocol, cast, runtime_checkable

from ..exceptions import CloutLoadError
from .file_loader import FileLoader


@runtime_checkable
class LoaderProtocol(Protocol):
    """Required signature for every concrete loader."""

    supported_exts: ClassVar[set[str]]

    @staticmethod
    def load(path: str | Path) -> Dict[str, Any]: ...


class LoaderFactory:
    """Simple OCP-friendly resolver – easy to extend later."""

    # Register new loaders here (order matters: first match wins).
    _LOADERS = (FileLoader,)

    @classmethod
    def resolve(cls, path: str | Path) -> type[LoaderProtocol]:
        """Return the first loader that *claims* to support the given path."""
        for loader in cls._LOADERS:
            if loader is FileLoader:
                # Decide by file-extension
                if Path(path).suffix.lower() in loader.supported_exts:
                    return cast(type[LoaderProtocol], loader)

        raise CloutLoadError(f"No loader found for: {path}")
