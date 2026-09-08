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
PREFIX: str = get("PREFIX", ",") or ","

#: Путь к файлу SQLite базы данных
DB_URL: str = get("DB_URL", "data/bot.db") or "data/bot.db"

#: Вебхук для отправки ошибок (необязательный)
ERROR_WEBHOOK_URL: str = get("ERROR_WEBHOOK_URL", "") or ""

# --- Внешние сервисы (опционально) ---
#: API-ключ Bloxlink для связи Discord -> Roblox (необязательный)
BLOXLINK_API_KEY: str = get("BLOXLINK_API_KEY", "") or ""

#: Вебхук для «снайпа» / событий (необязательный)
SNIPE_WEBHOOK_URL: str = get("SNIPE_WEBHOOK_URL", "") or ""


def require_token() -> str:
    """Вернуть токен или поднять ошибку, если он не задан."""
    if not TOKEN:
        raise RuntimeError(
            "Переменная окружения TOKEN не задана. "
            "Создайте файл `.env` и укажите TOKEN (см. `.env.example`)."
        )
    return TOKEN
