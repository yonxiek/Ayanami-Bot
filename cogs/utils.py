import asyncio
import json
import platform
import re
from datetime import datetime, timedelta, timezone

import aiohttp
import discord
from discord import app_commands, ui
from discord.components import MediaGalleryItem
from discord.ext import commands, tasks

import config
from db import Database
from ui_components import AyanamiUI, Colors


def parse_duration(duration: str) -> timedelta | None:
    pattern = re.compile(r'(\d+)([smhd])')
    matches = pattern.findall(duration.lower())
    if not matches: return None
    time_dict = {}
    for value, unit in matches:
        if unit == 's': time_dict['seconds'] = time_dict.get('seconds', 0) + int(value)
        elif unit == 'm': time_dict['minutes'] = time_dict.get('minutes', 0) + int(value)
        elif unit == 'h': time_dict['hours'] = time_dict.get('hours', 0) + int(value)
        elif unit == 'd': time_dict['days'] = time_dict.get('days', 0) + int(value)
    return timedelta(**time_dict)


class EventRSVPView(ui.LayoutView):
    def __init__(self, db: Database, *, event_type: str = None, host_id: str = None, timestamp: int = None, attendees: list = None):
        super().__init__(timeout=None)
        self.db = db
        self._event_type = event_type
        self._host_id = host_id
        self._timestamp = timestamp
        self._attendees = attendees if attendees is not None else []

        container = ui.Container(accent_color=discord.Color(0x2b2d31))
        if self._event_type:
            container.add_item(ui.TextDisplay(f"## Запланировано: {self._event_type}"))
        if self._host_id and self._timestamp:
            container.add_item(ui.TextDisplay(
                f"**Организатор:** <@{self._host_id}>\n"
                f"**Начало:** <t:{self._timestamp}:R>\n\n"
                f"Нажмите кнопку ниже для записи."
            ))
        if self._attendees is not None:
            mentions = [f"<@{uid}>" for uid in self._attendees]
            attendees_text = ", ".join(mentions) if mentions else "Пока никого нет."
            if len(attendees_text) > 1000:
                attendees_text = attendees_text[:950] + f"... и еще {len(self._attendees)-15} чел."
            container.add_item(ui.TextDisplay(f"**\ud83d\udc65 \u0423\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0438 ({len(self._attendees)})**\n{attendees_text}"))
        self.add_item(container)

    async def _update(self, interaction: discord.Interaction, is_joining: bool):
        msg_id = str(interaction.message.id)
        cursor = await self.db.conn.execute("SELECT * FROM events WHERE message_id = ?", (msg_id,))
        row = await cursor.fetchone()
        if not row:
            return await interaction.response.send_message("\u274c \u0418\u0432\u0435\u043d\u0442 \u0443\u0436\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d \u0438\u043b\u0438 \u0443\u0434\u0430\u043b\u0435\u043d.", ephemeral=True)

        attendees = json.loads(row['attendees'])
        user_id_str = str(interaction.user.id)

        if is_joining:
            if user_id_str in attendees:
                return await interaction.response.send_message("\u0412\u044b \u0443\u0436\u0435 \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u044b!", ephemeral=True)
            attendees.append(user_id_str)
            msg = "\u2705 \u0412\u044b \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u0437\u0430\u043f\u0438\u0441\u0430\u043b\u0438\u0441\u044c!"
        else:
            if user_id_str not in attendees:
                return await interaction.response.send_message("\u0412\u0430\u0441 \u0438 \u0442\u0430\u043a \u043d\u0435\u0442 \u0432 \u0441\u043f\u0438\u0441\u043a\u0435.", ephemeral=True)
            attendees.remove(user_id_str)
            msg = "\u274c \u0412\u044b \u0432\u044b\u043f\u0438\u0441\u0430\u043b\u0438\u0441\u044c \u0438\u0437 \u0441\u043f\u0438\u0441\u043a\u0430."

        await self.db.conn.execute("UPDATE events SET attendees = ? WHERE id = ?", (json.dumps(attendees), row['id']))
        await self.db.conn.commit()

        new_view = EventRSVPView(
            self.db,
            event_type=row['type'],
            host_id=row['host_id'],
            timestamp=int(datetime.fromisoformat(row['start_time']).timestamp()),
            attendees=attendees
        )
        await interaction.response.edit_message(view=new_view)
        await interaction.followup.send(msg, ephemeral=True)

    @ui.button(label="\u0411\u0443\u0434\u0443", style=discord.ButtonStyle.success, custom_id="event_join_btn", emoji="\u2705")
    async def join_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._update(interaction, True)

    @ui.button(label="\u041f\u0440\u043e\u043f\u0443\u0449\u0443", style=discord.ButtonStyle.secondary, custom_id="event_leave_btn", emoji="\u274c")
    async def leave_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._update(interaction, False)


class ReportResolveView(ui.LayoutView):
    def __init__(self, db: Database, *, title: str = None, color: discord.Color = None, thumbnail: str = None, fields: list = None, footer: str = None):
        super().__init__(timeout=None)
        self.db = db
        self._title = title
        self._color = color or discord.Color(0x2b2d31)
        self._thumbnail = thumbnail
        self._fields = list(fields) if fields else []
        self._footer = footer
        self._build_ui()

    def _build_ui(self, resolved_by: str = None):
        self.clear_items()
        color = discord.Color.green() if resolved_by else self._color
        container = ui.Container(accent_color=color)
        if self._title:
            container.add_item(ui.TextDisplay(f"## {self._title}"))
        if self._thumbnail:
            container.add_item(ui.MediaGallery(MediaGalleryItem(media=self._thumbnail)))
        fields = list(self._fields)
        if resolved_by:
            fields.append(("\u2705 Resolved by:", resolved_by))
        for name, value in fields:
            if name and value:
                container.add_item(ui.TextDisplay(f"**{name}**\n{value}"))
        if self._footer:
            container.add_item(ui.Separator(visible=False))
            container.add_item(ui.TextDisplay(f"*{self._footer}*"))
        self.add_item(container)

    @ui.button(label="Resolve (\u0417\u0430\u043a\u0440\u044b\u0442\u044c)", style=discord.ButtonStyle.success, custom_id="resolve_report_btn_v1", emoji="\u2705")
    async def resolve_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("\u274c \u0423 \u0432\u0430\u0441 \u043d\u0435\u0442 \u043f\u0440\u0430\u0432 \u0434\u043b\u044f \u0437\u0430\u043a\u0440\u044b\u0442\u0438\u044f \u0436\u0430\u043b\u043e\u0431!", ephemeral=True)
        await self.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "report_resolved", 1)
        resolved_by = f"{interaction.user.mention} (`{interaction.user.name}` | ID: `{interaction.user.id}`)"
        self._build_ui(resolved_by=resolved_by)
        for child in self.children:
            if isinstance(child, ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)


