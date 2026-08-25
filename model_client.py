"""
Thin wrapper so planner.py, locator_engine.py, and verifier.py all go
through one place, and never know or care which provider is behind it.

Two independent toggles in .env:

  LLM_PROVIDER          -> "groq" | "azure" | "deepseek"   (text/planning calls)
  VISION_LLM_PROVIDER    -> "groq" | "azure"                 (vision calls)

DeepSeek's chat models do not accept image input, so it is not a valid
choice for VISION_LLM_PROVIDER - attempting to use it raises a clear error
rather than silently failing.

Provider notes:
  - Groq: uses the AsyncGroq client. Also needs two quirks handled that
    don't apply to the others: reasoning models emit <think> blocks that
    must be hidden/stripped, and its vision models are more reliable
    without a separate "system" role.
  - Azure OpenAI: uses AsyncAzureOpenAI. The "model" param must be your
    DEPLOYMENT NAME (set in Azure AI/OpenAI Studio), not the underlying
    model name like "gpt-4.1".
  - DeepSeek: OpenAI-compatible API, so it uses AsyncOpenAI pointed at
    DeepSeek's base_url. The "model" param is DeepSeek's own model name.
"""

import json
import re

from openai import AsyncOpenAI, AsyncAzureOpenAI
from openai import BadRequestError as OpenAIBadRequestError
from groq import AsyncGroq
from groq import BadRequestError as GroqBadRequestError

from config import settings

MAX_TOKENS = 4096

_clients: dict = {}  # one cached client instance per provider name


def _token_kwarg_name(provider: str) -> str:
    # Groq's API (mirroring newer OpenAI reasoning-model conventions) wants
    # max_completion_tokens; plain chat-completions models (Azure/DeepSeek)
    # want max_tokens.
    return "max_completion_tokens" if provider == "groq" else "max_tokens"


def _get_groq_client():
    if not settings.groq_api_key:
        raise RuntimeError(
            "Missing GROQ_API_KEY. Set LLM_PROVIDER and/or VISION_LLM_PROVIDER=groq "
            "and fill this in your .env."
        )
    if "groq" not in _clients:
        _clients["groq"] = AsyncGroq(api_key=settings.groq_api_key)
    return _clients["groq"]


def _get_azure_client():
    missing = [
        name for name, val in [
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
        ] if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing Azure OpenAI config: {', '.join(missing)}. "
            f"Set LLM_PROVIDER and/or VISION_LLM_PROVIDER=azure and fill these in your .env."
        )
    if "azure" not in _clients:
        _clients["azure"] = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
    return _clients["azure"]


def _get_deepseek_client():
    if not settings.deepseek_api_key:
        raise RuntimeError(
            "Missing DEEPSEEK_API_KEY. Set LLM_PROVIDER=deepseek and fill this in your .env."
        )
    if "deepseek" not in _clients:
        _clients["deepseek"] = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    return _clients["deepseek"]


def _resolve_text_provider():
    provider = settings.llm_provider
    if provider == "groq":
        return provider, _get_groq_client(), settings.groq_model
    if provider == "azure":
        return provider, _get_azure_client(), settings.azure_openai_deployment
    if provider == "deepseek":
        return provider, _get_deepseek_client(), settings.deepseek_model
    raise RuntimeError(f"Unknown LLM_PROVIDER '{provider}'. Use 'groq', 'azure', or 'deepseek'.")


def _resolve_vision_provider():
    provider = settings.vision_llm_provider
    if provider == "groq":
        return provider, _get_groq_client(), settings.groq_vision_model
    if provider == "azure":
        model = settings.azure_openai_vision_deployment or settings.azure_openai_deployment
        return provider, _get_azure_client(), model
    if provider == "deepseek":
        raise RuntimeError(
            "DeepSeek's chat models do not support image input, so it can't be "
            "used for VISION_LLM_PROVIDER. Set VISION_LLM_PROVIDER=groq or azure instead."
        )
    raise RuntimeError(f"Unknown VISION_LLM_PROVIDER '{provider}'. Use 'groq' or 'azure'.")


def _strip_think_blocks(raw: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>")[0].strip()
    return cleaned


def _extract_json(raw: str) -> dict:
    if not raw or not raw.strip():
        raise ValueError("Empty response from model")

    cleaned = _strip_think_blocks(raw)
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError("Empty response from model after stripping reasoning")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError(f"Could not parse JSON from model output: {raw!r}")


async def _complete(provider: str, client, model: str, messages: list,
                     force_json: bool = True, hide_reasoning: bool = True) -> str:
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        _token_kwarg_name(provider): MAX_TOKENS,
    }
    if force_json:
        kwargs["response_format"] = {"type": "json_object"}
    if provider == "groq" and hide_reasoning:
        kwargs["reasoning_format"] = "hidden"

    try:
        completion = await client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content
    except (GroqBadRequestError, OpenAIBadRequestError):
        if provider == "groq" and hide_reasoning:
            return await _complete(provider, client, model, messages, force_json=force_json, hide_reasoning=False)
        if force_json:
            return await _complete(provider, client, model, messages, force_json=False, hide_reasoning=False)
        raise


async def _call_and_parse(provider: str, client, model: str, messages: list) -> dict:
    raw = await _complete(provider, client, model, messages, force_json=True)
    try:
        return _extract_json(raw)
    except ValueError:
        retry_messages = messages + [
            {"role": "assistant", "content": raw or ""},
            {"role": "user", "content": "That was not valid JSON. Reply again with ONLY a single "
                                         "valid JSON object, no <think> tags, no markdown fences, no other text."},
        ]
        raw2 = await _complete(provider, client, model, retry_messages, force_json=False)
        return _extract_json(raw2)


async def achat_json(system_prompt: str, user_prompt: str) -> dict:
    """Text-only planning/reasoning call. Provider chosen via LLM_PROVIDER."""
    provider, client, model = _resolve_text_provider()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return await _call_and_parse(provider, client, model, messages)


async def achat_vision_json(system_prompt: str, user_prompt: str, image_b64: str) -> dict:
    """
    Vision call (screenshot -> JSON). Provider chosen via VISION_LLM_PROVIDER.
    Raises clearly if VISION_LLM_PROVIDER=deepseek, since that's not supported.
    """
    provider, client, model = _resolve_vision_provider()

    if provider == "groq":
        # Groq's vision models are more reliable with everything folded into
        # one user text block alongside the image, no separate system role.
        combined_text = f"{system_prompt.strip()}\n\n{user_prompt.strip()}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": combined_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            },
        ]
    else:
        # Azure OpenAI vision-capable deployments (e.g. gpt-4.1) work fine
        # with a normal system + user(text+image) shape.
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            },
        ]

    return await _call_and_parse(provider, client, model, messages)
