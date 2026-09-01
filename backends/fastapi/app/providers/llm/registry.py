from app.config.settings import Settings
from app.core.errors import ProviderUnavailableError
from app.providers.llm.base import LLMProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai import OpenAILLMProvider


def build_llm_provider(app_settings: Settings) -> LLMProvider:
    if app_settings.llm_provider == "mock":
        return MockLLMProvider()
    if app_settings.llm_provider == "openai":
        if not app_settings.openai_api_key:
            raise ProviderUnavailableError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        return OpenAILLMProvider(
            api_key=app_settings.openai_api_key,
            base_url=app_settings.openai_base_url,
            model=app_settings.openai_model,
        )
    raise ProviderUnavailableError(f"unknown LLM_PROVIDER: {app_settings.llm_provider}")
