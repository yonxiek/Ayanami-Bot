"""ИИ-суммаризация: /summarize сжимает последние сообщения канала через Gemini."""

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ai_client import complete
from db import Database
from ui_components import Colors

MAX_MESSAGES = 200
MAX_CHARS = 18000


class Summarize(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(name="summarize", description="Краткая сводка последних сообщений канала (ИИ)")
    async def summarize_cmd(self, interaction: discord.Interaction, сообщений: int = 50):
        if not interaction.channel or not interaction.guild:
            return
        сообщений = max(5, min(сообщений, MAX_MESSAGES))

        await interaction.response.defer(ephemeral=True)

        lines = []
        async for message in interaction.channel.history(limit=None):
            if not message.content:
                continue
            prefix = "Бот" if message.author.bot else message.author.display_name
            lines.append(f"[{prefix}] {message.content}")
            if len(lines) >= сообщений:
                break
            if sum(len(l) for l in lines) > MAX_CHARS:
                break

        if not lines:
            return await interaction.followup.send(
                "📭 В этом канале нет текстовых сообщений для сводки.", ephemeral=True
            )

        history = ("\n".join(lines))[-MAX_CHARS:]
        now = datetime.now(timezone.utc)
        system_prompt = (
            "Ты — ассистент для краткой сводки чата Discord. Напиши сжатый пересказ "
            "на русском, в виде буллетов, самое важное. Без лишней воды."
        )
        summary = await complete(
            system_prompt,
            [{"role": "user", "content": f"Сводка сообщений за последнее время:\n{history}"}],
            temperature=0.3,
            max_tokens=800,
            timeout=40,
        )

        if not summary:
            return await interaction.followup.send(
                "❌ Не удалось получить ответ от ИИ (ключ не настроен или ошибка API).",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="📝 Сводка чата",
            description=summary[:4096],
            color=Colors.MAIN,
        )
        embed.set_footer(text=f"По {len(lines)} сообщениям · {now.strftime('%d.%m %H:%M')}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="summarize")
    async def summarize_prefix(self, ctx, сообщений: int = 50):
        from prefix_adapter import InteractionAdapter
        await self.summarize_cmd.callback(self, InteractionAdapter(ctx), сообщений)

    @app_commands.command(name="translate", description="Перевод текста на нужный язык (ИИ)")
    @app_commands.describe(текст="Текст для перевода", язык="На какой язык (например: английский, японский)")
    async def translate_cmd(self, interaction: discord.Interaction, текст: str, язык: str = "английский"):
        await interaction.response.defer()

        system_prompt = (
            "Ты — точный переводчик. Отвечай ТОЛЬКО переводом, без пояснений, "
            "кавычек и лишнего текста."
        )
        translated = await complete(
            system_prompt,
            [{"role": "user", "content": f"Переведи на язык: {язык}.\nТекст:\n{текст}"}],
            temperature=0.2,
            max_tokens=800,
            timeout=40,
        )

        if not translated:
            return await interaction.followup.send(
                "❌ Не удалось получить перевод от ИИ (ключ не настроен или ошибка API).",
                ephemeral=True,
            )

        embed = discord.Embed(
            title=f"🌐 Перевод: {язык}",
            description=translated[:4096],
            color=Colors.MAIN,
        )
        embed.add_field(name="Оригинал", value=текст[:1024], inline=False)
        embed.set_footer(text=f"Перевёл {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    @commands.command(name="translate")
    async def translate_prefix(self, ctx, *, текст: str):
        from prefix_adapter import InteractionAdapter
        await self.translate_cmd.callback(self, InteractionAdapter(ctx), текст)


async def setup(bot):
    await bot.add_cog(Summarize(bot))