class ReportMessageModal(ui.Modal, title="\u0416\u0430\u043b\u043e\u0431\u0430 \u043d\u0430 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435"):
    reason = ui.TextInput(label="\u041f\u0440\u0438\u0447\u0438\u043d\u0430 \u0436\u0430\u043b\u043e\u0431\u044b", style=discord.TextStyle.long, required=True, placeholder="\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0421\u043f\u0430\u043c, \u043e\u0441\u043a\u043e\u0440\u0431\u043b\u0435\u043d\u0438\u0435...")

    def __init__(self, message: discord.Message, log_channel: discord.TextChannel, db: Database):
        super().__init__()
        self.message = message
        self.log_channel = log_channel
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        content = self.message.content
        if not content and self.message.attachments: content = f"*[Вложение: {len(self.message.attachments)} файл(ов)]*"
        elif not content: content = "*Пустое сообщение*"
        if len(content) > 1000: content = content[:997] + "..."

        view = ReportResolveView(
            self.db,
            title="\ud83d\udea8 Message Report",
            color=discord.Color(0x2b2d31),
            thumbnail=self.message.author.display_avatar.url if self.message.author.display_avatar else None,
            fields=[
                ("Reported User", f"{self.message.author.mention}\n`{self.message.author.name}`"),
                ("Channel", self.message.channel.mention),
                ("Reported by", f"{interaction.user.mention}\n`{interaction.user.name}`"),
                ("Message content", f"```\n{content}\n```"),
                ("Reason", self.reason.value),
                ("Jump to Message", f"[Click here]({self.message.jump_url})"),
            ],
            footer=f"User ID: {self.message.author.id} | Reporter ID: {interaction.user.id} | Message ID: {self.message.id}"
        )
        await self.log_channel.send(view=view)
        await interaction.response.send_message("\u2705 \u0412\u0430\u0448\u0430 \u0436\u0430\u043b\u043e\u0431\u0430 \u043d\u0430 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430 \u043c\u043e\u0434\u0435\u0440\u0430\u0442\u043e\u0440\u0430\u043c!", ephemeral=True)


class ModeratorModal(ui.Modal, title="Заявка на должность Модератор"):
    q1 = ui.TextInput(label="Почему хотите стать модератором?", style=discord.TextStyle.long, required=True)
    q2 = ui.TextInput(label="Был ли у вас опыт в модерировании?", style=discord.TextStyle.long, required=True)
    q3 = ui.TextInput(label="Сколько готовы уделять времени?", style=discord.TextStyle.short, required=True)
    q4 = ui.TextInput(label="Как будете решать конфликты?", style=discord.TextStyle.long, required=True)
    q5 = ui.TextInput(label="Меры при нарушении правил?", style=discord.TextStyle.long, required=True)

    def __init__(self, log_channel):
        super().__init__()
        self.log_channel = log_channel

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📥 Новая заявка: Модератор",
            color=discord.Color(AyanamiUI.INFO),
        )
        for name, value in [
                ("1. Почему вы хотите стать модератором на нашем сервере? Объясните почему.", f"```\n{self.q1.value}\n```"),
                ("2. Был ли у вас опыт в модерировании где-то на каких-то серверах.", f"```\n{self.q2.value}\n```"),
                ("3. Сколько готовы уделять времени на модерацию.", f"```\n{self.q3.value}\n```"),
                ("4. Как вы будете решать конфликты/огромные ссоры.", f"```\n{self.q4.value}\n```"),
                ("5. Какие меры предпримете, когда участник будет нарушать правила.", f"```\n{self.q5.value}\n```"),
        ]:
            embed.add_field(name=name, value=value, inline=False)
        await self.log_channel.send(embed=embed)
        await interaction.response.send_message("Ваша заявка на **Модератора** отправлена!", ephemeral=True)


class TrainingModal(ui.Modal, title="\u0417\u0430\u044f\u0432\u043a\u0430 \u043d\u0430 Training Hoster"):
    q1 = ui.TextInput(label="\u0415\u0441\u0442\u044c \u043b\u0438 \u0443 \u0432\u0430\u0441 \u0433\u0435\u0439\u043c\u043f\u0430\u0441\u0441 PS+?", style=discord.TextStyle.short, required=True)
    q2 = ui.TextInput(label="\u0411\u044b\u043b \u043b\u0438 \u0443 \u0432\u0430\u0441 \u043e\u043f\u044b\u0442 \u0432 \u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0435/\u043a\u043b\u0430\u043d\u0435?", style=discord.TextStyle.long, required=True)
    q3 = ui.TextInput(label="\u0415\u0441\u043b\u0438 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a \u043d\u0435 \u0431\u0443\u0434\u0435\u0442 \u0441\u043b\u0443\u0448\u0430\u0442\u044c\u0441\u044f?", style=discord.TextStyle.long, required=True)
    q4 = ui.TextInput(label="\u0418\u043c\u0435\u0435\u0442\u0441\u044f \u043b\u0438 \u0443 \u0432\u0430\u0441 \u0447\u0430\u0442?", style=discord.TextStyle.short, required=True)

    def __init__(self, log_channel):
        super().__init__()
        self.log_channel = log_channel

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="\ud83d\udce5 \u041d\u043e\u0432\u0430\u044f \u0437\u0430\u044f\u0432\u043a\u0430: Training Hoster",
            color=discord.Color(0x3498db),
        )
        for name, value in [
                ("1. \u0415\u0441\u0442\u044c \u043b\u0438 \u0443 \u0432\u0430\u0441 \u043a\u0443\u043f\u043b\u0435\u043d\u043d\u044b\u0439 \u0433\u0435\u0439\u043c\u043f\u0430\u0441\u0441 Private + ( PS+ )", f"```\n{self.q1.value}\n```"),
                ("2. \u0411\u044b\u043b \u043b\u0438 \u0443 \u0432\u0430\u0441 \u043e\u043f\u044b\u0442 \u0432 \u043a\u0430\u043a\u043e\u043c-\u043b\u0438\u0431\u043e \u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0435/\u043a\u043b\u0430\u043d\u0435, \u0431\u044b\u043b \u043b\u0438 \u043e\u043f\u044b\u0442 \u0432\u043e\u043e\u0431\u0449\u0435?", f"```\n{self.q2.value}\n```"),
                ("3. \u0427\u0442\u043e \u0432\u044b \u0431\u0443\u0434\u0435\u0442\u0435 \u0434\u0435\u043b\u0430\u0442\u044c, \u0435\u0441\u043b\u0438 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a \u043d\u0435 \u0431\u0443\u0434\u0435\u0442 \u0441\u043b\u0443\u0448\u0430\u0442\u044c\u0441\u044f \u0432\u0430\u0441/\u0438\u0433\u043d\u043e\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0432\u0430\u0448\u0438 \u0441\u043b\u043e\u0432\u0430.", f"```\n{self.q3.value}\n```"),
                ("4. \u0418\u043c\u0435\u0435\u0442\u0441\u044f \u043b\u0438 \u0443 \u0432\u0430\u0441 \u0447\u0430\u0442?", f"```\n{self.q4.value}\n```"),
        ]:
            embed.add_field(name=name, value=value, inline=False)
        await self.log_channel.send(embed=embed)
        await interaction.response.send_message("\u0412\u0430\u0448\u0430 \u0437\u0430\u044f\u0432\u043a\u0430 \u043d\u0430 **Training Hoster** \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430!", ephemeral=True)


