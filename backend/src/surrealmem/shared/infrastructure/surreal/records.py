"""Translate between SDK values (RecordID, PreciseDatetime) and plain domain values."""

from datetime import UTC, datetime
from typing import Any, cast

from surrealdb import RecordID

from surrealmem.shared.domain import RecordRef


def to_record_id(ref: str | RecordRef) -> RecordID:
    parsed = RecordRef.parse(ref) if isinstance(ref, str) else ref
    return RecordID(parsed.table, parsed.key)


def ref_str(value: Any) -> str:
    """Render a RecordID (or an already-plain string) as ``table:key``."""
    if isinstance(value, RecordID):
        return f"{value.table_name}:{value.id}"
    if isinstance(value, str):
        return str(RecordRef.parse(value))
    raise TypeError(f"not a record reference: {value!r}")


def opt_ref_str(value: Any) -> str | None:
    return None if value is None else ref_str(value)


def to_datetime(value: Any) -> datetime:
    """Normalize the SDK's datetime flavours to a timezone-aware ``datetime``."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if hasattr(value, "to_datetime"):
        return to_datetime(value.to_datetime())
    if hasattr(value, "isoformat"):
        return to_datetime(datetime.fromisoformat(cast("str", value.isoformat())))
    if isinstance(value, str):
        return to_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise TypeError(f"not a datetime: {value!r}")


def opt_datetime(value: Any) -> datetime | None:
    return None if value is None else to_datetime(value)


def plain(value: Any) -> Any:
    """Recursively convert SDK types inside metadata blobs to JSON-friendly values."""
    if isinstance(value, RecordID):
        return ref_str(value)
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in cast("dict[Any, Any]", value).items()}
    if isinstance(value, list | tuple):
        return [plain(v) for v in cast("list[Any]", value)]
    if isinstance(value, datetime):
        return to_datetime(value).isoformat()
    if hasattr(value, "to_datetime"):
        return to_datetime(value).isoformat()
    return value


def rows_with(results: list[Any], marker: str) -> list[dict[str, Any]]:
    """Return the first statement result that is a list of rows containing ``marker``.

    Used after multi-statement scripts (transactions) where the interesting statement is not last.
    """
    for result in results:
        if isinstance(result, list):
            rows = cast("list[Any]", result)
            if rows and isinstance(rows[0], dict) and marker in cast("dict[str, Any]", rows[0]):
                return cast("list[dict[str, Any]]", rows)
    raise LookupError(f"no statement returned rows containing {marker!r}")
