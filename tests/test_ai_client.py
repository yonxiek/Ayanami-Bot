import ai_client
from ai_client import normalize_provider, DEFAULT_MODELS


def test_normalize_valid():
    assert normalize_provider("gemini") == "gemini"
    assert normalize_provider("openai") == "openai"
    assert normalize_provider("deepseek") == "deepseek"
    assert normalize_provider("  OpenAI ") == "openai"


def test_normalize_invalid_falls_back():
    assert normalize_provider("giga") == ai_client.DEFAULT_PROVIDER
    assert normalize_provider("") == ai_client.DEFAULT_PROVIDER
    assert normalize_provider(None) == ai_client.DEFAULT_PROVIDER


def test_default_models_present():
    assert "gemini" in DEFAULT_MODELS
    assert "openai" in DEFAULT_MODELS
    assert "deepseek" in DEFAULT_MODELS


def test_models_nonempty():
    for model in DEFAULT_MODELS.values():
        assert model


async def test_complete_returns_none_without_key(monkeypatch):
    monkeypatch.setattr(ai_client, "_api_key_for", lambda _: "")
    result = await ai_client.complete("system", [{"role": "user", "content": "hi"}])
    assert result is None


async def test_openai_payload_shapes(monkeypatch):
    """Проверяем, что для OpenAI-совместимых провайдеров собирается правильный body."""
    captured = {}

    class FakeResponse:
        def __init__(self):
            self.status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def text(self):
            return ""

        async def json(self):
            return {"choices": [{"message": {"content": "привет"}}]}

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(ai_client.aiohttp, "ClientSession", FakeSession)
    monkeypatch.setattr(ai_client, "_api_key_for", lambda p: "key-" + p)

    result = await ai_client.complete(
        "system", [{"role": "user", "content": "hi"}], provider="openai", max_tokens=40)

    assert result == "привет"
    assert captured["url"] == ai_client.OPENAI_COMPAT_URL
    assert captured["headers"]["Authorization"] == "Bearer key-openai"
    assert captured["json"]["model"] == DEFAULT_MODELS["openai"]
    assert captured["json"]["messages"][0] == {"role": "system", "content": "system"}
    assert captured["json"]["messages"][1] == {"role": "user", "content": "hi"}


async def test_gemini_payload_shapes(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self):
            self.status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def text(self):
            return ""

        async def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Ответ Gemini"}]}}]}

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(ai_client.aiohttp, "ClientSession", FakeSession)
    monkeypatch.setattr(ai_client, "_api_key_for", lambda p: "gemkey")

    result = await ai_client.complete(
        "system", [{"role": "user", "content": "hi"}], provider="gemini", max_tokens=20)

    assert result == "Ответ Gemini"
    assert "utils" in captured["url"] or "gemini" in captured["url"]
    assert captured["json"]["systemInstruction"]["parts"][0]["text"] == "system"
    assert captured["json"]["contents"][0]["parts"][0]["text"] == "hi"