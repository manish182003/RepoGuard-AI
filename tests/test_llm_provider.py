import pytest
from app.llm.provider import (
    BaseLLMProvider,
    FakeLLMProvider,
    GroqProvider,
    LLMAuthenticationError,
    LLMInvalidRequestError,
    LLMMessage,
    LLMRateLimitError,
)


@pytest.mark.asyncio
async def test_fake_llm_provider():
    provider = FakeLLMProvider(response_content={"summary": "test", "hypotheses": []})
    messages = [
        LLMMessage(role="system", content="You are a helper"),
        LLMMessage(role="user", content="Hello"),
    ]

    response = await provider.generate(messages)

    assert response.model == "fake-model"
    assert '"summary": "test"' in response.content
    assert len(provider.call_history) == 1
    assert provider.call_history[0] == messages


def test_token_estimation():
    provider = FakeLLMProvider()
    text = "Hello world! This is a test snippet."
    tokens = provider.estimate_tokens(text)
    assert tokens > 0
    assert tokens == len(text) // 4


def test_groq_provider_missing_api_key(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", "")

    with pytest.raises(LLMAuthenticationError):
        GroqProvider(api_key=None)


@pytest.mark.asyncio
async def test_cloudflare_provider_missing_credentials(monkeypatch):
    from app.core.config import settings
    from app.llm.provider import CloudflareProvider

    monkeypatch.setattr(settings, "cloudflare_account_id", None)
    monkeypatch.setattr(settings, "cloudflare_api_token", None)
    provider = CloudflareProvider(account_id=None, api_token=None)
    with pytest.raises(LLMAuthenticationError):
        await provider.generate([LLMMessage(role="user", content="hello")])


@pytest.mark.asyncio
async def test_cloudflare_provider_success(monkeypatch):
    from app.llm.provider import CloudflareProvider
    import httpx

    provider = CloudflareProvider(
        account_id="fake_account",
        api_token="fake_token",
        model="@cf/qwen/qwen2.5-coder-32b-instruct",
    )

    class MockResponse:
        status_code = 200
        text = '{"result": {"response": "test answer", "usage": {"prompt_tokens": 15, "completion_tokens": 8, "neurons": 1.2}}}'
        def json(self):
            return {
                "result": {
                    "response": "test answer",
                    "usage": {"prompt_tokens": 15, "completion_tokens": 8, "neurons": 1.2},
                }
            }

    async def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    resp = await provider.generate([LLMMessage(role="user", content="hello")])
    assert resp.content == "test answer"
    assert resp.model == "@cf/qwen/qwen2.5-coder-32b-instruct"
    assert resp.prompt_tokens == 15
    assert resp.completion_tokens == 8


@pytest.mark.asyncio
async def test_cloudflare_provider_rate_limit(monkeypatch):
    from app.llm.provider import CloudflareProvider
    import httpx

    provider = CloudflareProvider(
        account_id="fake_account",
        api_token="fake_token",
    )

    class Mock429Response:
        status_code = 429
        text = "Too Many Requests"

    async def mock_post(*args, **kwargs):
        return Mock429Response()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(LLMRateLimitError):
        await provider.generate([LLMMessage(role="user", content="hello")])


@pytest.mark.asyncio
async def test_groq_fallback_to_cloudflare(monkeypatch):
    from app.llm.provider import GroqProvider, LLMResponse

    provider = GroqProvider(api_key="fake-groq-key")

    class MockPrimaryClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    raise Exception("Rate limit reached: 429 TPM exceeded")

    class MockCloudflareProvider:
        model = "@cf/qwen/qwen2.5-coder-32b-instruct"
        async def generate(self, messages, response_format=None, temperature=0.0):
            return LLMResponse(
                content='{"action": "done"}',
                model="@cf/qwen/qwen2.5-coder-32b-instruct",
                prompt_tokens=20,
                completion_tokens=5,
            )

    provider.client = MockPrimaryClient()
    provider.cloudflare_provider = MockCloudflareProvider()

    res = await provider.generate([LLMMessage(role="user", content="investigate")])
    assert res.content == '{"action": "done"}'
    assert res.model == "@cf/qwen/qwen2.5-coder-32b-instruct"

