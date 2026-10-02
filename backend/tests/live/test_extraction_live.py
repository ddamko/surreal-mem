"""Live evaluation against the local inference services (``pytest -m live``).

Needs the llama-server units running (``just inference``). Reports recall of expected entities and
relationship kinds over the fixture set and fails below the floor, so prompt or model changes get a
number instead of a feeling.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from surrealmem.bootstrap.inference import build_embedder, build_extractor
from surrealmem.extraction.domain import ExtractionContext
from surrealmem.shared.domain import normalize_name
from surrealmem.shared.infrastructure.config import Settings

pytestmark = pytest.mark.live

EVAL_SET = Path(__file__).resolve().parents[1] / "fixtures" / "extraction_eval.json"
RECALL_FLOOR = 0.75


def _settings() -> Settings:
    return Settings()


def _reachable(url: str) -> bool:
    try:
        return httpx.get(url.rstrip("/") + "/models", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="module")
def settings() -> Settings:
    s = _settings()
    if not _reachable(s.llm_base_url) or not _reachable(s.embed_base_url):
        pytest.skip("inference services are not reachable; run `just inference`")
    return s


async def test_embedding_dimension(settings: Settings) -> None:
    embedder = build_embedder(settings)
    try:
        [doc] = await embedder.embed(["Derek Damko works at WWS."])
        [query] = await embedder.embed_queries(["where does derek work"])
    finally:
        await embedder.close()
    assert len(doc) == settings.embed_dimension == len(query)


async def test_extraction_recall(settings: Settings) -> None:
    cases: list[dict[str, Any]] = json.loads(EVAL_SET.read_text())
    extractor = build_extractor(settings)
    hits = total = 0
    report: list[str] = []
    for case in cases:
        context = ExtractionContext(
            message_id="message:eval",
            conversation_id="conversation:eval",
            space="work",
            agent_id="eval",
            role=case["role"],
            content=case["content"],
            sent_at=datetime(2026, 10, 2, tzinfo=UTC),
            known_kinds=["WORKS_AT", "LIVES_IN", "USES", "PREFERS", "MAINTAINS", "LOCATED_IN"],
        )
        result = await extractor.extract(context)
        names = {normalize_name(e.name) for e in result.entities}
        names |= {normalize_name(a) for e in result.entities for a in e.aliases}
        kinds = {r.kind for r in result.relations} | {f.kind for f in result.facts}
        for expected in case.get("expect_entities", []):
            total += 1
            ok = any(normalize_name(expected) in n or n in normalize_name(expected) for n in names)
            hits += ok
            report.append(f"{case['id']}: entity {expected!r} {'ok' if ok else 'MISSING'}")
        for kind in case.get("expect_kinds", []) + case.get("expect_fact_kinds", []):
            total += 1
            ok = kind in kinds
            hits += ok
            report.append(f"{case['id']}: kind {kind} {'ok' if ok else 'MISSING'}")
        if case.get("expect_empty"):
            total += 1
            ok = result.is_empty
            hits += ok
            report.append(f"{case['id']}: empty {'ok' if ok else 'NOISE ' + str(result.entities)}")
        if "expect_valid_from" in case:
            total += 1
            ok = any(
                (f.valid_from or "").startswith(case["expect_valid_from"]) for f in result.facts
            )
            hits += ok
            report.append(f"{case['id']}: valid_from {'ok' if ok else 'MISSING'}")
    recall = hits / total if total else 1.0
    print("\n".join(report))
    print(f"recall {hits}/{total} = {recall:.2f}")
    assert recall >= RECALL_FLOOR, f"recall {recall:.2f} below {RECALL_FLOOR}"
