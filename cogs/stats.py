import asyncio
import io
import os
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

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


def _load_font(size: int, bold: bool = False):
    path = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render_activity_chart(week_keys: list[str], series: dict[str, list[int]], display_name: str):
    W, H = 900, 430
    img = Image.new("RGB", (W, H), (43, 45, 49))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(26, bold=True)
    small_font = _load_font(14)
    legend_font = _load_font(18)

    colors = {
        "messages": (43, 108, 176),
        "voice_minutes": (155, 89, 182),
        "commands": (230, 126, 34),
    }
    labels = {"messages": "Сообщения", "voice_minutes": "Голос (мин)", "commands": "Команды"}

    draw.text((24, 16), f"Активность за {len(week_keys)} недель — {display_name}",
              font=title_font, fill=(245, 245, 245))

    x = W - 280
    for key, col in colors.items():
        draw.rectangle([x, 14, x + 16, 30], fill=col)
        draw.text((x + 22, 12), labels[key], font=legend_font, fill=(220, 220, 220))
        x += 16 + draw.textlength(labels[key], font=legend_font) + 24

    left, top, right, bottom = 70, 70, W - 30, H - 55
    max_val = 0
    for vals in series.values():
        max_val = max(max_val, *(vals or [0]))
    max_val = max(1, max_val)

    for step_frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = bottom - step_frac * (bottom - top)
        draw.line([left, y, right, y], fill=(60, 62, 68))
        val = int(round(step_frac * max_val))
        draw.text((12, y - 8), str(val), font=small_font, fill=(160, 160, 160))

    group_width = (right - left) / len(week_keys)
    bar_width = 18
    gap = 6
    total = 3 * bar_width + 2 * gap

    for i, key in enumerate(week_keys):
        cx = left + group_width * i + group_width / 2
        wk = key.split("-W", 1)[-1]
        draw.text((cx, bottom + 8), f"W{wk}", font=small_font, fill=(200, 200, 200), anchor="mm")

        for j, (metric, vals) in enumerate(series.items()):
            v = vals[i]
            bar_h = (v / max_val) * (bottom - top)
            if bar_h < 2 and v > 0:
                bar_h = 2
            bx = cx - total / 2 + j * (bar_width + gap)
            draw.rounded_rectangle([bx, bottom - bar_h, bx + bar_width, bottom],
                                   radius=4, fill=colors[metric])
            if v > 0:
                label = str(v)
                tw = draw.textlength(label, font=small_font)
                if bar_h > 18:
                    draw.text((bx + bar_width / 2 - tw / 2, bottom - bar_h + 3), label,
                              font=small_font, fill=(245, 245, 245))
                else:
                    draw.text((bx + bar_width / 2 - tw / 2, bottom - bar_h - 16), label,
                              font=small_font, fill=(220, 220, 220))

    return img


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
            except Exception as e:
                print(f"Ошибка очистки статистики: {e}")
            await asyncio.sleep(3600)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        guild_id, user_id = str(message.guild.id), str(message.author.id)
        await self.db.increment_weekly(guild_id, user_id, current_week_key(), "messages")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        if before.channel is None and after.channel is not None:
            self.track_voice_join(member.guild.id, member.id)
        elif before.channel is not None and after.channel is None:
            minutes, _ = self.track_voice_leave(member.guild.id, member.id)
            if minutes > 0:
                await self.db.increment_weekly(str(member.guild.id), str(member.id), current_week_key(), "voice_minutes", minutes)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if not interaction.guild:
            return
        await self.db.increment_weekly(
            str(interaction.guild.id), str(interaction.user.id), current_week_key(), "commands"
        )

    @app_commands.command(name="stats", description="График активности за последние 8 недель")
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

        cursor = await self.db.conn.execute(
            "SELECT total_messages, total_voice_minutes, total_commands, reputation FROM users "
            "WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id))
        urow = await cursor.fetchone()

        img = render_activity_chart(keys, series, target.display_name)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)

        embed = discord.Embed(title=f"📊 Активность: {target.display_name}", color=Colors.MAIN)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.add_field(name="💬 Сообщений (8 нед.)", value=str(sum(series["messages"])), inline=True)
        total_voice = sum(series["voice_minutes"])
        embed.add_field(name="🎙 Голос (8 нед.)", value=f"{total_voice} мин" if total_voice < 60 else f"≈{total_voice // 60} ч {total_voice % 60} мин", inline=True)
        embed.add_field(name="⌨️ Команд (8 нед.)", value=str(sum(series["commands"])), inline=True)
        if urow:
            embed.add_field(name="🏅 Сообщений всего", value=str(urow["total_messages"]), inline=True)
            tm = urow["total_voice_minutes"]
            embed.add_field(name="⏱ В голосе всего", value=f"{tm // 60} ч {tm % 60} мин", inline=True)
            embed.add_field(name="⭐ Репутация", value=str(urow["reputation"]), inline=True)
        embed.set_image(url="attachment://stats.png")
        embed.set_footer(text=f"ID: {target.id}")
        if member:
            embed.set_author(name="Статистика участника", icon_url=target.display_avatar.url)
        else:
            embed.set_author(name="Ваша статистика", icon_url=target.display_avatar.url)
        await interaction.followup.send(embed=embed, file=discord.File(buf, filename="stats.png"))

    @commands.command(name="stats")
    async def stats_prefix(self, ctx, member: discord.Member = None):
        from prefix_adapter import InteractionAdapter
        await self.stats.callback(self, InteractionAdapter(ctx), member)



async def setup(bot):
    await bot.add_cog(WeeklyStats(bot))