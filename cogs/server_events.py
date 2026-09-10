import discord
import json
from datetime import datetime, timezone, timedelta
from discord.ext import commands
from discord import app_commands
from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors
from cogs.achievements import award_achievement


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

    @app_commands.command(name="event_create", description="Создать событие")
    @app_commands.describe(
        name="Название события",
        description="Описание",
        time="Время начала (дд.мм чч:мм или через durée)",
        channel="Канал для напоминания"
    )
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

    @app_commands.command(name="event_list", description="Список активных событий")
    async def event_list(self, interaction: discord.Interaction):
        cursor = await self.db.conn.execute(
            "SELECT id, name, starts_at, creator_id, status FROM server_events "
            "WHERE guild_id = ? AND status = 'active' ORDER BY starts_at",
            (str(interaction.guild.id),)
        )
        rows = await cursor.fetchall()
        if not rows:
            return await interaction.response.send_message("📭 Активных событий нет.", ephemeral=True)

        lines = []
        for r in rows:
            time_text = f"<t:{int(datetime.fromisoformat(r['starts_at']).timestamp())}:R>" if r["starts_at"] else "Без даты"
            lines.append(f"**{r['name']}** — {time_text} (организатор: <@{r['creator_id']}>)")

        embed = discord.Embed(title="🎉 Активные события", description="\n".join(lines), color=Colors.MAIN)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="event_cancel", description="Отменить событие")
    @app_commands.describe(event_id="ID события")
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

    # ==========================================================
    #                ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================================

    @commands.command(name="event_create")
    async def event_create_prefix(self, ctx, name: str, description: str = "", time: str = None):
        from prefix_adapter import InteractionAdapter
        await self.event_create.callback(self, InteractionAdapter(ctx), name, description, time)

    @commands.command(name="event_list")
    async def event_list_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.event_list.callback(self, InteractionAdapter(ctx))

    @commands.command(name="event_cancel")
    async def event_cancel_prefix(self, ctx, event_id: int):
        from prefix_adapter import InteractionAdapter
        await self.event_cancel.callback(self, InteractionAdapter(ctx), event_id)


async def setup(bot):
    await bot.add_cog(ServerEvents(bot))
