"""Поиск участника по упоминанию, ID, username, display name или нику.

Используется в префиксных командах и модменю, чтобы участника можно было
указать любым из этих способов, а не только по ID или упоминанию.
"""

import re

import discord
from discord.ext import commands


def extract_id(text: str) -> int | None:
    """Извлекает ID из упоминания или голой строки с цифрами."""
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


def find_member(guild: discord.Guild, text: str) -> discord.Member | None:
    """Ищет участника по ID/упоминанию, затем по username/глобальному имени/нику.

    Сравнение имён — без учёта регистра и ведущего '@'.
    """
    text = text.strip()
    cid = extract_id(text)
    if cid:
        member = guild.get_member(cid)
        if member:
            return member
    query = text.lstrip("@").strip().lower()
    if not query:
        return None
    for member in guild.members:
        if (member.name.lower() == query
                or (member.nick and member.nick.lower() == query)
                or (member.global_name and member.global_name.lower() == query)
                or member.display_name.lower() == query):
            return member
    return None


class MemberSearch(commands.Converter):
    """Конвертер: участник на сервере по ID/упоминанию/username/display name/нику."""

    async def convert(self, ctx, argument: str):
        if ctx.guild:
            member = find_member(ctx.guild, argument)
            if member:
                return member
        raise commands.BadArgument(f"Участник «{argument}» не найден на сервере.")


class UserSearch(commands.Converter):
    """Конвертер: участник на сервере или глобальный пользователь (для банов/ЧС)."""

    async def convert(self, ctx, argument: str):
        if ctx.guild:
            member = find_member(ctx.guild, argument)
            if member:
                return member
        try:
            return await commands.UserConverter().convert(ctx, argument)
        except commands.BadArgument:
            raise commands.BadArgument(f"Пользователь «{argument}» не найден.") from None