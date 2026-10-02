"""REST routes for retrieval: context packs and search with score breakdowns."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from surrealmem.retrieval.application import Retriever
from surrealmem.retrieval.domain import ContextPack, RetrievalQuery, SearchResult


def _retriever(request: Request) -> Retriever:
    return request.app.state.retriever


RetrieverDep = Annotated[Retriever, Depends(_retriever)]
router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/context")
async def get_context(query: RetrievalQuery, retriever: RetrieverDep) -> ContextPack:
    return await retriever.context(query)


@router.post("/search")
async def search(query: RetrievalQuery, retriever: RetrieverDep) -> SearchResult:
    return await retriever.search(query)
