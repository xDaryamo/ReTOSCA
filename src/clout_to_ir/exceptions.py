"""
exceptions.py

Custom, typed exception hierarchy used across the clout → IR pipeline
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
#                              Base hierarchy                                 #
# --------------------------------------------------------------------------- #


class CloutError(Exception):
    """
    Root of all clout-related errors raised by this project.
    """


class CloutLoadError(CloutError):
    """
    Raised by the I/O layer when a clout document cannot be read or parsed.

    Examples
    --------
    * File does not exist / bad extension
    * YAML or JSON syntax error
    * Top-level object is not a mapping
    """


class CloutTransformError(CloutError):
    """
    Raised by the Transformer when raw clout data cannot be converted to
    the intermediate Pydantic model (IR).

    This typically wraps:
        * Key/field inconsistencies
        * Missing mandatory sections
        * Pydantic validation failures surfaced while building the IR
    """
