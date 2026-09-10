"""Централизованная конфигурация бота.

Все значения читаются из переменных окружения (файл `.env`).
Секреты (токены, ключи, вебхуки) НЕ должны храниться в коде —
только в `.env`, который не попадает в git.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Базовая директория проекта (родительская по отношению к этому файлу)
BASE_DIR = Path(__file__).resolve().parent

# Загружаем переменные окружения из .env рядом с проектом
load_dotenv(BASE_DIR / ".env")


def get(name: str, default: str | None = None) -> str | None:
    """Получить значение переменной окружения."""
    value = os.getenv(name)
    return value if value is not None else default


def get_int(name: str, default: int = 0) -> int:
    """Получить целочисленное значение переменной окружения."""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def get_bool(name: str, default: bool = False) -> bool:
    """Получить булево значение переменной окружения.

    В `1`, `true`, `yes`, `on` — True; всё остальное — False.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --- Основные настройки ---
#: Токен Discord-бота (обязателен)
TOKEN: str | None = get("TOKEN")

#: Префикс для текстовых (не slash) команд
PREFIX: str = get("PREFIX", "!") or "!"

#: Путь к файлу SQLite базы данных
DB_URL: str = get("DB_URL", "data/bot.db") or "data/bot.db"

#: Вебхук для отправки ошибок (необязательный)
ERROR_WEBHOOK_URL: str = get("ERROR_WEBHOOK_URL", "") or ""

# --- Внешние сервисы (опционально) ---
#: API-ключ Bloxlink для связи Discord -> Roblox (необязательный)
BLOXLINK_API_KEY: str = get("BLOXLINK_API_KEY", "") or ""

#: Вебхук для «снайпа» / событий (необязательный)
SNIPE_WEBHOOK_URL: str = get("SNIPE_WEBHOOK_URL", "") or ""

# --- Чат с ИИ (опционально) ---
#: Провайдер ИИ: gemini, openai, deepseek
AI_PROVIDER: str = get("AI_PROVIDER", "gemini") or "gemini"

#: Бесплатный ключ Google AI Studio: https://aistudio.google.com/apikey
GEMINI_API_KEY: str = get("GEMINI_API_KEY", "") or ""
#: Модель Gemini (на случай смены доступных моделей)
GEMINI_MODEL: str = get("GEMINI_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash"

#: OpenAI API-ключ (опционально)
OPENAI_API_KEY: str = get("OPENAI_API_KEY", "") or ""
#: Модель OpenAI
OPENAI_MODEL: str = get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"

#: DeepSeek API-ключ (опционально)
DEEPSEEK_API_KEY: str = get("DEEPSEEK_API_KEY", "") or ""
#: Модель DeepSeek
DEEPSEEK_MODEL: str = get("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat"

# --- Музыка (Lavalink, опционально) ---
#: Хост Lavalink-сервера (пусто = музыка отключена)
LAVALINK_HOST: str = get("LAVALINK_HOST", "") or ""
#: Порт Lavalink-сервера
LAVALINK_PORT: int = get_int("LAVALINK_PORT", 2333)
#: Пароль Lavalink-сервера
LAVALINK_PASSWORD: str = get("LAVALINK_PASSWORD", "youshallnotpass") or "youshallnotpass"

# --- Веб-дашборд (опционально) ---
#: Секретный ключ для веб-дашборда
DASHBOARD_SECRET: str = get("DASHBOARD_SECRET", "") or ""
#: Хост для веб-дашборда
DASHBOARD_HOST: str = get("DASHBOARD_HOST", "127.0.0.1") or "127.0.0.1"
#: Порт для веб-дашборда
DASHBOARD_PORT: int = get_int("DASHBOARD_PORT", 8080)


def require_token() -> str:
    """Вернуть токен или поднять ошибку, если он не задан."""
    if not TOKEN:
        raise RuntimeError(
            "Переменная окружения TOKEN не задана. "
            "Создайте файл `.env` и укажите TOKEN (см. `.env.example`)."
        )
    return TOKEN
