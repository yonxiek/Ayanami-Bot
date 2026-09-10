"""Единый клиент для ИИ-провайдеров (Gemini / OpenAI / DeepSeek).

Позволяет переключать провайдера через переменные окружения без изменения
логики когов. Поддерживает текстовые завершения (чат и модерация).
"""

import aiohttp
import json
import config

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_COMPAT_URL = "https://api.openai.com/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

PROVIDERS = ("gemini", "openai", "deepseek")

#: Провайдер по умолчанию определяется из конфига
DEFAULT_PROVIDER = config.get("AI_PROVIDER", "gemini").strip().lower()
if DEFAULT_PROVIDER not in PROVIDERS:
    DEFAULT_PROVIDER = "gemini"

#: Модели по умолчанию для каждого провайдера
DEFAULT_MODELS = {
    "gemini": config.get("GEMINI_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash",
    "openai": config.get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
    "deepseek": config.get("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat",
}


def _api_key_for(provider: str) -> str:
    if provider == "openai":
        return config.get("OPENAI_API_KEY", "") or ""
    if provider == "deepseek":
        return config.get("DEEPSEEK_API_KEY", "") or ""
    return config.GEMINI_API_KEY


def normalize_provider(provider: str | None) -> str:
    """Привести значение к валидному провайдеру, иначе вернуть DEFAULT_PROVIDER."""
    if provider and provider.strip().lower() in PROVIDERS:
        return provider.strip().lower()
    return DEFAULT_PROVIDER


async def _call_gemini(session: aiohttp.ClientSession, api_key: str, model: str,
                       system_prompt: str, messages: list[dict], temperature: float,
                       max_tokens: int) -> str | None:
    contents = [{"role": "user", "parts": [{"text": m["content"]}]} for m in messages]
    body = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    headers = {"Content-Type": "application/json"}
    url = GEMINI_URL.format(model=model)
    async with session.post(f"{url}?key={api_key}", json=body, headers=headers) as resp:
        if resp.status != 200:
            print(f"❌ Gemini API {resp.status}: {(await resp.text())[:300]}")
            return None
        data = await resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return ""


async def _call_openai_compat(session: aiohttp.ClientSession, url: str, api_key: str, model: str,
                              system_prompt: str, messages_raw: list[dict], temperature: float,
                              max_tokens: int) -> str | None:
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": m["role"] if m["role"] == "assistant" else "user", "content": m["content"]}
                 for m in messages_raw]
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    async with session.post(url, json=body, headers=headers) as resp:
        if resp.status != 200:
            print(f"❌ {url} API {resp.status}: {(await resp.text())[:300]}")
            return None
        data = await resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return ""


async def complete(system_prompt: str, messages: list[dict], *, timeout: float = 30,
                   provider: str | None = None, temperature: float = 0.9,
                   max_tokens: int = 250) -> str | None:
    """Единая точка вызова ИИ.

    messages — список {"role": "user"|"assistant", "content": str}.
    Возвращает текст ответа или None при ошибке/не настроенном ключе.
    """
    provider = normalize_provider(provider)
    api_key = _api_key_for(provider)
    if not api_key:
        return None
    model = DEFAULT_MODELS[provider]

    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=timeout_obj) as session:
        if provider == "gemini":
            return await _call_gemini(session, api_key, model, system_prompt, messages,
                                      temperature, max_tokens)
        if provider == "openai":
            return await _call_openai_compat(session, OPENAI_COMPAT_URL, api_key, model,
                                             system_prompt, messages, temperature, max_tokens)
        if provider == "deepseek":
            return await _call_openai_compat(session, DEEPSEEK_URL, api_key, model,
                                             system_prompt, messages, temperature, max_tokens)
    return None