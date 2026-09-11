from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from cogs.achievements import award_achievement
from db import Database
from ui_components import Colors


class EventRSVPView(discord.ui.View):
    def __init__(self, event_id: int):
        super().__init__(timeout=None)
        self.event_id = event_id

    @discord.ui.button(label="Going", emoji="✅", style=discord.ButtonStyle.success, custom_id="event_going")
    async def going(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ServerEvents")
        if cog:
            await cog._rsvp(interaction, self.event_id, "going")

    @discord.ui.button(label="Maybe", emoji="❓", style=discord.ButtonStyle.secondary, custom_id="event_maybe")
    async def maybe(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ServerEvents")
        if cog:
            await cog._rsvp(interaction, self.event_id, "maybe")

    @discord.ui.button(label="Not Going", emoji="❌", style=discord.ButtonStyle.danger, custom_id="event_notgoing")
    async def not_going(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ServerEvents")
        if cog:
            await cog._rsvp(interaction, self.event_id, "not_going")


class ServerEvents(commands.Cog):
    """Система событий с регистрацией и RSVP."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def event_create(self, interaction: discord.Interaction, name: str, description: str = "",
                           time: str = None, channel: discord.TextChannel = None):
        target_channel = channel or interaction.channel

        starts_at = None
        if time:
            starts_at = self._parse_event_time(time)
            if not starts_at:
                return await interaction.response.send_message(
                    "❌ Не могу распознать время. Формат: `15.06 19:00`, `завтра 18:00`, `через 2ч`.", ephemeral=True
                )

        await self.db.conn.execute(
            "INSERT INTO server_events (guild_id, creator_id, channel_id, name, description, starts_at, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (str(interaction.guild.id), str(interaction.user.id), str(target_channel.id),
             name, description, starts_at.isoformat() if starts_at else None,
             datetime.now(timezone.utc).isoformat())
        )
        await self.db.conn.commit()

        cursor = await self.db.conn.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        event_id = row[0]

        time_text = f"<t:{int(starts_at.timestamp())}:F>" if starts_at else "Не указано"

        embed = discord.Embed(
            title=f"🎉 {name}",
            description=description or "Нет описания",
            color=Colors.SUCCESS,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="⏰ Время", value=time_text, inline=True)
        embed.add_field(name="📍 Канал", value=target_channel.mention, inline=True)
        embed.add_field(name="👤 Организатор", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"ID: {event_id}")

        view = EventRSVPView(event_id)
        msg = await target_channel.send(embed=embed, view=view)

        await self.db.conn.execute(
            "UPDATE server_events SET message_id = ? WHERE id = ?", (str(msg.id), event_id)
        )
        await self.db.conn.commit()

        await interaction.response.send_message(f"✅ Событие создано в {target_channel.mention}!", ephemeral=True)
        await award_achievement(self.db, str(interaction.guild.id), str(interaction.user.id), "first_event", interaction.user)

    async def event_list(self, interaction: discord.Interaction):
        """Список событий: предстоящие и последние прошедшие."""
        cursor = await self.db.conn.execute(
            "SELECT id, name, starts_at, creator_id, status FROM server_events "
            "WHERE guild_id = ? ORDER BY starts_at DESC LIMIT 25",
            (str(interaction.guild.id),)
        )
        rows = await cursor.fetchall()
        if not rows:
            return await interaction.response.send_message("📭 Событий ещё нет. Создайте первое!", ephemeral=True)

        now = datetime.now(timezone.utc)
        upcoming, past = [], []
        for r in rows:
            if r["starts_at"]:
                starts = datetime.fromisoformat(r["starts_at"])
                if starts >= now and r["status"] == "active":
                    upcoming.append((r, starts))
                elif starts < now:
                    past.append((r, starts))
            else:
                upcoming.append((r, None))

        upcoming.sort(key=lambda x: x[1] or datetime.max)
        past.sort(key=lambda x: x[1] or datetime.min, reverse=True)

        def fmt_event(r, starts):
            time_text = f"<t:{int(starts.timestamp())}:F>" if starts else "Без даты"
            status = "❌ отменено" if r["status"] == "cancelled" else ""
            return f"**{r['name']}** — {time_text} (от: <@{r['creator_id']}>) {status}".rstrip()

        lines = []
        if upcoming:
            lines.append("### 📅 Предстоящие")
            lines.extend(f"{fmt_event(r, s)} [`#{r['id']}`]" for r, s in upcoming[:5])
        if past:
            lines.append("\n### 🕰️ Прошедшие")
            lines.extend(f"`{discord.utils.format_dt(s, style='d')}` **{r['name']}** [`#{r['id']}`]" for r, s in past[:5])
        if not lines:
            lines.append("Нет событий для показа.")

        embed = discord.Embed(title="🎉 События сервера", description="\n".join(lines), color=Colors.MAIN)
        await interaction.response.send_message(embed=embed)

    async def event_cancel(self, interaction: discord.Interaction, event_id: int):
        cursor = await self.db.conn.execute(
            "SELECT creator_id, name FROM server_events WHERE id = ? AND guild_id = ?",
            (event_id, str(interaction.guild.id))
        )
        row = await cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Событие не найдено.", ephemeral=True)
        if row["creator_id"] != str(interaction.user.id) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только организатор или админ может отменить.", ephemeral=True)

        await self.db.conn.execute(
            "UPDATE server_events SET status = 'cancelled' WHERE id = ?", (event_id,)
        )
        await self.db.conn.commit()
        await interaction.response.send_message(f"✅ Событие **{row['name']}** отменено.")

    async def _rsvp(self, interaction: discord.Interaction, event_id: int, response_type: str):
        await interaction.response.defer(ephemeral=True)
        cursor = await self.db.conn.execute(
            "SELECT id, name, channel_id FROM server_events WHERE id = ? AND guild_id = ? AND status = 'active'",
            (event_id, str(interaction.guild.id))
        )
        row = await cursor.fetchone()
        if not row:
            return await interaction.followup.send("❌ Событие не найдено.", ephemeral=True)

        user_id = str(interaction.user.id)
        await self.db.conn.execute(
            "DELETE FROM event_rsvps WHERE event_id = ? AND user_id = ?", (event_id, user_id)
        )
        await self.db.conn.execute(
            "INSERT INTO event_rsvps (event_id, user_id, response, created_at) VALUES (?, ?, ?, ?)",
            (event_id, user_id, response_type, datetime.now(timezone.utc).isoformat())
        )
        await self.db.conn.commit()

        labels = {"going": "✅ Вы идёте!", "maybe": "❓ Может быть", "not_going": "❌ Не идёте"}
        await interaction.followup.send(labels.get(response_type, "Голос записан."), ephemeral=True)
        if response_type == "going":
            await award_achievement(self.db, str(interaction.guild.id), str(interaction.user.id), "event_rsvp", interaction.user)

    def _parse_event_time(self, text: str) -> datetime | None:
        now = datetime.now(timezone.utc)
        text = text.strip().lower()

        # "через Xч/м/с"
        if text.startswith("через"):
            import re
            m = re.search(r"(\d+)([чмс])", text)
            if not m:
                return None
            val, unit = int(m.group(1)), m.group(2)
            delta = timedelta(hours=val) if unit == "ч" else timedelta(minutes=val) if unit == "м" else timedelta(seconds=val)
            return now + delta

        # "завтра HH:MM"
        if text.startswith("завтра"):
            time_part = text.replace("завтра", "").strip()
            try:
                h, mi = map(int, time_part.split(":"))
                return (now + timedelta(days=1)).replace(hour=h, minute=mi, second=0, microsecond=0)
            except ValueError:
                return None

        # "DD.MM HH:MM"
        try:
            parts = text.split()
            date_part, time_part = parts[0], parts[1] if len(parts) > 1 else "00:00"
            d, m = map(int, date_part.split("."))
            h, mi = map(int, time_part.split(":"))
            result = now.replace(month=m, day=d, hour=h, minute=mi, second=0, microsecond=0)
            if result < now:
                result = result.replace(year=now.year + 1)
            return result
        except (ValueError, IndexError):
            return None


async def setup(bot):
    await bot.add_cog(ServerEvents(bot))
