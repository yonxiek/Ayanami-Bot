"""AFK-система: /afk <причина>, уведомление при упоминании, авто-снятие.

Префиксные команды используют ту же логику через `InteractionAdapter`.
"""

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from ui_components import Colors


def _format_since(since: str | None) -> str:
    try:
        dt = datetime.fromisoformat(since)
        return f"<t:{int(dt.timestamp())}:R>"
    except Exception:
        return "недавно"


class Afk(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(name="afk", description="Уйти в AFK (автоматически снимется при возвращении)")
    @app_commands.describe(причина="Причина ухода (необязательно)")
    async def afk_cmd(self, interaction: discord.Interaction, причина: str = "Без причины"):
        if not interaction.guild:
            return
        await self.db.set_afk(str(interaction.guild.id), str(interaction.user.id), причина.strip())
        embed = discord.Embed(
            title="😴 AFK",
            description=f"**{interaction.user.name}**, ты в AFK. Напиши любое сообщение, чтобы вернуться.",
            color=Colors.WARNING,
        )
        embed.add_field(name="Причина", value=причина.strip() or "—", inline=False)
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        guild_id = str(message.guild.id)
        author_id = str(message.author.id)

        # Снимаем AFK, когда пользователь снова пишет в чат
        if await self.db.get_afk(guild_id, author_id):
            await self.db.clear_afk(guild_id, author_id)
            embed = discord.Embed(
                title="🙂 Возвращение",
                description=f"{message.author.mention} вернулся! AFK снят.",
                color=Colors.SUCCESS,
            )
            try:
                await message.channel.send(embed=embed)
            except discord.HTTPException:
                pass

        # Предупреждаем о тех, кто в AFK
        for user in message.mentions:
            if user == message.author or user.bot:
                continue
            afk = await self.db.get_afk(guild_id, str(user.id))
            if not afk:
                continue
            embed = discord.Embed(
                title="😴 В AFK",
                description=f"**{user.mention}** сейчас в AFK: **{afk['reason'] or '—'}**",
                color=Colors.WARNING,
            )
            embed.set_footer(text=f"Ушёл {_format_since(afk.get('since'))}")
            try:
                await message.reply(embed=embed)
            except discord.HTTPException:
                pass

    @commands.command(name="afk")
    async def afk_prefix(self, ctx, *, причина: str = "Без причины"):
        from prefix_adapter import InteractionAdapter
        await self.afk_cmd.callback(self, InteractionAdapter(ctx), причина)


async def setup(bot):
    await bot.add_cog(Afk(bot))