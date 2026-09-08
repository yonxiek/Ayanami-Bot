import discord
from discord.ext import commands
from discord import app_commands
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from db import Database
from ui_components import Icons, Colors, AyanamiUI
import asyncio


class RaidUtils:
    ALLOWED_KEYWORDS = ["roblox.com", "roqol.io", "ropro.io", "test"]

    @classmethod
    def validate_and_format_link(cls, link: str) -> Optional[str]:
        link_lower = link.lower()
        if not any(kw in link_lower for kw in cls.ALLOWED_KEYWORDS):
            return None
        if link_lower == "test":
            return "https://roblox.com/test-link"
        if not link_lower.startswith(('http://', 'https://', 'discord://')):
            return f"https://{link}"
        return link

    @staticmethod
    def build_raid_description(queue: List[Dict[str, Any]], link: str, enemies: str = None, alliance: str = None) -> str:
        enemies_text = f"# {enemies}\n\n" if enemies else ""
        alliance_text = f"## Альянс: {alliance}\n\n" if alliance else ""
        if not queue:
            queue_text = "*Пока никого нет...*"
        else:
            queue_text = "\n".join([f"**Line {q['line']}** — <@{q['user_id']}>" for q in queue])
        return f"{enemies_text}{alliance_text}**Лайны:**\n{queue_text}\n\n## [Присоединиться]({link})"

    @staticmethod
    def get_safe_mention(role: discord.Role) -> str:
        return "@everyone" if role.is_default() else role.mention


class RaidLineModal(discord.ui.Modal, title="Занять лайн"):
    line_input = discord.ui.TextInput(label="Ваш лайн", placeholder="Число лайна", max_length=5, required=True)

    def __init__(self, cog, raid_data: dict):
        super().__init__()
        self.cog = cog
        self.raid_data = raid_data

    async def on_submit(self, interaction: discord.Interaction):
        try:
            line_num = int(self.line_input.value.strip())
            if line_num <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("Номер лайна должен быть положительным числом.", ephemeral=True)
        await self.cog.process_line_claim(user=interaction.user, line_num=line_num, raid_data=self.raid_data, interaction=interaction)


class RaidPersistentView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def _get_raid_or_error(self, interaction: discord.Interaction) -> Optional[dict]:
        msg_id = str(interaction.message.id)
        cursor = await self.cog.db.conn.execute("SELECT * FROM raids_v3 WHERE message_id = ?", (msg_id,))
        row = await cursor.fetchone()
        if not row:
            await interaction.response.send_message("Этот рейд больше не существует.", ephemeral=True)
            return None
        columns = [col[0] for col in cursor.description]
        raid_data = dict(zip(columns, row))
        if raid_data["status"] == "ended":
            await interaction.response.send_message("Этот рейд завершён.", ephemeral=True)
            return None
        return raid_data

    @discord.ui.button(label='Занять лайн', style=discord.ButtonStyle.success, custom_id="raid_join_queue_btn")
    async def join_raid(self, interaction: discord.Interaction, button: discord.ui.Button):
        raid_data = await self._get_raid_or_error(interaction)
        if raid_data:
            await interaction.response.send_modal(RaidLineModal(self.cog, raid_data))

    @discord.ui.button(label='Завершить', style=discord.ButtonStyle.danger, custom_id="raid_end_btn")
    async def end_raid(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Только администраторы могут завершить рейд.", ephemeral=True)
        raid_data = await self._get_raid_or_error(interaction)
        if not raid_data:
            return
        await self.cog.db.conn.execute("UPDATE raids_v3 SET status = 'ended' WHERE message_id = ?", (raid_data['message_id'],))
        await self.cog.db.conn.commit()
        await interaction.message.edit(view=None)
        await interaction.response.send_message("Рейд завершён.", ephemeral=True)


class Raids(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = Database()

    async def cog_load(self):
        self.bot.add_view(RaidPersistentView(self))

    async def process_line_claim(self, user, line_num: int, raid_data: dict, interaction=None):
        msg_id = raid_data["message_id"]
        queue = json.loads(raid_data["queue_data"])

        if interaction:
            await self.db.mark_raid_attendance(str(interaction.guild.id), str(user.id), msg_id)

        queue = [q for q in queue if str(q["user_id"]) != str(user.id)]
        queue.append({"user_id": str(user.id), "line": line_num})
        queue.sort(key=lambda x: int(x["line"]))

        await self.db.conn.execute("UPDATE raids_v3 SET queue_data = ? WHERE message_id = ?", (json.dumps(queue), msg_id))
        await self.db.conn.commit()

        valid_link = RaidUtils.validate_and_format_link(raid_data["link"])
        announce_channel = self.bot.get_channel(int(raid_data["channel_id"]))

        if announce_channel:
            try:
                raid_msg = await announce_channel.fetch_message(int(msg_id))
                embed = raid_msg.embeds[0]
                embed.description = RaidUtils.build_raid_description(queue, valid_link, raid_data["enemies"], raid_data.get("alliance", ""))
                await raid_msg.edit(content=raid_msg.content, embed=embed)
            except discord.NotFound:
                pass

        if interaction and not interaction.response.is_done():
            await interaction.response.defer()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        config = await self.db.get_guild_config(str(message.guild.id))
        lines_cfg = config.get("raid_line_channel_id")
        if not lines_cfg or message.channel.id != int(lines_cfg):
            return
        cursor = await self.db.conn.execute(
            "SELECT message_id FROM raids_v3 WHERE target_channel_id = ? AND status = 'started' ORDER BY created_at DESC LIMIT 1",
            (str(message.channel.id),)
        )
        active_raid = await cursor.fetchone()
        if active_raid:
            await self.db.mark_raid_attendance(str(message.guild.id), str(message.author.id), active_raid['message_id'])


async def setup(bot: commands.Bot):
    await bot.add_cog(Raids(bot))
