import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from ui_components import Colors
from voice_tracker import VoiceTrackerMixin


def current_week_key() -> str:
    iso = datetime.now().isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def last_week_keys(n: int = 8) -> list[str]:
    today = datetime.now(timezone.utc).date()
    keys = []
    for i in range(n - 1, -1, -1):
        d = today - timedelta(weeks=i)
        iso = d.isocalendar()
        keys.append(f"{iso[0]}-W{iso[1]:02d}")
    return keys


_SPARK = "▁▂▃▄▅▆▇█"
_BAR_FULL = "█"
_BAR_EMPTY = "░"


def sparkline(values: list[int]) -> str:
    """Мини-график тренда: 8 символов ▁▂▃▄▅▆▇█ (нормировка по максимуму серии)."""
    if not values:
        return ""
    mx = max(values)
    if mx <= 0:
        return _SPARK[0] * len(values)
    return "".join(_SPARK[min(len(_SPARK) - 1, int((v / mx) * (len(_SPARK) - 1)))] for v in values)


def hbar(value: int, max_val: int) -> str:
    """Горизонтальная полоска из 10 сегментов.""" ""
    if max_val <= 0:
        return _BAR_EMPTY * 10
    filled = round((value / max_val) * 10)
    return _BAR_FULL * filled + _BAR_EMPTY * (10 - filled)


def fmt_voice(minutes: int) -> str:
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes} мин"
    h, m = divmod(minutes, 60)
    return f"{h} ч {m} мин"


def fmt_num(value: int) -> str:
    return f"{value:,}".replace(",", " ")


