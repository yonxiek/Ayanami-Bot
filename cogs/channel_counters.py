"""Счётчики каналов: голосовые каналы с актуальной статистикой сервера.

Конфигурация хранится в guild_config: {"channel_counters": {id: "members"|"users"|"bots"|"online"|"voice"}}
"""

import asyncio

import discord
from discord.ext import commands

from db import Database

TYPES = {
    "members": "👥 Участники",
    "users": "🧑 Люди",
    "bots": "🤖 Боты",
    "online": "🟢 Онлайн",
    "voice": "🔊 В голосе",
    "boost": "🛡️ Бусты",
    "boostlvl": "🚀 Уровень буста",
    "channels": "🗂️ Каналы",
    "roles": "🎭 Роли",
    "emoji": "😀 Эмодзи",
    "stickers": "🏷️ Стикеры",
}

LABEL_LIMIT = 80


class ChannelCounters(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def cog_load(self):
        try:
            self.bg_task = self.bot.loop.create_task(self._refresh_loop())
        except (RuntimeError, AttributeError):
            pass

    async def cog_unload(self):
        if hasattr(self, "bg_task"):
            self.bg_task.cancel()

    async def _refresh_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._refresh_all()
            except Exception as e:
                print(f"Ошибка счётчиков: {e}")
            await asyncio.sleep(1800)

    async def _counters(self, guild_id: str) -> dict[str, str]:
        cfg = await self.db.get_guild_config(guild_id)
        return cfg.get("channel_counters", {}) or {}

    async def _set_counters(self, guild_id: str, counters: dict):
        cfg = await self.db.get_guild_config(guild_id)
        cfg["channel_counters"] = counters
        await self.db.update_guild_config(guild_id, **cfg)

    def _compute(self, guild: discord.Guild, counter_type: str) -> int:
        if counter_type == "members":
            return len(guild.members)
        if counter_type == "users":
            return sum(1 for m in guild.members if not m.bot)
        if counter_type == "bots":
            return sum(1 for m in guild.members if m.bot)
        if counter_type == "online":
            statuses = ("online", "idle", "dnd")
            return sum(1 for m in guild.members if m.status in statuses)
        if counter_type == "voice":
            return sum(1 for vc in guild.voice_channels for _ in vc.members)
        if counter_type == "boost":
            return guild.premium_subscription_count
        if counter_type == "boostlvl":
            return guild.premium_tier
        if counter_type == "channels":
            return len(guild.channels)
        if counter_type == "roles":
            return len(guild.roles)
        if counter_type == "emoji":
            return len(guild.emojis)
        if counter_type == "stickers":
            return len(guild.stickers)
        return 0

    async def _update_one(self, guild: discord.Guild, channel_id: str, counter_type: str):
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return
        count = self._compute(guild, counter_type)
        base = TYPES.get(counter_type, "Счётчик")
        try:
            name = f"{base}: {count}"
            if channel.name != name:
                await channel.edit(name=name[:LABEL_LIMIT])
        except discord.Forbidden:
            pass

    async def _update_guild(self, guild: discord.Guild):
        counters = await self._counters(str(guild.id))
        for channel_id, counter_type in counters.items():
            try:
                await self._update_one(guild, channel_id, counter_type)
            except Exception:
                pass

    async def _refresh_all(self):
        for guild in self.bot.guilds:
            await self._update_guild(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self._update_guild(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self._update_guild(member.guild)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        await self._update_guild(member.guild)

    async def _add_counter(self, guild: discord.Guild, channel_id: int, counter_type: str) -> bool:
        if counter_type not in TYPES or guild.get_channel(channel_id) is None:
            return False
        counters = await self._counters(str(guild.id))
        counters[str(channel_id)] = counter_type
        await self._set_counters(str(guild.id), counters)
        await self._update_one(guild, str(channel_id), counter_type)
        return True

    async def _remove_counter(self, guild: discord.Guild, channel_id: int) -> bool:
        counters = await self._counters(str(guild.id))
        if str(channel_id) not in counters:
            return False
        del counters[str(channel_id)]
        await self._set_counters(str(guild.id), counters)
        return True

    async def _list_counters(self, guild: discord.Guild) -> list[tuple[str, str, int, discord.VoiceChannel | None]]:
        counters = await self._counters(str(guild.id))
        result = []
        for channel_id, counter_type in counters.items():
            channel = guild.get_channel(int(channel_id))
            name = channel.mention if isinstance(channel, discord.VoiceChannel) else f"`{channel_id}`"
            result.append((name, counter_type, self._compute(guild, counter_type), channel))
        return result


async def setup(bot):
    await bot.add_cog(ChannelCounters(bot))