class TryoutModal(ui.Modal, title="\u0417\u0430\u044f\u0432\u043a\u0430 \u043d\u0430 Tryout Hoster"):
    q1 = ui.TextInput(label="\u0415\u0441\u0442\u044c \u043b\u0438 \u0443 \u0432\u0430\u0441 \u0433\u0435\u0439\u043c\u043f\u0430\u0441\u0441 PS+?", style=discord.TextStyle.short, required=True)
    q2 = ui.TextInput(label="\u041a\u0430\u043a\u043e\u0439 \u0443 \u0432\u0430\u0441 \u0441\u0442\u0435\u0439\u0434\u0436?", style=discord.TextStyle.short, required=True)
    q3 = ui.TextInput(label="\u0411\u044b\u043b\u0438 \u043b\u0438 \u0432\u044b Tryout Hoster \u0440\u0430\u043d\u0435\u0435?", style=discord.TextStyle.long, required=True)
    q4 = ui.TextInput(label="\u041a\u0430\u043a \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u044f\u0435\u0442\u0435 \u0441\u0442\u0435\u0439\u0434\u0436 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0430?", style=discord.TextStyle.long, required=True)

    def __init__(self, log_channel):
        super().__init__()
        self.log_channel = log_channel

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="\ud83d\udce5 \u041d\u043e\u0432\u0430\u044f \u0437\u0430\u044f\u0432\u043a\u0430: Tryout Hoster",
            color=discord.Color(0x9b59b6),
        )
        for name, value in [
                ("1. \u0415\u0441\u0442\u044c \u043b\u0438 \u0443 \u0432\u0430\u0441 \u043a\u0443\u043f\u043b\u0435\u043d\u043d\u044b\u0439 \u0433\u0435\u0439\u043c\u043f\u0430\u0441\u0441 Private + ( PS+ )?", f"```\n{self.q1.value}\n```"),
                ("2. \u041a\u0430\u043a\u043e\u0439 \u0443 \u0432\u0430\u0441 \u0441\u0442\u0435\u0439\u0434\u0436 (\u043f\u0440\u0438\u043d\u0438\u043c\u0430\u0435\u043c \u0434\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u0430 \u0441\u0442\u0435\u0439\u0434\u0436\u0430 \u0442\u043e\u043b\u044c\u043a\u043e \u0438\u0437 CIS TSB Community \u0438 TSBCC \u0431\u0440\u0430\u043d\u0447\u0435\u0439 )?", f"```\n{self.q2.value}\n```"),
                ("3. \u0411\u044b\u043b\u0438 \u043b\u0438 \u0432\u044b Tryout Hoster \u0432 \u043a\u0430\u043a\u043e\u043c-\u043b\u0438\u0431\u043e \u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0435 \u0438\u043b\u0438 \u043a\u043b\u0430\u043d\u0430\u0445, \u0431\u044b\u043b \u043b\u0438 \u043e\u043f\u044b\u0442 \u0432\u043e\u043e\u0431\u0449\u0435?", f"```\n{self.q3.value}\n```"),
                ("4. \u041f\u043e \u043a\u0430\u043a\u0438\u043c \u043a\u0440\u0438\u0442\u0435\u0440\u0438\u044f\u043c \u0432\u044b \u0441\u043e\u0431\u0438\u0440\u0430\u0435\u0442\u0435\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u044f\u0442\u044c \u0441\u0442\u0435\u0439\u0434\u0436 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0430?", f"```\n{self.q4.value}\n```"),
        ]:
            embed.add_field(name=name, value=value, inline=False)
        await self.log_channel.send(embed=embed)
        await interaction.response.send_message("\u0412\u0430\u0448\u0430 \u0437\u0430\u044f\u0432\u043a\u0430 \u043d\u0430 **Tryout Hoster** \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430!", ephemeral=True)