class StatsView(discord.ui.View):
    def __init__(self, keys, series, dow, mention, extra_fields, avatar_url, guild_icon, user_id, member_flag):
        super().__init__(timeout=180)
        self.keys = keys
        self.series = series
        self.dow = dow
        self.mention = mention
        self.extra_fields = extra_fields
        self.avatar_url = avatar_url
        self.guild_icon = guild_icon
        self.user_id = user_id
        self.member_flag = member_flag
        self.mode = "weekly"

    def build(self):
        embed = discord.Embed(color=Colors.MAIN)
        if self.guild_icon:
            embed.set_thumbnail(url=self.guild_icon)
        embed.set_footer(text=f"ID: {self.user_id}")
        embed.set_author(
            name="Статистика участника" if self.member_flag else "Ваша статистика",
            icon_url=self.avatar_url,
        )

        messages = self.series["messages"]
        voice = self.series["voice_minutes"]
        commands = self.series["commands"]

        if self.mode == "weekly":
            embed.title = "📊 Активность"
            weeks = " · ".join(f"`W{self.keys[-i].split('-W', 1)[-1]}`" for i in range(len(self.keys), 0, -1))
            embed.description = f"{self.mention}\nПоследние **{len(self.keys)} недель** · {weeks}"
            embed.add_field(name="💬 Сообщения", value=fmt_num(sum(messages)), inline=True)
            embed.add_field(name="🎙 Голос (мин)", value=fmt_voice(sum(voice)), inline=True)
            embed.add_field(name="⌨️ Команды", value=fmt_num(sum(commands)), inline=True)
            if sum(messages + voice + commands) == 0:
                embed.add_field(
                    name="ℹ️",
                    value="Данных пока нет — статистика копится с этого дня.",
                    inline=False,
                )
            else:
                lines = [
                    f"`{sparkline(messages)}`  **💬** соообщений",
                    f"`{sparkline(voice)}`  **🎙** минут в голосе",
                    f"`{sparkline(commands)}`  **⌨️** команд",
                ]
                embed.add_field(name="📈 Динамика по неделям", value="\n".join(lines), inline=False)
        else:
            embed.title = "📆 Дни недели"
            embed.description = f"{self.mention}\nАктивность за **28 дней**: сообщения + голос ÷ 10 + команды"
            if sum(self.dow) == 0:
                embed.add_field(
                    name="ℹ️",
                    value="Данных пока нет — статистика копится с этого дня.",
                    inline=False,
                )
            else:
                labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                maxd = max(self.dow)
                lines = [
                    f"{d} `{hbar(val, maxd)}` **{fmt_num(val)}**"
                    for d, val in zip(labels, self.dow)
                ]
                embed.add_field(name="📆 По дням недели", value="\n".join(lines), inline=False)

        for label, value in self.extra_fields:
            embed.add_field(name=label, value=value, inline=True)
        return embed

    @discord.ui.button(label="Недели", emoji="📅", style=discord.ButtonStyle.primary, row=0)
    async def btn_weekly(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.mode = "weekly"
        await self._refresh(interaction)

    @discord.ui.button(label="Дни недели", emoji="📆", style=discord.ButtonStyle.secondary, row=0)
    async def btn_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.mode = "daily"
        await self._refresh(interaction)

    async def _refresh(self, interaction: discord.Interaction):
        embed = self.build()
        await interaction.response.edit_message(
            embed=embed, view=self,
            allowed_mentions=discord.AllowedMentions(users=False, everyone=False, roles=False),
        )


class WeeklyStats(VoiceTrackerMixin, commands.Cog):
    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        self.db = Database()

    async def cog_load(self):
        try:
            self.bg_task = self.bot.loop.create_task(self._prune_loop())
        except (RuntimeError, AttributeError):
            pass

    async def cog_unload(self):
        if hasattr(self, "bg_task"):
            self.bg_task.cancel()

    async def _prune_loop(self):
        await self.bot.wait_until_ready()
        self.restore_voice_sessions(self.bot)
        while not self.bot.is_closed():
            try:
                await self.db.prune_weekly_stats()
                await self.db.prune_daily_activity()
            except Exception as e:
                print(f"Ошибка очистки статистики: {e}")
            await asyncio.sleep(3600)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        guild_id, user_id = str(message.guild.id), str(message.author.id)
        today = datetime.now(timezone.utc).date().isoformat()
        await self.db.increment_weekly(guild_id, user_id, current_week_key(), "messages")
        await self.db.increment_daily(guild_id, user_id, today, "messages")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        if before.channel is None and after.channel is not None:
            self.track_voice_join(member.guild.id, member.id)
        elif before.channel is not None and after.channel is None:
            minutes, _ = self.track_voice_leave(member.guild.id, member.id)
            if minutes > 0:
                today = datetime.now(timezone.utc).date().isoformat()
                await self.db.increment_weekly(str(member.guild.id), str(member.id), current_week_key(), "voice_minutes", minutes)
                await self.db.increment_daily(str(member.guild.id), str(member.id), today, "voice_minutes", minutes)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if not interaction.guild:
            return
        today = datetime.now(timezone.utc).date().isoformat()
        await self.db.increment_weekly(
            str(interaction.guild.id), str(interaction.user.id), current_week_key(), "commands"
        )
        await self.db.increment_daily(
            str(interaction.guild.id), str(interaction.user.id), today, "commands"
        )

    @app_commands.command(name="stats", description="Статистика активности за 8 недель и по дням недели")
    @app_commands.describe(member="Участник (по умолчанию — вы)")
    async def stats(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        if target.bot:
            return await interaction.response.send_message(
                embed=discord.Embed(color=Colors.ERROR, description="❌ У ботов нет статистики."), ephemeral=True)
        await interaction.response.defer()

        guild_id, user_id = str(interaction.guild.id), str(target.id)
        keys = last_week_keys(8)
        placeholders = ",".join("?" * len(keys))
        cursor = await self.db.conn.execute(
            f"SELECT week_key, messages, voice_minutes, commands FROM weekly_stats "
            f"WHERE guild_id = ? AND user_id = ? AND week_key IN ({placeholders})",
            (guild_id, user_id, *keys))
        rows = await cursor.fetchall()
        data = {row['week_key']: row for row in rows}

        series = {
            "messages": [data.get(k)['messages'] if data.get(k) else 0 for k in keys],
            "voice_minutes": [data.get(k)['voice_minutes'] if data.get(k) else 0 for k in keys],
            "commands": [data.get(k)['commands'] if data.get(k) else 0 for k in keys],
        }
        dow = await self.db.get_daily_activity_by_dow(guild_id, user_id)

        cursor = await self.db.conn.execute(
            "SELECT total_messages, total_voice_minutes, total_commands, reputation FROM users "
            "WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id))
        urow = await cursor.fetchone()

        extra_fields = []
        if urow:
            extra_fields.append(("🏅 Сообщений всего", str(urow["total_messages"])))
            tm = urow["total_voice_minutes"]
            extra_fields.append(("⏱ В голосе всего", f"{tm // 60} ч {tm % 60} мин"))
            extra_fields.append(("⭐ Репутация", str(urow["reputation"])))

        view = StatsView(
            keys=keys, series=series, dow=dow,
            mention=target.mention, extra_fields=extra_fields,
            avatar_url=target.display_avatar.url,
            guild_icon=interaction.guild.icon.url if interaction.guild.icon else None,
            user_id=str(target.id), member_flag=bool(member),
        )
        embed = view.build()
        await interaction.followup.send(
            embed=embed, view=view,
            allowed_mentions=discord.AllowedMentions(users=False, everyone=False, roles=False),
        )

    @commands.command(name="stats")
    async def stats_prefix(self, ctx, member: discord.Member = None):
        from prefix_adapter import InteractionAdapter
        await self.stats.callback(self, InteractionAdapter(ctx), member)


async def setup(bot):
    await bot.add_cog(WeeklyStats(bot))