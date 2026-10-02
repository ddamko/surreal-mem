"""Record identifiers as plain strings of the form ``table:key``.

Domain code never depends on the database driver; adapters translate these
strings to and from the SDK's ``RecordID``.
"""

from dataclasses import dataclass


class InvalidRecordRef(ValueError):
    """A string is not a ``table:key`` reference."""


@dataclass(frozen=True, slots=True)
class RecordRef:
    """A typed reference to a record in a named table."""

    table: str
    key: str

    def __str__(self) -> str:
        return f"{self.table}:{self.key}"

    @classmethod
    def parse(cls, value: str, *, expect_table: str | None = None) -> RecordRef:
        table, sep, key = value.partition(":")
        if not sep or not table or not key:
            raise InvalidRecordRef(f"not a record reference: {value!r}")
        key = key.strip("⟨⟩`")
        if expect_table is not None and table != expect_table:
            raise InvalidRecordRef(f"expected a {expect_table} reference, got {value!r}")
        return cls(table, key)
