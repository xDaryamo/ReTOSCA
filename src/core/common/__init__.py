"""Common base classes and utilities for core functionality."""

from .base_mapper import BaseResourceMapper
from .base_parser import BaseSourceFileParser
from .base_phase_plugin import BasePhasePlugin

__all__ = ["BaseSourceFileParser", "BaseResourceMapper", "BasePhasePlugin"]
