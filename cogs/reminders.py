import asyncio
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors

MAX_ACTIVE_REMINDERS = 25

DURATION_RE = re.compile(r'^\s*(\d+)\s*(с|сек|секунд|м|мин|минут|ч|час|часов|д|дн|дней)?\s*$', re.IGNORECASE)


def parse_duration(text: str) -> timedelta | None:
    m = DURATION_RE.match(text)
    if not m:
        return None
    value = int(m.group(1))
    unit = (m.group(2) or "м").lower()
    if unit in ("с", "сек", "секунд"):
        return timedelta(seconds=value)
    if unit in ("м", "мин", "минут"):
        return timedelta(minutes=value)
    if unit in ("ч", "час", "часов"):
        return timedelta(hours=value)
    if unit in ("д", "дн", "дней"):
        return timedelta(days=value)
    return None


def format_remind_at(remind_at: str) -> str:
    try:
        dt = datetime.fromisoformat(remind_at)
        return f"<t:{int(dt.timestamp())}:R>"
    except Exception:
        return remind_at


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def cog_load(self):
        try:
            self.bg_task = self.bot.loop.create_task(self._reminder_loop())
        except (RuntimeError, AttributeError):
            pass

    async def cog_unload(self):
        if hasattr(self, "bg_task"):
            self.bg_task.cancel()

    async def _reminder_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._process_due()
                await self.db.clear_expired_reminders()
            except Exception as e:
                print(f"Ошибка напоминаний: {e}")
            await asyncio.sleep(30)

    async def _process_due(self):
        due = await self.db.get_due_reminders()
        for rem in due:
            await self._deliver(rem)
            await self.db.mark_reminder_done(rem["id"])

    async def _deliver(self, rem):
        guild = self.bot.get_guild(int(rem["guild_id"])) if rem["guild_id"] else None
        user = guild.get_member(int(rem["user_id"])) if guild else self.bot.get_user(int(rem["user_id"]))
        target_channel = None
        if rem["channel_id"] and guild:
            target_channel = guild.get_channel(int(rem["channel_id"]))

        embed = discord.Embed(
            title="⏰ Напоминание",
            description=rem["text"] or "…",
            color=Colors.MAIN,
        )
        embed.set_footer(text=f"Создано {format_remind_at(rem['remind_at'])}")

        if target_channel is not None:
            try:
                at = f"<@{rem['user_id']}>" if user else ""
                await target_channel.send(content=at or None, embed=embed)
                return
            except Exception:
                pass
        if user:
            try:
                await user.send(embed=embed)
            except Exception:
                pass

    @app_commands.command(name="remind", description="Напомнить через время (например: 10м, 2ч, 1д)")
    @app_commands.describe(время="Через сколько: 30с / 10м / 2ч / 1д", текст="Что напомнить")
    async def remind(self, interaction: discord.Interaction, время: str, текст: str):
        if not interaction.guild:
            return
        delta = parse_duration(время)
        if not delta:
            return await interaction.response.send_message(
                "❌ Не понимаю время. Примеры: `30с`, `10м`, `2ч`, `1д` (`\\d` = минуты).",
                ephemeral=True
            )
        if delta < timedelta(seconds=5):
            return await interaction.response.send_message("❌ Минимум — 5 секунд.", ephemeral=True)

        user_id = str(interaction.user.id)
        active = await self.db.get_active_reminder_count(user_id)
        if active >= MAX_ACTIVE_REMINDERS:
            return await interaction.response.send_message(
                f"❌ У вас уже {active} активных напоминаний (максимум {MAX_ACTIVE_REMINDERS}).",
                ephemeral=True
            )

        remind_at = (datetime.now(timezone.utc) + delta).isoformat()
        await self.db.add_reminder(
            str(interaction.guild.id), user_id,
            interaction.channel.id if interaction.channel else None,
            remind_at, текст.strip()
        )
        await interaction.response.send_message(
            f"✅ Напомню **{format_remind_at(remind_at)}**: «{текст.strip()}»",
            ephemeral=True
        )
        await award_reminder_achievement(interaction)

    @app_commands.command(name="reminders", description="Список активных напоминаний")
    async def reminders(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await self.db.get_user_reminders(str(interaction.user.id))
        if not rows:
            return await interaction.followup.send("📭 Активных напоминаний нет.", ephemeral=True)
        lines = []
        for r in rows:
            lines.append(f"**#{r['id']}** · {format_remind_at(r['remind_at'])} — «{r['text']}»")
        embed = discord.Embed(
            title="⏰ Мои напоминания",
            description="\n".join(lines[:25]),
            color=Colors.MAIN,
        )
        embed.set_footer(text="Удалить: /remind_remove id")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="remind_remove", description="Удалить напоминание по ID")
    @app_commands.describe(id="ID из /reminders")
    async def remind_remove(self, interaction: discord.Interaction, id: int):
        ok = await self.db.delete_reminder(id, str(interaction.user.id))
        if ok:
            await interaction.response.send_message(f"✅ Напоминание **#{id}** удалено.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Напоминание **#{id}** не найдено.", ephemeral=True)

    @commands.command(name="reminders")
    async def reminders_prefix(self, ctx):
        await self.reminders.callback(self, InteractionAdapter(ctx))

    @commands.command(name="remind")
    async def remind_prefix(self, ctx, время: str, *, текст: str):
        await self.remind.callback(self, InteractionAdapter(ctx), время, текст)

    @commands.command(name="remind_remove")
    async def remind_remove_prefix(self, ctx, id: int):
        await self.remind_remove.callback(self, InteractionAdapter(ctx), id)


async def award_reminder_achievement(interaction: discord.Interaction):
    from cogs.achievements import award_achievement
    await award_achievement(
        Database(), str(interaction.guild.id), str(interaction.user.id),
        "reminder_1", interaction.user
    )


async def setup(bot):
    await bot.add_cog(Reminders(bot))