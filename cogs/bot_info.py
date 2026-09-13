"""Мониторинг бота: /botinfo (аптайм, память, пинг, статистика)."""

import platform
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from ui_components import Colors


def _rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024
    except Exception:
        pass
    return 0.0


class BotInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(name="botinfo", description="Статистика и состояние бота")
    async def botinfo_cmd(self, interaction: discord.Interaction):
        start = getattr(self.bot, "start_time", None)
        if start:
            uptime = f"<t:{int(start.timestamp())}:R>"
        else:
            uptime = "—"

        try:
            latency = round(self.bot.latency * 1000)
            ping = f"{latency} мс"
        except Exception:
            ping = "—"

        member_count = sum(len(g.members) for g in self.bot.guilds)

        embed = discord.Embed(
            title="🤖 Информация о боте",
            color=Colors.INFO,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="🕐 Аптайм", value=uptime, inline=True)
        embed.add_field(name="📶 Пинг", value=ping, inline=True)
        embed.add_field(name="💾 Память (RSS)", value=f"{_rss_mb():.0f} МБ", inline=True)
        embed.add_field(name="🖥 Серверов", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="👥 Участников", value=str(member_count), inline=True)
        embed.add_field(
            name="🧩 Команд",
            value=f"{len(self.bot.tree.get_commands())} слэш · {len(self.bot.commands)} префиксных",
            inline=True,
        )
        embed.add_field(name="🐍 Python", value=platform.python_version(), inline=True)
        embed.add_field(name="📦 discord.py", value=discord.__version__, inline=True)

        await interaction.response.send_message(embed=embed)

    @commands.command(name="botinfo")
    async def botinfo_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.botinfo_cmd.callback(self, InteractionAdapter(ctx))


async def setup(bot):
    await bot.add_cog(BotInfo(bot))