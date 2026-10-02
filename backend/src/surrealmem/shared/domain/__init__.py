"""Shared domain primitives."""

from surrealmem.shared.domain.ids import InvalidRecordRef, RecordRef
from surrealmem.shared.domain.spaces import (
    DEFAULT_SPACE,
    SHARED_SPACE,
    InvalidSpace,
    normalize_name,
    validate_space,
)

__all__ = [
    "DEFAULT_SPACE",
    "SHARED_SPACE",
    "InvalidRecordRef",
    "InvalidSpace",
    "RecordRef",
    "normalize_name",
    "validate_space",
]
