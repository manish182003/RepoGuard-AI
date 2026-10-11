from abc import ABC, abstractmethod
import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_response: dict[str, Any] = Field(default_factory=dict)


class LLMError(Exception):
    """Base exception for LLM provider errors."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when LLM rate limit or TPM limit is exceeded."""
    pass


class LLMAuthenticationError(LLMError):
    """Raised when API key or auth fails."""
    pass


class LLMInvalidRequestError(LLMError):
    """Raised when request payload is malformed or exceeds context limit."""
    pass


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        response_format: dict[str, str] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate a response from the LLM provider."""
        pass

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text snippet (~4 chars per token rule of thumb)."""
        return max(1, len(text) // 4)


class GroqProvider(BaseLLMProvider):
    """LLM Provider implementation supporting Groq / OpenRouter async API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        client: Any = None,
    ):
        if settings.groq_api_key:
            self.api_key = api_key or settings.groq_api_key
            self.model = model or settings.groq_model or "qwen/qwen3.8-27b"
            self.base_url = base_url or "https://api.groq.com/openai/v1"
        elif settings.openrouter_api_key:
            self.api_key = api_key or settings.openrouter_api_key
            self.model = model or settings.openrouter_model or "openrouter/free"
            self.base_url = base_url or "https://openrouter.ai/api/v1"
        else:
            self.api_key = api_key or ""
            self.model = model or "qwen/qwen3.8-27b"
            self.base_url = base_url or "https://api.groq.com/openai/v1"

        if client is not None:
            self.client = client
            self.fallback_client = None
            self.fallback_model = None
        else:
            if not self.api_key:
                raise LLMAuthenticationError(
                    "Neither GROQ_API_KEY nor OPENROUTER_API_KEY is configured."
                )

            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                default_headers={
                    "HTTP-Referer": "https://github.com/RepoGuard-AI",
                    "X-Title": "RepoGuard AI",
                },
            )

            # Configure fallback client
            if settings.groq_api_key:
                self.fallback_client = AsyncOpenAI(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=settings.groq_api_key,
                )
                self.fallback_model = "openai/gpt-oss-120b"
            else:
                self.fallback_client = None
                self.fallback_model = None

            # Configure Cloudflare Workers AI Fallback Provider
            if settings.cloudflare_account_id and settings.cloudflare_api_token:
                self.cloudflare_provider = CloudflareProvider(
                    account_id=settings.cloudflare_account_id,
                    api_token=settings.cloudflare_api_token,
                    model=settings.cloudflare_model,
                )
            else:
                self.cloudflare_provider = None

            # Configure OpenRouter Fallback Client
            if settings.openrouter_api_key:
                self.openrouter_client = AsyncOpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=settings.openrouter_api_key,
                    default_headers={
                        "HTTP-Referer": "https://github.com/RepoGuard-AI",
                        "X-Title": "RepoGuard AI",
                    },
                )
                self.openrouter_model = "qwen/qwen-2.5-coder-32b-instruct"
            else:
                self.openrouter_client = None
                self.openrouter_model = None

    async def generate(
        self,
        messages: list[LLMMessage],
        response_format: dict[str, str] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
        }

        if response_format and response_format.get("type") == "json_object":
            if not any("json" in m["content"].lower() for m in formatted_messages):
                formatted_messages[0]["content"] += "\nProvide output in valid JSON format."
            kwargs["response_format"] = response_format

        try:
            try:
                response = await self.client.chat.completions.create(**kwargs)
            except Exception as exc:
                err_msg = str(exc).lower()
                if ("json_validate_failed" in err_msg or "tool_use_failed" in err_msg or "failed to generate json" in err_msg) and "response_format" in kwargs:
                    logger.warning("LLM response format error. Retrying without explicit response_format...")
                    kwargs.pop("response_format", None)
                    response = await self.client.chat.completions.create(**kwargs)
                else:
                    raise exc
        except Exception as exc:
            err_msg = str(exc).lower()
            if ("rate_limit" in err_msg or "429" in err_msg or "tpm" in err_msg or "not a valid model id" in err_msg):
                # Fallback 1: Cloudflare Workers AI
                if self.cloudflare_provider:
                    logger.warning(
                        f"Primary LLM issue ({exc}). Automatically falling back to Cloudflare Workers AI ({self.cloudflare_provider.model})..."
                    )
                    try:
                        return await self.cloudflare_provider.generate(
                            messages=messages,
                            response_format=response_format,
                            temperature=temperature,
                        )
                    except Exception as cf_exc:
                        logger.warning(f"Cloudflare Workers AI fallback failed ({cf_exc}). Trying secondary fallback...")

                # Fallback 2: Secondary model (Groq / OpenRouter)
                if self.fallback_client:
                    logger.warning(f"Automatically falling back to ({self.fallback_model})...")
                    try:
                        # Truncate context to 1500 chars per message to respect Groq 8K TPM limits
                        groq_messages = [
                            {"role": msg.role, "content": msg.content[:1500] if len(msg.content) > 1500 else msg.content}
                            for msg in messages
                        ]
                        if response_format and response_format.get("type") == "json_object":
                            if not any("json" in m["content"].lower() for m in groq_messages):
                                groq_messages[0]["content"] += "\nProvide output in valid JSON format."

                        fallback_kwargs = {
                            "model": self.fallback_model,
                            "messages": groq_messages,
                            "temperature": temperature,
                        }
                        if response_format:
                            fallback_kwargs["response_format"] = response_format

                        try:
                            response = await self.fallback_client.chat.completions.create(**fallback_kwargs)
                        except Exception as fb_exc:
                            fb_err = str(fb_exc).lower()
                            if ("json_validate_failed" in fb_err or "tool_use_failed" in fb_err or "failed to generate json" in fb_err) and "response_format" in fallback_kwargs:
                                logger.warning("Fallback LLM response format error. Retrying without explicit response_format...")
                                fallback_kwargs.pop("response_format", None)
                                response = await self.fallback_client.chat.completions.create(**fallback_kwargs)
                            else:
                                raise fb_exc
                    except Exception as fb_exc:
                        logger.warning(f"Secondary Groq fallback failed ({fb_exc}). Trying OpenRouter fallback...")

                # Fallback 3: OpenRouter
                if getattr(self, "openrouter_client", None):
                    logger.warning(f"Automatically falling back to OpenRouter ({self.openrouter_model})...")
                    try:
                        openrouter_messages = [
                            {"role": msg.role, "content": msg.content}
                            for msg in messages
                        ]
                        or_kwargs = {
                            "model": self.openrouter_model,
                            "messages": openrouter_messages,
                            "temperature": temperature,
                        }
                        if response_format:
                            or_kwargs["response_format"] = response_format
                        response = await self.openrouter_client.chat.completions.create(**or_kwargs)
                        choice = response.choices[0]
                        content = choice.message.content or ""
                        return LLMResponse(
                            content=content,
                            model=self.openrouter_model,
                            prompt_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
                            completion_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
                            raw_response={"id": getattr(response, "id", None)},
                        )
                    except Exception as or_exc:
                        logger.warning(f"OpenRouter fallback failed: {or_exc}")
                        raise LLMRateLimitError(f"All LLM providers hit rate limits / failed: {or_exc}") from or_exc

                if not getattr(self, "openrouter_client", None):
                    raise LLMRateLimitError(f"All LLM providers hit rate limits: {exc}") from exc
            elif "rate_limit" in err_msg or "429" in err_msg or "tpm" in err_msg:
                raise LLMRateLimitError(f"Rate limit exceeded: {exc}") from exc
            elif "auth" in err_msg or "401" in err_msg or "403" in err_msg:
                raise LLMAuthenticationError(f"Authentication failed: {exc}") from exc
            elif "context_length" in err_msg or "400" in err_msg:
                raise LLMInvalidRequestError(f"Invalid request or context length: {exc}") from exc
            else:
                raise LLMError(f"LLM API call failed: {exc}") from exc

        choice = response.choices[0]
        content = choice.message.content or ""

        prompt_tokens = 0
        completion_tokens = 0
        if getattr(response, "usage", None):
            prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0

        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw_response={"id": getattr(response, "id", None)},
        )


class CloudflareProvider(BaseLLMProvider):
    """LLM Provider implementation for Cloudflare Workers AI."""

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        model: str | None = None,
        timeout: float = 45.0,
    ):
        self.account_id = account_id or settings.cloudflare_account_id
        self.api_token = api_token or settings.cloudflare_api_token
        self.model = model or settings.cloudflare_model or "@cf/qwen/qwen2.5-coder-32b-instruct"
        self.timeout = timeout

    async def generate(
        self,
        messages: list[LLMMessage],
        response_format: dict[str, str] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.account_id or not self.api_token:
            raise LLMAuthenticationError("Cloudflare Account ID or API Token is not configured.")

        import httpx

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        if response_format and response_format.get("type") == "json_object":
            if not any("json" in m["content"].lower() for m in formatted_messages):
                formatted_messages[0]["content"] += "\nProvide output in valid JSON format."

        payload: dict[str, Any] = {
            "messages": formatted_messages,
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 429:
                raise LLMRateLimitError(f"Cloudflare Workers AI rate limit exceeded: {resp.text}")
            if resp.status_code in (401, 403):
                raise LLMAuthenticationError(f"Cloudflare authentication failed: {resp.text}")
            if resp.status_code != 200:
                raise LLMError(f"Cloudflare Workers AI returned status {resp.status_code}: {resp.text}")

            data = resp.json()
            result = data.get("result", {})

            content = ""
            if "response" in result:
                resp_val = result["response"]
                if isinstance(resp_val, dict):
                    content = json.dumps(resp_val)
                else:
                    content = str(resp_val)
            elif "choices" in result and result["choices"]:
                content = result["choices"][0].get("message", {}).get("content", "")
            else:
                content = json.dumps(result)

            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            return LLMResponse(
                content=content,
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                raw_response={"id": data.get("id"), "neurons": usage.get("neurons")},
            )


class FakeLLMProvider(BaseLLMProvider):
    """Fake LLM Provider for deterministic testing without external network calls."""

    def __init__(self, response_content: str | dict[str, Any] | None = None):
        if isinstance(response_content, dict):
            self.response_content = json.dumps(response_content)
        elif isinstance(response_content, str):
            self.response_content = response_content
        else:
            self.response_content = json.dumps({
                "summary": "Fake investigation completed.",
                "hypotheses": []
            })
        self.call_history: list[list[LLMMessage]] = []

    async def generate(
        self,
        messages: list[LLMMessage],
        response_format: dict[str, str] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.call_history.append(messages)
        return LLMResponse(
            content=self.response_content,
            model="fake-model",
            prompt_tokens=100,
            completion_tokens=50,
        )
