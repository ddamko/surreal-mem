"""Build the embedder and the extraction model from settings (ADR-0009/0010)."""

from typing import TYPE_CHECKING

from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from surrealmem.extraction.adapters.pydantic_ai.extractor import PydanticAIExtractor
from surrealmem.extraction.adapters.pydantic_ai.summarizer import PydanticAISummarizer
from surrealmem.shared.infrastructure.inference.embedder import OpenAIEmbedder

if TYPE_CHECKING:
    from pydantic_ai.models import Model

    from surrealmem.shared.infrastructure.config import Settings

_COMPAT_PROFILE = OpenAIModelProfile(
    openai_supports_strict_tool_definition=False,
    openai_chat_supports_max_completion_tokens=False,
)


def build_embedder(settings: Settings) -> OpenAIEmbedder:
    return OpenAIEmbedder(
        base_url=settings.embed_base_url,
        model=settings.embed_model,
        dimension=settings.embed_dimension,
        api_key=settings.embed_api_key.get_secret_value() if settings.embed_api_key else None,
    )


def build_extraction_model(settings: Settings) -> Model:
    primary = OpenAIChatModel(
        settings.llm_model,
        provider=OpenAIProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else "local",
        ),
        profile=_COMPAT_PROFILE,
    )
    if settings.llm_fallback_base_url and settings.llm_fallback_model:
        fallback = OpenAIChatModel(
            settings.llm_fallback_model,
            provider=OpenAIProvider(
                base_url=settings.llm_fallback_base_url,
                api_key=(
                    settings.llm_fallback_api_key.get_secret_value()
                    if settings.llm_fallback_api_key
                    else "unset"
                ),
            ),
            profile=_COMPAT_PROFILE,
        )
        return FallbackModel(primary, fallback)
    return primary


def build_extractor(settings: Settings) -> PydanticAIExtractor:
    return PydanticAIExtractor(
        model=build_extraction_model(settings),
        extractor_name=f"llm:{settings.llm_model}",
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def build_summarizer(settings: Settings) -> PydanticAISummarizer:
    return PydanticAISummarizer(
        model=build_extraction_model(settings), name=f"llm:{settings.llm_model}"
    )