class ApplicationView(ui.LayoutView):
    def __init__(self, app_type: str, log_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.app_type = app_type
        self.log_channel = log_channel

        container = ui.Container(accent_color=discord.Color(0x2b2d31))
        container.add_item(ui.TextDisplay(f"## \u041e\u0442\u043a\u0440\u044b\u0442 \u043d\u0430\u0431\u043e\u0440: {app_type}"))
        container.add_item(ui.TextDisplay(
            f"\u0412\u044b \u043c\u043e\u0436\u0435\u0442\u0435 \u043f\u043e\u0434\u0430\u0442\u044c \u0437\u0430\u044f\u0432\u043a\u0443 \u043d\u0430 \u0434\u043e\u043b\u0436\u043d\u043e\u0441\u0442\u044c **{app_type}**.\n"
            f"\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u043d\u0430 \u043a\u043d\u043e\u043f\u043a\u0443 \u043d\u0438\u0436\u0435, \u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435."
        ))
        container.add_item(ui.Separator(visible=False))
        container.add_item(ui.TextDisplay("*Ayanami System*"))
        self.add_item(container)

    @ui.button(label="\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u0430\u043d\u043a\u0435\u0442\u0443", style=discord.ButtonStyle.green, custom_id="apply_btn")
    async def apply_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.app_type == "Moderator": await interaction.response.send_modal(ModeratorModal(self.log_channel))
        elif self.app_type == "Training": await interaction.response.send_modal(TrainingModal(self.log_channel))
        elif self.app_type == "Tryout": await interaction.response.send_modal(TryoutModal(self.log_channel))


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.bloxlink_api_key = config.BLOXLINK_API_KEY

        self.report_ctx_menu = app_commands.ContextMenu(name="Report Message", callback=self.report_message_context)
        self.bot.tree.add_command(self.report_ctx_menu)

    async def get_log_channel_id(self, guild_id: int):
        config = await self.db.get_guild_config(str(guild_id))
        return config.get("log_channel_id")

    async def get_report_channel_id(self, guild_id: int):
        config = await self.db.get_guild_config(str(guild_id))
        return config.get("report_channel_id")

    async def cog_load(self):
        self.bot.add_view(EventRSVPView(self.db))
        self.bot.add_view(ReportResolveView(self.db))
        self.event_notifier.start()
        self.task_checker.start()

    def cog_unload(self):
        self.event_notifier.cancel()
        self.task_checker.cancel()

    @tasks.loop(minutes=1)
    async def event_notifier(self):
        now = datetime.now(timezone.utc)
        cursor = await self.db.conn.execute("SELECT * FROM events WHERE pinged = 0")
        events = await cursor.fetchall()
        for event in events:
            start_time = datetime.fromisoformat(event['start_time'])
            if (start_time - now).total_seconds() <= 600:
                channel = self.bot.get_channel(int(event['channel_id']))
                if channel:
                    attendees = json.loads(event['attendees'])
                    if attendees:
                        mentions = " ".join([f"<@{uid}>" for uid in attendees])
                        embed = discord.Embed(
                            title="\ud83d\udd14 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 \u043e \u0441\u043e\u0431\u044b\u0442\u0438\u0438!",
                            description=f"\u0421\u043e\u0431\u044b\u0442\u0438\u0435 **{event['type']}** \u043e\u0442 <@{event['host_id']}> \u043d\u0430\u0447\u043d\u0435\u0442\u0441\u044f \u043c\u0435\u043d\u0435\u0435 \u0447\u0435\u043c \u0437\u0430 10 \u043c\u0438\u043d\u0443\u0442!\n\n**\u041f\u0440\u0438\u0433\u043e\u0442\u043e\u0432\u044c\u0442\u0435\u0441\u044c!**",
                            color=discord.Color(0xfaa61a)
                        )
                        await channel.send(
                            content=mentions,
                            embed=embed,
                            allowed_mentions=discord.AllowedMentions(users=True)
                        )
                await self.db.conn.execute("UPDATE events SET pinged = 1 WHERE id = ?", (event['id'],))
                await self.db.conn.commit()

    @tasks.loop(minutes=1)
    async def task_checker(self):
        now = datetime.now(timezone.utc)
        cursor = await self.db.conn.execute("SELECT * FROM scheduled_tasks WHERE end_time <= ?", (now.isoformat(),))
        tasks_to_close = await cursor.fetchall()
        for task in tasks_to_close:
            try:
                channel = self.bot.get_channel(int(task['channel_id']))
                if channel:
                    msg = await channel.fetch_message(int(task['message_id']))
                    if msg:
                        if task['task_type'] == "application":
                            meta = json.loads(task['metadata'])
                            closed_embed = discord.Embed(
                                title=f"\u274c \u041d\u0430\u0431\u043e\u0440 \u0437\u0430\u043a\u0440\u044b\u0442: {meta['app_type']}",
                                description="\u041f\u0440\u0438\u0435\u043c \u0437\u0430\u044f\u0432\u043e\u043a \u043d\u0430 \u0434\u0430\u043d\u043d\u0443\u044e \u0434\u043e\u043b\u0436\u043d\u043e\u0441\u0442\u044c \u043e\u043a\u043e\u043d\u0447\u0435\u043d. \u041e\u0436\u0438\u0434\u0430\u0439\u0442\u0435 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0445 \u043d\u0430\u0431\u043e\u0440\u043e\u0432!",
                                color=discord.Color(Colors.MAIN)
                            )
                            await msg.edit(embed=closed_embed)

                await self.db.conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task['id'],))
            except Exception as e:
                print(f"\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u0437\u0430\u043a\u0440\u044b\u0442\u0438\u0438 \u0437\u0430\u0434\u0430\u0447\u0438 {task['id']}: {e}")
                await self.db.conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task['id'],))

        await self.db.conn.commit()

    @event_notifier.before_loop
    async def before_notifier(self):
        await self.bot.wait_until_ready()

    async def report_message_context(self, interaction: discord.Interaction, message: discord.Message):
        report_channel_id = await self.get_report_channel_id(interaction.guild.id)
        report_channel = self.bot.get_channel(int(report_channel_id)) if report_channel_id else None
        if not report_channel: return await interaction.response.send_message("\u274c \u041a\u0430\u043d\u0430\u043b \u0434\u043b\u044f \u0436\u0430\u043b\u043e\u0431 \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d (\u043d\u0430\u0441\u0442\u0440\u043e\u0439\u0442\u0435 \u0432 /setup).", ephemeral=True)
        await interaction.response.send_modal(ReportMessageModal(message, report_channel, self.db))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        if message.reference and message.reference.message_id:
            if message.content.lower().startswith(('/report', '!report', '.report')):
                parts = message.content.split(maxsplit=1)
                reason = parts[1] if len(parts) > 1 else "\u041f\u0440\u0438\u0447\u0438\u043d\u0430 \u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u0430"
                try: target_msg = await message.channel.fetch_message(message.reference.message_id)
                except discord.NotFound: return
                report_channel_id = await self.get_report_channel_id(message.guild.id)
                report_channel = self.bot.get_channel(int(report_channel_id)) if report_channel_id else None
                if not report_channel: return await message.reply("\u274c \u041a\u0430\u043d\u0430\u043b \u0434\u043b\u044f \u0436\u0430\u043b\u043e\u0431 \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d.", delete_after=5)

                content = target_msg.content
                if not content and target_msg.attachments: content = f"*[Вложение: {len(target_msg.attachments)} файл(ов)]*"
                elif not content: content = "*Пустое сообщение*"
                if len(content) > 1000: content = content[:997] + "..."

                view = ReportResolveView(
                    self.db,
                    title="\ud83d\udea8 Message Report (\u0427\u0435\u0440\u0435\u0437 \u043e\u0442\u0432\u0435\u0442)",
                    color=discord.Color(0x2b2d31),
                    thumbnail=target_msg.author.display_avatar.url if target_msg.author.display_avatar else None,
                    fields=[
                        ("Reported User", f"{target_msg.author.mention}\n`{target_msg.author.name}`"),
                        ("Channel", target_msg.channel.mention),
                        ("Reported by", f"{message.author.mention}\n`{message.author.name}`"),
                        ("Message content", f"```\n{content}\n```"),
                        ("Reason", f"```\n{reason}\n```"),
                        ("Jump to Message", f"[Click here]({target_msg.jump_url})"),
                    ],
                    footer=f"User ID: {target_msg.author.id} | Reporter ID: {message.author.id} | Message ID: {target_msg.id}"
                )

                await report_channel.send(view=view)
                try: await message.delete()
                except: pass
                success_msg = await message.channel.send(f"\u2705 {message.author.mention}, \u0432\u0430\u0448\u0430 \u0436\u0430\u043b\u043e\u0431\u0430 \u043d\u0430 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430!")
                await asyncio.sleep(5)
                try: await success_msg.delete()
                except: pass

    async def fetch_roblox_data_from_api(self, guild_id: int, user_id: int) -> dict | None:
        url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{user_id}"
        headers = {"Authorization": self.bloxlink_api_key}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        print(f"[Bloxlink] Status {resp.status} for user {user_id}")
                        return None
                    data = await resp.json()
                    roblox_id = data.get("robloxID")
                if not roblox_id:
                    print(f"[Bloxlink] No robloxID for user {user_id}, data: {data}")
                    return None
                rbx_url = f"https://users.roblox.com/v1/users/{roblox_id}"
                async with session.get(rbx_url) as r_resp:
                    if r_resp.status == 200:
                        r_data = await r_resp.json()
                        return { "roblox_id": roblox_id, "username": r_data.get("name"), "display_name": r_data.get("displayName"), "description": r_data.get("description", ""), "created": r_data.get("created")}
                    print(f"[Roblox] Status {r_resp.status} for roblox_id {roblox_id}")
        except Exception as e:
            print(f"[Bloxlink] Exception for user {user_id}: {e}")
        return None

    @app_commands.command(name="whois", description="\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043f\u043e\u0434\u0440\u043e\u0431\u043d\u0443\u044e \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044e \u043e\u0431 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0435")
    async def whois(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        roles = [role.mention for role in reversed(target.roles[1:])]
        roles_str = " ".join(roles) if roles else "\u041d\u0435\u0442 \u0440\u043e\u043b\u0435\u0439"
        if len(roles_str) > 1024: roles_str = roles_str[:1020] + "..."
        key_perms = []
        perms = target.guild_permissions
        if perms.administrator: key_perms.append("\u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440")
        if perms.manage_guild: key_perms.append("\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c")
        if perms.manage_roles: key_perms.append("\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0440\u043e\u043b\u044f\u043c\u0438")
        if perms.manage_channels: key_perms.append("\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u043a\u0430\u043d\u0430\u043b\u0430\u043c\u0438")
        if perms.manage_messages: key_perms.append("\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f\u043c\u0438")
        if perms.kick_members: key_perms.append("\u041a\u0438\u043a \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u043e\u0432")
        if perms.ban_members: key_perms.append("\u0411\u0430\u043d \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u043e\u0432")
        perms_str = ", ".join(key_perms) if key_perms else "\u041e\u0431\u044b\u0447\u043d\u044b\u0439 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a"

        embed = discord.Embed(
            color=discord.Color(0x2b2d31),
        )
        embed.set_author(name=f"\u0423\u0447\u0430\u0441\u0442\u043d\u0438\u043a: {target.name}", icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=target.display_avatar.url)
        for name, value in [
                ("\u0414\u0430\u0442\u0430 \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u0438", f"<t:{int(target.created_at.timestamp())}:D>"),
                ("\u041f\u0440\u0438\u0441\u043e\u0435\u0434\u0438\u043d\u0438\u043b\u0441\u044f", f"<t:{int(target.joined_at.timestamp())}:D>"),
                ("ID", f"`{target.id}`"),
                ("\u0420\u043e\u043b\u0438", roles_str),
                ("\u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u043f\u0440\u0430\u0432\u0430", perms_str),
        ]:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Информация о боте")
    async def botinfo(self, interaction: discord.Interaction):
        uptime = datetime.now(timezone.utc) - self.bot.start_time
        total_seconds = int(uptime.total_seconds())
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_parts = []
        if days:
            uptime_parts.append(f"{days} {AyanamiUI.get_plural(days, 'день', 'дня', 'дней')}")
        if hours:
            uptime_parts.append(f"{hours} {AyanamiUI.get_plural(hours, 'час', 'часа', 'часов')}")
        if minutes:
            uptime_parts.append(f"{minutes} {AyanamiUI.get_plural(minutes, 'минута', 'минуты', 'минут')}")
        if not uptime_parts:
            uptime_parts.append(f"{seconds} {AyanamiUI.get_plural(seconds, 'секунда', 'секунды', 'секунд')}")
        uptime_text = " ".join(uptime_parts)

        member_count = sum(g.member_count or 0 for g in self.bot.guilds)
        command_count = len(self.bot.tree.get_commands())

        embed = discord.Embed(
            title=f"🤖 {self.bot.user.name} — информация",
            color=discord.Color(Colors.MAIN),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="🐍 Версия Python", value=platform.python_version(), inline=True)
        embed.add_field(name="📚 discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="🕒 Аптайм", value=uptime_text, inline=False)
        embed.add_field(name="🖥 Сервера", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="👥 Пользователи", value=f"{member_count:,}".replace(",", " "), inline=True)
        embed.add_field(name="⚙ Коги", value=str(len(self.bot.cogs)), inline=True)
        embed.add_field(name="📝 Команды", value=str(command_count), inline=True)
        embed.add_field(name="📡 WebSocket", value=f"{self.bot.latency * 1000:.0f} мс", inline=True)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roblox", description="Посмотреть подробный профиль Roblox участника")
    async def roblox_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None):
        await interaction.response.defer()
        target = member or interaction.user
        api_data = await self.fetch_roblox_data_from_api(interaction.guild.id, target.id)
        if not api_data:
            embed = discord.Embed(
                title="\u0410\u043a\u043a\u0430\u0443\u043d\u0442 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d",
                description=f"> \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c {target.mention} \u043d\u0435 \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u043b \u0430\u043a\u043a\u0430\u0443\u043d\u0442 Roblox \u0447\u0435\u0440\u0435\u0437 Bloxlink.",
                color=discord.Color(Colors.MAIN)
            )
            return await interaction.followup.send(embed=embed)

        roblox_id = api_data["roblox_id"]
        username = api_data["username"]
        display_name = api_data["display_name"]
        description = api_data.get("description", "") or "\u041e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442"
        if len(description) > 300: description = description[:297] + "..."
        created_str = api_data.get("created", "")
        created_timestamp_text = "`\u0421\u043a\u0440\u044b\u0442\u0430`"
        if created_str:
            try:
                dt = datetime.strptime(created_str[:19], "%Y-%m-%dT%H:%M:%S")
                ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
                created_timestamp_text = f"<t:{ts}:D> (<t:{ts}:R>)"
            except Exception: pass
        profile_url = f"https://www.roblox.com/users/{roblox_id}/profile"
        avatar_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={roblox_id}&size=420x420&format=Png&isCircular=false"
        friends_url = f"https://friends.roblox.com/v1/users/{roblox_id}/friends/count"
        followers_url = f"https://friends.roblox.com/v1/users/{roblox_id}/followers/count"
        presence_url = "https://presence.roblox.com/v1/presence/users"
        presence_payload = {"userIds": [roblox_id]}
        friends_count = 0
        followers_count = 0
        presence_type = 0
        try:
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(avatar_url) as resp:
                        if resp.status == 200:
                            pass
                except Exception: pass
                try:
                    async with session.get(friends_url) as resp:
                        if resp.status == 200:
                            fd_data = await resp.json()
                            friends_count = fd_data.get("count", 0)
                except Exception: pass
                try:
                    async with session.get(followers_url) as resp:
                        if resp.status == 200:
                            fw_data = await resp.json()
                            followers_count = fw_data.get("count", 0)
                except Exception: pass
                try:
                    async with session.post(presence_url, json=presence_payload) as resp:
                        if resp.status == 200:
                            pr_data = await resp.json()
                            if pr_data.get("userPresences"):
                                presence_type = pr_data["userPresences"][0].get("userPresenceType", 0)
                except Exception: pass
        except Exception: pass
        status_map = {0: "\u26ab **\u041e\u0444\u0444\u043b\u0430\u0439\u043d**", 1: "\ud83d\udfe2 **\u041e\u043d\u043b\u0430\u0439\u043d** (\u0421\u0430\u0439\u0442/\u041c\u0435\u043d\u044e)", 2: "\ud83c\udfae **\u0412 \u0418\u0433\u0440\u0435**", 3: "\ud83d\udee0\ufe0f **\u0412 Roblox Studio**"}
        status_text = status_map.get(presence_type, "\u26ab **\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e**")

        description_text = (
            f"**\u041e\u0431\u0449\u0430\u044f \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044f:**\n> \ud83d\udc64 **\u041d\u0438\u043a\u043d\u0435\u0439\u043c:** `{username}`\n> \ud83c\udff7\ufe0f **Display Name:** `{display_name}`\n"
            f"> \ud83c\udd94 **ID:** `{roblox_id}`\n> \ud83d\udfe1 **\u0421\u0442\u0430\u0442\u0443\u0441:** {status_text}\n> \ud83d\udcc5 **\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f:** {created_timestamp_text}\n\n"
            f"**\u0421\u043e\u0446\u0438\u0430\u043b\u044c\u043d\u044b\u0435 \u0441\u0432\u044f\u0437\u0438:**\n> \ud83d\udc65 **\u0414\u0440\u0443\u0437\u044c\u044f:** `{friends_count}`\n> \ud83c\udf1f **\u041f\u043e\u0434\u043f\u0438\u0441\u0447\u0438\u043a\u0438:** `{followers_count}`\n\n"
            f"**\u041e \u0441\u0435\u0431\u0435:**\n```text\n{description}\n```\n\ud83d\udd17 **[\u041d\u0430\u0436\u043c\u0438\u0442\u0435, \u0447\u0442\u043e\u0431\u044b \u043f\u0435\u0440\u0435\u0439\u0442\u0438 \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u044c Roblox]({profile_url})**"
        )

        embed = discord.Embed(
            color=discord.Color(0x2b2d31),
        )
        embed.set_author(name=f"Roblox: {api_data['username']}", icon_url=target.display_avatar.url)
        embed.description = description_text
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="report", description="\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0436\u0430\u043b\u043e\u0431\u0443 \u043d\u0430 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0430")
    @app_commands.describe(member="\u041d\u0430\u0440\u0443\u0448\u0438\u0442\u0435\u043b\u044c", reason="\u041f\u0440\u0438\u0447\u0438\u043d\u0430 \u0436\u0430\u043b\u043e\u0431\u044b", message_ref="\u0421\u0441\u044b\u043b\u043a\u0430 \u0438\u043b\u0438 ID \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f")
    async def report_cmd(self, interaction: discord.Interaction, member: discord.Member, reason: str, message_ref: str):
        await interaction.response.defer(ephemeral=True)
        report_channel_id = await self.get_report_channel_id(interaction.guild.id)
        report_channel = self.bot.get_channel(int(report_channel_id)) if report_channel_id else None
        if not report_channel: return await interaction.followup.send("\u274c \u041a\u0430\u043d\u0430\u043b \u0434\u043b\u044f \u0436\u0430\u043b\u043e\u0431 \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d (\u043d\u0430\u0441\u0442\u0440\u043e\u0439\u0442\u0435 \u0432 /setup).", ephemeral=True)

        fields = [
            ("Reported User", f"{member.mention}\n`{member.name}`"),
            ("Reported by", f"{interaction.user.mention}\n`{interaction.user.name}`"),
            ("Reason", f"```\n{reason}\n```"),
        ]

        if message_ref.startswith("https://discord.com/channels/"):
            fields.append(("Jump to Message", f"[Click here]({message_ref})"))
        elif message_ref.isdigit():
            try:
                msg = await interaction.channel.fetch_message(int(message_ref))
                fields.append(("Jump to Message", f"[Click here]({msg.jump_url})"))
            except discord.NotFound:
                fields.append(("Message Info", f"ID: `{message_ref}`\n*(\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0432 \u044d\u0442\u043e\u043c \u043a\u0430\u043d\u0430\u043b\u0435)*"))
            except Exception:
                fields.append(("Message Info", f"ID: `{message_ref}`"))
        else:
            fields.append(("Message Info", message_ref))

        view = ReportResolveView(
            self.db,
            title="\ud83d\udea8 User Report",
            color=discord.Color(0x2b2d31),
            thumbnail=member.display_avatar.url if member.display_avatar else None,
            fields=fields,
            footer=f"User ID: {member.id} | Reporter ID: {interaction.user.id}"
        )
        await report_channel.send(view=view)
        await interaction.followup.send(f"\u2705 \u0412\u0430\u0448\u0430 \u0436\u0430\u043b\u043e\u0431\u0430 \u043d\u0430 {member.mention} \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430!", ephemeral=True)

    @app_commands.command(name="verify", description="\u0412\u0435\u0440\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u044f: \u0441\u043c\u0435\u043d\u0430 \u043d\u0438\u043a\u0430 \u0438 \u0432\u044b\u0434\u0430\u0447\u0430 \u0440\u043e\u043b\u0438 Roblox")
    @app_commands.describe(member="\u0423\u0447\u0430\u0441\u0442\u043d\u0438\u043a (\u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e \u0432\u044b)")
    async def verify(self, interaction: discord.Interaction, member: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        target = member or interaction.user

        config = await self.db.get_guild_config(str(interaction.guild.id))
        verify_config = config.get("verify", {})
        change_nick = verify_config.get("change_nickname", True)
        give_role = verify_config.get("give_role", True)
        role_id = verify_config.get("role_id")

        api_data = await self.fetch_roblox_data_from_api(interaction.guild.id, target.id)
        if not api_data:
            embed = discord.Embed(
                title="\u041e\u0448\u0438\u0431\u043a\u0430",
                description=f"> {target.mention} \u043d\u0435 \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u043b \u0430\u043a\u043a\u0430\u0443\u043d\u0442 \u0447\u0435\u0440\u0435\u0437 Bloxlink.",
                color=discord.Color(Colors.MAIN)
            )
            return await interaction.followup.send(embed=embed)

        roblox_nick = f"{api_data['display_name']} (@{api_data['username']})"
        await self.db.update_user_stats(str(interaction.guild.id), str(target.id), roblox_nick=roblox_nick)

        results = []

        if change_nick:
            try:
                new_nick = roblox_nick[:32]
                await target.edit(nick=new_nick)
                results.append(f"\u2705 \u041d\u0438\u043a\u043d\u0435\u0439\u043c: `{new_nick}`")
            except discord.Forbidden:
                results.append("\u274c \u041d\u0435\u0442 \u043f\u0440\u0430\u0432 \u043d\u0430 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435 \u043d\u0438\u043a\u043d\u0435\u0439\u043c\u0430")

        if give_role and role_id:
            role = interaction.guild.get_role(int(role_id))
            if role:
                try:
                    await target.add_roles(role, reason="Auto-verify")
                    results.append(f"\u2705 \u0420\u043e\u043b\u044c: {role.mention}")
                except discord.Forbidden:
                    results.append("\u274c \u041d\u0435\u0442 \u043f\u0440\u0430\u0432 \u043d\u0430 \u0432\u044b\u0434\u0430\u0447\u0443 \u0440\u043e\u043b\u0438")
            else:
                results.append("\u274c \u0420\u043e\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430")

        if not results:
            results.append("\u26a0\ufe0f \u0412\u0435\u0440\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u044f \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430 \u0432 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u0445")

        embed = discord.Embed(
            color=discord.Color(0x2b2d31),
        )
        embed.set_author(name="\u0412\u0435\u0440\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u044f Roblox", icon_url=target.display_avatar.url)
        embed.description = f"**\u0423\u0447\u0430\u0441\u0442\u043d\u0438\u043a:** {target.mention}\n\n" + "\n".join(results)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="verifyall", description="\u041c\u0430\u0441\u0441\u043e\u0432\u0430\u044f \u0432\u0435\u0440\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u044f \u043d\u0438\u043a\u043d\u0435\u0439\u043c\u043e\u0432")
    @app_commands.default_permissions(administrator=True)
    async def verifyall(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if not interaction.guild.chunked:
            await interaction.guild.chunk()

        config = await self.db.get_guild_config(str(interaction.guild.id))
        verify_config = config.get("verify", {})
        change_nick = verify_config.get("change_nickname", True)
        give_role = verify_config.get("give_role", True)
        role_id = verify_config.get("role_id")

        IMMUNE_ROLE_ID = 1539691325362806854
        targets = [
            m for m in interaction.guild.members
            if not m.bot and not any(r.id == IMMUNE_ROLE_ID for r in m.roles)
        ]

        if len(targets) == 0:
            return await interaction.followup.send("\u274c \u0421\u043f\u0438\u0441\u043e\u043a \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u043e\u0432 \u043f\u0443\u0441\u0442.")

        status_msg = await interaction.followup.send(f"\ud83d\ude80 \u041d\u0430\u0439\u0434\u0435\u043d\u043e \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u043e\u0432: `{len(targets)}`. \u041d\u0430\u0447\u0438\u043d\u0430\u044e \u0432\u0435\u0440\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u044e...")

        changed, already_ok, no_link, errors = [], [], [], []
        role = interaction.guild.get_role(int(role_id)) if give_role and role_id else None

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": self.bloxlink_api_key}
            for i, member in enumerate(targets):
                if i % 5 == 0 and i > 0:
                    try:
                        await status_msg.edit(content=f"\u23f3 \u041e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u043e: `{i}/{len(targets)}` \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u043e\u0432...")
                    except Exception:
                        pass

                user_data = await self.db.get_or_create_user(str(interaction.guild.id), str(member.id))
                stored_nick = user_data.get('roblox_nick')

                if stored_nick and member.display_name == stored_nick[:32]:
                    already_ok.append(member.display_name)
                    continue

                await asyncio.sleep(0.8)
                try:
                    url = f"https://api.blox.link/v4/public/guilds/{interaction.guild.id}/discord-to-roblox/{member.id}"
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            no_link.append(member.display_name)
                            continue
                        data = await resp.json()
                        roblox_id = data.get("robloxID")
                        if not roblox_id:
                            no_link.append(member.display_name)
                            continue

                    r_url = f"https://users.roblox.com/v1/users/{roblox_id}"
                    async with session.get(r_url) as resp:
                        if resp.status != 200:
                            errors.append(member.display_name)
                            continue
                        r_data = await resp.json()
                        roblox_nick = f"{r_data['displayName']} (@{r_data['name']})"

                    await self.db.update_user_stats(str(interaction.guild.id), str(member.id), roblox_nick=roblox_nick)

                    if change_nick:
                        try:
                            await member.edit(nick=roblox_nick[:32])
                        except discord.Forbidden:
                            pass

                    if role:
                        try:
                            await member.add_roles(role, reason="Mass verify")
                        except discord.Forbidden:
                            pass

                    changed.append(member.display_name)
                except Exception:
                    errors.append(member.display_name)

        summary = (
            f"**\u041c\u0430\u0441\u0441\u043e\u0432\u0430\u044f \u0432\u0435\u0440\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430!**\n\n"
            f"> \u2705 \u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e: `{len(changed)}`\n"
            f"> \u23ed\ufe0f \u0423\u0436\u0435 \u043e\u043a: `{len(already_ok)}`\n"
            f"> \u274c \u041d\u0435 \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u043d\u043e: `{len(no_link)}`\n"
            f"> \u26a0\ufe0f \u041e\u0448\u0438\u0431\u043a\u0438: `{len(errors)}`"
        )
        embed = discord.Embed(
            description=summary,
            color=discord.Color(Colors.MAIN),
        )
        embed.set_footer(text="Ayanami System")
        await status_msg.edit(content=None, embed=embed)

    @app_commands.command(name="host", description="\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0430\u043d\u043e\u043d\u0441 \u0438\u0432\u0435\u043d\u0442\u0430")
    @app_commands.choices(event_type=[
        app_commands.Choice(name="Game Night (\u0418\u0433\u0440\u044b)", value="Game Night")
    ])
    @app_commands.describe(
        duration="\u0427\u0435\u0440\u0435\u0437 \u0441\u043a\u043e\u043b\u044c\u043a\u043e \u043d\u0430\u0447\u043d\u0435\u0442\u0441\u044f? (\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440, 10m, 1h)",
        ping_role="\u041a\u0430\u043a\u0443\u044e \u0440\u043e\u043b\u044c \u043f\u0438\u043d\u0433\u0430\u043d\u0443\u0442\u044c? (\u041d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def host_cmd(self, interaction: discord.Interaction, event_type: str, duration: str, ping_role: discord.Role | None = None):
        delta = parse_duration(duration)
        if not delta:
            return await interaction.response.send_message("\u274c \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0432\u0440\u0435\u043c\u0435\u043d\u0438 (\u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 10m, 1h, 1d).", ephemeral=True)

        total_seconds = int(delta.total_seconds())
        if total_seconds < 600:
            return await interaction.response.send_message("\u274c \u0421\u043e\u0431\u044b\u0442\u0438\u0435 \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c \u043c\u0438\u043d\u0438\u043c\u0443\u043c \u0447\u0435\u0440\u0435\u0437 10 \u043c\u0438\u043d\u0443\u0442 (10m).", ephemeral=True)

        await interaction.response.defer()

        start_time = datetime.now(timezone.utc) + delta
        timestamp = int(start_time.timestamp())

        cursor = await self.db.conn.execute(
            "INSERT INTO events (guild_id, host_id, type, start_time, channel_id, message_id) VALUES (?, ?, ?, ?, ?, ?)",
            (str(interaction.guild.id), str(interaction.user.id), event_type, start_time.isoformat(), str(interaction.channel.id), "0")
        )
        event_id = cursor.lastrowid

        role = ping_role
        if not role:
            role_name_map = {"Game Night": "gamenight-ping"}
            target_name = role_name_map.get(event_type, "")
            role = discord.utils.find(lambda r: r.name.lower() == target_name.lower(), interaction.guild.roles)

        ping_content = role.mention if role else "*(\u0420\u043e\u043b\u044c \u0434\u043b\u044f \u043f\u0438\u043d\u0433\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430)*"

        event_view = EventRSVPView(
            self.db,
            event_type=event_type,
            host_id=str(interaction.user.id),
            timestamp=timestamp,
            attendees=[]
        )

        msg = await interaction.followup.send(
            content=ping_content,
            view=event_view,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )

        await self.db.conn.execute("UPDATE events SET message_id = ? WHERE id = ?", (str(msg.id), event_id))
        await self.db.conn.commit()

    @app_commands.command(name="applications", description="\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430\u0431\u043e\u0440 \u043d\u0430 \u0434\u043e\u043b\u0436\u043d\u043e\u0441\u0442\u044c")
    @app_commands.choices(app_type=[
        app_commands.Choice(name="Модератор", value="Moderator")
    ])
    @app_commands.describe(duration="\u0414\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c (\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440, 1h 30m, 1d, 5h)")
    @app_commands.default_permissions(administrator=True)
    async def applications(self, interaction: discord.Interaction, app_type: str, duration: str):
        delta = parse_duration(duration)
        if not delta:
            return await interaction.response.send_message("\u274c \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0432\u0440\u0435\u043c\u0435\u043d\u0438.", ephemeral=True)

        log_channel_id = await self.get_log_channel_id(interaction.guild.id)
        log_channel = self.bot.get_channel(int(log_channel_id)) if log_channel_id else None
        if not log_channel:
            return await interaction.response.send_message("\u274c \u041a\u0430\u043d\u0430\u043b \u0434\u043b\u044f \u043b\u043e\u0433\u043e\u0432 \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d (\u043d\u0430\u0441\u0442\u0440\u043e\u0439\u0442\u0435 \u0432 /setup).", ephemeral=True)

        now = datetime.now(timezone.utc)
        end_time = now + delta

        view = ApplicationView(app_type, log_channel)
        await interaction.response.defer()
        msg = await interaction.followup.send(view=view)

        await self.db.conn.execute(
            "INSERT INTO scheduled_tasks (guild_id, channel_id, message_id, end_time, task_type, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(interaction.guild.id),
                str(interaction.channel.id),
                str(msg.id),
                end_time.isoformat(),
                "application",
                json.dumps({"app_type": app_type})
            )
        )
        await self.db.conn.commit()

    @commands.command(name="whois")
    async def whois_prefix(self, ctx, member: discord.Member | None = None):
        from prefix_adapter import InteractionAdapter
        await self.whois.callback(self, InteractionAdapter(ctx), member)

    @commands.command(name="roblox")
    async def roblox_prefix(self, ctx, member: discord.Member | None = None):
        from prefix_adapter import InteractionAdapter
        await self.roblox_cmd.callback(self, InteractionAdapter(ctx), member)

    @commands.command(name="report")
    async def report_prefix(self, ctx, member: discord.Member, *, reason: str):
        from prefix_adapter import InteractionAdapter
        await self.report_cmd.callback(self, InteractionAdapter(ctx), member, reason, "")

    @commands.command(name="verify")
    async def verify_prefix(self, ctx, member: discord.Member | None = None):
        from prefix_adapter import InteractionAdapter
        await self.verify.callback(self, InteractionAdapter(ctx), member)

    @commands.command(name="verifyall")
    async def verifyall_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.verifyall.callback(self, InteractionAdapter(ctx))

    @commands.command(name="host")
    @commands.has_permissions(manage_messages=True)
    async def host_prefix(self, ctx, event_type: str, duration: str, ping_role: discord.Role | None = None):
        from prefix_adapter import InteractionAdapter
        await self.host_cmd.callback(self, InteractionAdapter(ctx), event_type, duration, ping_role)

    @commands.command(name="applications")
    async def applications_prefix(self, ctx, app_type: str, duration: str):
        from prefix_adapter import InteractionAdapter
        await self.applications.callback(self, InteractionAdapter(ctx), app_type, duration)


class WebhookEmbedModal(ui.Modal, title="Embed конструктор"):
    embed_title = discord.ui.TextInput(label="Заголовок", placeholder="Заголовок embed", required=False, max_length=256)
    embed_description = discord.ui.TextInput(label="Описание", placeholder="Описание (поддерживает markdown)", required=False, style=discord.TextStyle.long, max_length=4000)
    embed_color = discord.ui.TextInput(label="Цвет (hex)", placeholder="#5865F2", required=False, max_length=7)
    embed_author_name = discord.ui.TextInput(label="Author name", placeholder="Имя автора", required=False, max_length=256)
    embed_footer = discord.ui.TextInput(label="Footer", placeholder="Текст футера", required=False, max_length=2048)

    def __init__(self):
        super().__init__()
        self.result_embed = None

    async def on_submit(self, interaction: discord.Interaction):
        color = discord.Color.blurple()
        if self.embed_color.value.strip():
            try:
                color = discord.Color(int(self.embed_color.value.strip().strip("#"), 16))
            except Exception:
                pass

        embed = discord.Embed(
            title=self.embed_title.value or None,
            description=self.embed_description.value or None,
            color=color,
        )
        if self.embed_author_name.value:
            embed.set_author(name=self.embed_author_name.value)
        if self.embed_footer.value:
            embed.set_footer(text=self.embed_footer.value)

        self.result_embed = embed
        await interaction.response.defer()
        self.stop()


class WebhookBuilderView(ui.View):
    def __init__(self, webhook_url: str):
        super().__init__(timeout=300)
        self.webhook_url = webhook_url
        self.content = None
        self.embeds = []

    def build_payload(self):
        data = {}
        if self.content:
            data["content"] = self.content
        if self.embeds:
            data["embeds"] = [e.to_dict() for e in self.embeds[:10]]
        return data

    def build_preview(self):
        lines = []
        if self.content:
            lines.append(f"**Текст:** {self.content[:200]}")
        if self.embeds:
            for i, e in enumerate(self.embeds):
                lines.append(f"**Embed {i+1}:** {e.title or '(без заголовка)'}")
        if not lines:
            lines.append("*Пусто — нажмите «Текст» или «Embed»*")
        return "\n".join(lines)

    @ui.button(label="Текст", emoji="📝", style=discord.ButtonStyle.blurple, row=0)
    async def btn_content(self, interaction: discord.Interaction, button: ui.Button):
        modal = ui.Modal(title="Текст сообщения")
        field = discord.ui.TextInput(label="Content", placeholder="Текст сообщения...", required=False, style=discord.TextStyle.long, max_length=2000)
        modal.add_item(field)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.content = field.value or None
        await interaction.message.edit(embed=self._make_embed(), view=self)

    @ui.button(label="Embed", emoji="🎨", style=discord.ButtonStyle.blurple, row=0)
    async def btn_embed(self, interaction: discord.Interaction, button: ui.Button):
        if len(self.embeds) >= 10:
            return await interaction.response.send_message("❌ Максимум 10 embed'ов.", ephemeral=True)
        modal = WebhookEmbedModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result_embed:
            self.embeds.append(modal.result_embed)
        await interaction.message.edit(embed=self._make_embed(), view=self)

    @ui.button(label="Удалить embed", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def btn_remove_embed(self, interaction: discord.Interaction, button: ui.Button):
        if self.embeds:
            self.embeds.pop()
        await interaction.response.edit_message(embed=self._make_embed(), view=self)

    @ui.button(label="Отправить", emoji="🚀", style=discord.ButtonStyle.success, row=2)
    async def btn_send(self, interaction: discord.Interaction, button: ui.Button):
        payload = self.build_payload()
        if not payload.get("content") and not payload.get("embeds"):
            return await interaction.response.send_message("❌ Добавьте хотя бы текст или embed.", ephemeral=True)
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload) as resp:
                if resp.status in (200, 204):
                    await interaction.response.send_message("✅ Отправлено!", ephemeral=True)
                else:
                    text = await resp.text()
                    await interaction.response.send_message(f"❌ Ошибка {resp.status}: `{text[:200]}`", ephemeral=True)

    def _make_embed(self):
        embed = discord.Embed(
            title="Webhook Builder",
            description=self.build_preview(),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Текст → Embed → Отправить")
        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


async def setup(bot):
    await bot.add_cog(Utils(bot))
