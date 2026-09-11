"""Статическая проверка загрузки когов без запуска бота.

Повторяет логику load_cogs() из main.py, но без токена и БД:
импортирует каждый модуль из cogs/ и проверяет наличие setup() корутины.

Запуск:
    python load_check.py

Код возврата: 0 — все коги OK, 1 — есть ошибки (для CI).
"""

import importlib
import inspect
import json
import os
import sys

COGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cogs")


def get_cog_modules() -> list[str]:
    """Возвращает список имён модулей когов (cogs.<имя>), исключая __init__."""
    names = []
    for filename in sorted(os.listdir(COGS_DIR)):
        if filename.endswith(".py") and filename != "__init__.py":
            names.append(f"cogs.{filename[:-3]}")
    return names


def check_module(module_name: str) -> list[str]:
    """Импортирует модуль и возвращает список ошибок."""
    errors = []
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        errors.append(f"ImportError: {type(e).__name__}: {e}")
        return errors

    setup_func = getattr(module, "setup", None)
    if setup_func is None:
        errors.append("нет функции setup()")
    elif not inspect.iscoroutinefunction(setup_func):
        errors.append("setup() не является корутиной (нужен async def setup)")

    return errors


def main() -> int:
    modules = get_cog_modules()
    results = {}
    failed = 0

    for module_name in modules:
        errors = check_module(module_name)
        short_name = module_name.split(".")[-1]
        if errors:
            results[short_name] = errors
            failed += 1
            print(f"  ✗ {short_name}: {errors[0]}")
        else:
            results[short_name] = []
            print(f"  ✓ {short_name}")

    if failed:
        print(f"\nИтого: {len(modules) - failed} когов OK, {failed} с ошибками")
        print(json.dumps({"failed": results}, ensure_ascii=False, indent=2))
        return 1

    print(f"\nВсе {len(modules)} когов загружаются без ошибок")
    return 0


if __name__ == "__main__":
    sys.exit(main())