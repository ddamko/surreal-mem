"""Space tags partition memories (ADR-0002)."""

import re

SPACE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
SHARED_SPACE = "shared"
DEFAULT_SPACE = "personal"


class InvalidSpace(ValueError):
    """A space tag does not match the allowed pattern."""


def validate_space(space: str) -> str:
    if not SPACE_PATTERN.match(space):
        raise InvalidSpace(
            f"space {space!r} must be lowercase letters, digits and . _ : - "
            "(for example project:surreal-mem)"
        )
    return space


def normalize_name(name: str) -> str:
    """Mirror of the database function ``fn::normalize_name``."""
    return " ".join(name.strip().lower().split())
