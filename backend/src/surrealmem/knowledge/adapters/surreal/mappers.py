"""Row to model mappers for the knowledge tables."""

from typing import Any

from surrealmem.knowledge.domain import (
    BaseType,
    Entity,
    Fact,
    FactStatus,
    RelationKind,
    Relationship,
    SourceKind,
)
from surrealmem.shared.infrastructure.surreal.records import (
    opt_datetime,
    opt_ref_str,
    plain,
    ref_str,
    to_datetime,
)

type Row = dict[str, Any]


def entity_from_row(row: Row) -> Entity:
    return Entity(
        id=ref_str(row["id"]),
        name=row["name"],
        name_key=row["name_key"],
        base_type=BaseType(row["base_type"]),
        subtype=row.get("subtype"),
        description=row.get("description"),
        aliases=list(row.get("aliases") or []),
        spaces=list(row.get("spaces") or []),
        confidence=float(row.get("confidence", 1.0)),
        salience=float(row.get("salience", 0.5)),
        mention_count=int(row.get("mention_count", 0)),
        first_seen_at=opt_datetime(row.get("first_seen_at")),
        last_seen_at=opt_datetime(row.get("last_seen_at")),
        archived=bool(row.get("archived", False)),
        merged_into=opt_ref_str(row.get("merged_into")),
        embedding_model=row.get("embedding_model"),
        metrics=plain(row.get("metrics") or {}),
        projection=plain(row.get("projection") or {}),
        created_at=to_datetime(row["created_at"]),
        updated_at=to_datetime(row["updated_at"]),
        metadata=plain(row.get("metadata") or {}),
    )


def relationship_from_row(row: Row) -> Relationship:
    return Relationship(
        id=ref_str(row["id"]),
        source_id=ref_str(row["in"]),
        target_id=ref_str(row["out"]),
        kind=row["kind"],
        proposed=bool(row.get("proposed", False)),
        weight=float(row.get("weight", 1.0)),
        confidence=float(row.get("confidence", 1.0)),
        spaces=list(row.get("spaces") or []),
        mention_count=int(row.get("mention_count", 1)),
        fact_id=opt_ref_str(row.get("fact")),
        first_seen_at=to_datetime(row["first_seen_at"]),
        last_seen_at=to_datetime(row["last_seen_at"]),
        metadata=plain(row.get("metadata") or {}),
    )


def kind_from_row(row: Row) -> RelationKind:
    return RelationKind(
        kind=row["kind"],
        description=row.get("description"),
        seeded=bool(row.get("seeded", False)),
        proposed=bool(row.get("proposed", False)),
        functional=bool(row.get("functional", False)),
        inverse=row.get("inverse"),
        usage_count=int(row.get("usage_count", 0)),
    )


def fact_from_row(row: Row) -> Fact:
    return Fact(
        id=ref_str(row["id"]),
        statement=row["statement"],
        space=row["space"],
        subject_id=ref_str(row["subject"]),
        object_id=opt_ref_str(row.get("object")),
        object_literal=row.get("object_literal"),
        kind=row["kind"],
        category=row.get("category"),
        confidence=float(row.get("confidence", 1.0)),
        salience=float(row.get("salience", 0.5)),
        valid_from=opt_datetime(row.get("valid_from")),
        valid_to=opt_datetime(row.get("valid_to")),
        recorded_at=to_datetime(row["recorded_at"]),
        invalidated_at=opt_datetime(row.get("invalidated_at")),
        superseded_by=opt_ref_str(row.get("superseded_by")),
        supersedes=opt_ref_str(row.get("supersedes")),
        status=FactStatus(row.get("status", "active")),
        source_kind=SourceKind(row.get("source_kind", "extraction")),
        flags=list(row.get("flags") or []),
        access_count=int(row.get("access_count", 0)),
        embedding_model=row.get("embedding_model"),
        metadata=plain(row.get("metadata") or {}),
    )
