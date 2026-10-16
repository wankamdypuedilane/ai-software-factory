import pytest


@pytest.fixture(autouse=True)
def _no_provider_retry_wait(monkeypatch):
    """Provider retries wait tens of seconds in real use; never in tests."""

    monkeypatch.setattr(
        "ai_factory.openai_provider.OpenAIProvider._sleep",
        lambda self, seconds: None,
    )
