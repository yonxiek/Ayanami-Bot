"""Лотерея: игроки покупают билеты, фонд копится, победитель забирает всё.

- `/lottery_start <цена> <длительность>` — запуск (длительность как у напоминаний: 30м, 2ч, 1д)
- `/lottery_buy <количество>` — покупка билетов
- `/lottery` — статус лотереи
"""

import asyncio
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.reminders import parse_duration
from db import Database
from ui_components import Colors


def _format_ends(ends_at: str) -> str:
    try:
        dt = datetime.fromisoformat(ends_at)
        return f"<t:{int(dt.timestamp())}:R>"
    except Exception:
        return ends_at


class Lottery(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def cog_load(self):
        try:
            self.bg_task = self.bot.loop.create_task(self._lottery_loop())
        except (RuntimeError, AttributeError):
            pass

    async def cog_unload(self):
        if hasattr(self, "bg_task"):
            self.bg_task.cancel()

    async def _lottery_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._check_draws()
            except Exception as e:
                print(f"Ошибка лотереи: {e}")
            await asyncio.sleep(30)

    async def _check_draws(self):
        now = datetime.now(timezone.utc).isoformat()
        for guild in self.bot.guilds:
            lottery = await self.db.get_lottery(str(guild.id))
            if not lottery or lottery["status"] != "active" or not lottery["ends_at"]:
                continue
            if lottery["ends_at"] > now:
                continue
            await self._draw(guild, lottery)

    async def _draw(self, guild: discord.Guild, lottery: dict):
        tickets = await self.db.get_lottery_tickets(str(guild.id))
        pool = lottery["prize_pool"]
        channel = guild.get_channel(int(lottery["channel_id"])) if lottery["channel_id"] else None
        await self.db.end_lottery(str(guild.id))

        embed = discord.Embed(
            title="🎉 Лотерея: розыгрыш!",
            color=Colors.SUCCESS,
        )
        if tickets and pool > 0:
            weighted = [int(t["user_id"]) for t in tickets for _ in range(int(t["tickets"]))]
            winner_id = random.choice(weighted)
            member = guild.get_member(winner_id)
            await self.db.update_user_balance(str(guild.id), str(winner_id), pool)
            embed.description = (
                f"🏆 Победитель: {member.mention if member else f'<@{winner_id}>'}!\n"
                f"💰 Выигрыш: **{pool}** монет"
            )
        else:
            embed.description = "Лотерея завершилась, но билетов никто не купил. Призовой фонд сгорел. 💀"

        if channel:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @app_commands.command(name="lottery", description="Статус активной лотереи на сервере")
    async def lottery_cmd(self, interaction: discord.Interaction):
        lottery = await self.db.get_lottery(str(interaction.guild.id))
        if not lottery or lottery["status"] != "active":
            return await interaction.response.send_message(
                "🎟 В данный момент лотерея не активна.", ephemeral=True
            )
        tickets = await self.db.get_lottery_tickets(str(interaction.guild.id))
        participants = sum(1 for t in tickets if t["tickets"] > 0)
        my = next((t for t in tickets if t["user_id"] == str(interaction.user.id)), None)
        embed = discord.Embed(
            title="🎟 Лотерея",
            color=Colors.MAIN,
        )
        embed.add_field(name="💸 Билет", value=f"{lottery['ticket_price']} монет", inline=True)
        embed.add_field(name="💰 Фонд", value=f"{lottery['prize_pool']} монет", inline=True)
        embed.add_field(name="👥 Участников", value=str(participants), inline=True)
        embed.add_field(name="⏳ Розыгрыш", value=_format_ends(lottery["ends_at"]), inline=False)
        embed.add_field(name="🎫 Ваших билетов", value=str(my["tickets"] if my else 0), inline=True)
        await interaction.response.send_message(
            embed=embed,
            content="Купить: `/lottery_buy <количество>`",
            ephemeral=False,
        )

    @app_commands.command(name="lottery_start", description="Запустить лотерею (роль модератора)")
    @app_commands.default_permissions(manage_channels=True)
    async def lottery_start_cmd(self, interaction: discord.Interaction, цена_билета: int, длительность: str):
        if цена_билета < 1:
            return await interaction.response.send_message("❌ Цена билета должна быть ≥ 1.", ephemeral=True)
        delta = parse_duration(длительность)
        if not delta:
            return await interaction.response.send_message(
                "❌ Не понимаю длительность. Примеры: `30м`, `2ч`, `1д`.", ephemeral=True
            )
        if delta.total_seconds() < 60:
            return await interaction.response.send_message("❌ Минимум — 1 минута.", ephemeral=True)

        ends_at = (datetime.now(timezone.utc) + delta).isoformat()
        channel_id = str(interaction.channel.id) if interaction.channel else ""
        await self.db.set_lottery(str(interaction.guild.id), цена_билета, ends_at, channel_id)

        embed = discord.Embed(
            title="🎟 Лотерея запущена!",
            description=(
                f"**Цена билета:** {цена_билета} монет\n"
                f"**Розыгрыш:** {_format_ends(ends_at)}\n\n"
                f"Покупай билеты: `/lottery_buy` и забери весь фонд 🏆"
            ),
            color=Colors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="lottery_buy", description="Купить билеты лотереи")
    async def lottery_buy_cmd(self, interaction: discord.Interaction, количество: int = 1):
        количество = max(1, min(количество, 1000))
        lottery = await self.db.get_lottery(str(interaction.guild.id))
        if not lottery or lottery["status"] != "active":
            return await interaction.response.send_message(
                "❌ Лотерея не активна. Запусти через `/lottery_start`.", ephemeral=True
            )
        ok = await self.db.buy_lottery_tickets(
            str(interaction.guild.id), str(interaction.user.id), количество, lottery["ticket_price"]
        )
        if not ok:
            return await interaction.response.send_message(
                f"❌ Недостаточно монет. Нужно: {количество * lottery['ticket_price']}.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            f"✅ Куплено билетов: **{количество}** ({количество * lottery['ticket_price']} монет). Удачи! 🍀",
            ephemeral=True,
        )

    @commands.command(name="lottery")
    async def lottery_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.lottery_cmd.callback(self, InteractionAdapter(ctx))


async def setup(bot):
    await bot.add_cog(Lottery(bot))