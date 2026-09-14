"""Счётчики каналов: голосовые каналы с актуальной статистикой сервера.

Конфигурация хранится в guild_config: {"channel_counters": {id: "members"|"users"|"bots"|"online"|"voice"}}
"""

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from ui_components import Colors

TYPES = {
    "members": "👥 Участники",
    "users": "🧑 Люди",
    "bots": "🤖 Боты",
    "online": "🟢 Онлайн",
    "voice": "🔊 В голосе",
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

    @app_commands.command(name="counter_add", description="Создать счётчик в голосовом канале (роль модератора)")
    @app_commands.describe(канал="Голосовой канал для счётчика", тип="Тип счётчика: members/users/bots/online/voice")
    @app_commands.default_permissions(manage_channels=True)
    async def counter_add_cmd(self, interaction: discord.Interaction, канал: discord.VoiceChannel, тип: str):
        if тип not in TYPES:
            help_text = ", ".join(f"`{k}`" for k in TYPES)
            return await interaction.response.send_message(
                f"❌ Тип должен быть одним из: {help_text}", ephemeral=True
            )
        counters = await self._counters(str(interaction.guild.id))
        counters[str(канал.id)] = тип
        await self._set_counters(str(interaction.guild.id), counters)
        await self._update_one(interaction.guild, str(канал.id), тип)
        embed = discord.Embed(
            title="📊 Счётчик добавлен",
            description=f"Канал {канал.mention} теперь показывает: **{TYPES[тип]}**",
            color=Colors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="counter_remove", description="Убрать счётчик из канала (роль модератора)")
    @app_commands.describe(канал="Голосовой канал, из которого убрать счётчик")
    @app_commands.default_permissions(manage_channels=True)
    async def counter_remove_cmd(self, interaction: discord.Interaction, канал: discord.VoiceChannel):
        counters = await self._counters(str(interaction.guild.id))
        if str(канал.id) not in counters:
            return await interaction.response.send_message(
                f"❌ В канале {канал.mention} нет счётчика.", ephemeral=True
            )
        del counters[str(канал.id)]
        await self._set_counters(str(interaction.guild.id), counters)
        await interaction.response.send_message(
            f"✅ Счётчик убран из {канал.mention}.", ephemeral=True
        )

    @app_commands.command(name="counter_list", description="Список активных счётчиков")
    async def counter_list_cmd(self, interaction: discord.Interaction):
        counters = await self._counters(str(interaction.guild.id))
        if not counters:
            return await interaction.response.send_message(
                "❌ Счётчиков нет. Добавь через `/counter_add`.", ephemeral=True
            )
        lines = []
        for channel_id, counter_type in counters.items():
            channel = interaction.guild.get_channel(int(channel_id))
            name = channel.mention if channel else f"`{channel_id}`"
            value = self._compute(interaction.guild, counter_type)
            lines.append(f"{name} — **{TYPES[counter_type]}**: {value}")
        embed = discord.Embed(
            title="📊 Счётчики",
            description="\n".join(lines),
            color=Colors.MAIN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ChannelCounters(bot))