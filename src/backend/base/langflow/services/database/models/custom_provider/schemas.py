"""Enums and wire schemas for the custom_provider package.

Kept separate from ``model.py`` so modules like ``crud.py`` can use these
types without pulling in SQLModel / SQLAlchemy dependencies.
"""

from enum import Enum


class ValidationStatus(str, Enum):
    """Last endpoint-probe outcome for a custom provider."""

    DRAFT = "draft"
    VALID = "valid"
    INVALID = "invalid"
