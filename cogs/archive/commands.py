import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import aiohttp
import json
import re
from datetime import datetime, timezone, timedelta
from db import Database
from ui_components import Icons, Colors, AyanamiUI


def parse_duration(duration: str) -> Optional[timedelta]:
    parts = duration.lower().split()
    total = 0
    for part in parts:
        if part.endswith('d'):
            try: total += int(part[:-1]) * 86400
            except ValueError: return None
        elif part.endswith('h'):
            try: total += int(part[:-1]) * 3600
            except ValueError: return None
        elif part.endswith('m'):
            try: total += int(part[:-1]) * 60
            except ValueError: return None
        elif part.endswith('s'):
            try: total += int(part[:-1])
            except ValueError: return None
        else:
            return None
    return timedelta(seconds=total) if total > 0 else None


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
    def build_raid_description(queue, link, enemies=None, alliance=None) -> str:
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


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.bloxlink_api_key = ""

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

    async def _send_raid_dms(self, members, embed: discord.Embed, jump_url: str):
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Присоединиться к сбору", url=jump_url))
        for member in members:
            if not member.bot:
                try:
                    await member.send(
                        content=f"{member.mention}, **⚔️ НАЧАЛСЯ НОВЫЙ СБОР!**",
                        embed=embed,
                        view=view
                    )
                    await asyncio.sleep(0.1)
                except discord.Forbidden:
                    pass

    # ==========================================
    #               RAID
    # ==========================================

    @app_commands.command(name="raid", description="Создать новый рейд")
    @app_commands.default_permissions(manage_messages=True)
    async def raid_slash(
        self, interaction: discord.Interaction, enemies: str, alliance: str, link: str,
        ping: Optional[discord.Role] = None, lines_channel: Optional[discord.TextChannel] = None, photo: Optional[discord.Attachment] = None
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            config = await self.db.get_guild_config(str(interaction.guild.id))
            raid_cfg = config.get("raid_ping_role_id", None)
            lines_cfg = config.get("raid_line_channel_id", None)

            target_ping = ping or (interaction.guild.get_role(int(raid_cfg)) if raid_cfg else None)
            target_channel = lines_channel or (interaction.guild.get_channel(int(lines_cfg)) if lines_cfg else None)

            if not target_ping or not target_channel:
                err_embed = discord.Embed(title="Ошибка", description="> Не указана роль для пинга или канал для лайнов.\nУкажите их в команде или настройте в `/setup`.", color=Colors.MAIN)
                return await interaction.followup.send(embed=err_embed, ephemeral=True)

            valid_link = RaidUtils.validate_and_format_link(link)
            if not valid_link:
                err_embed = discord.Embed(title="Ошибка", description="> Ссылка не распознана. Используйте корректный формат.", color=Colors.MAIN)
                return await interaction.followup.send(embed=err_embed, ephemeral=True)

            desc = RaidUtils.build_raid_description([], valid_link, enemies, alliance)
            embed = discord.Embed(description=desc)
            if photo:
                embed.set_image(url=photo.url)

            mention_text = RaidUtils.get_safe_mention(target_ping)
            raid_msg = await interaction.channel.send(content=mention_text, embed=embed, view=RaidPersistentView(self))

            await self.db.conn.execute(
                "INSERT INTO raids_v3 (message_id, channel_id, target_channel_id, link, enemies, alliance, ping_role_id, queue_data, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(raid_msg.id), str(interaction.channel.id), str(target_channel.id), link, enemies, alliance, str(target_ping.id), "[]", "started", datetime.now(timezone.utc).isoformat())
            )
            await self.db.conn.commit()

            if target_ping:
                self.bot.loop.create_task(self._send_raid_dms(target_ping.members, embed, raid_msg.jump_url))

            done_embed = discord.Embed(title="Успех", description="> Рейд запущен!\n> Рассылка в ЛС участникам начата.", color=Colors.MAIN)
            await interaction.followup.send(embed=done_embed, ephemeral=True)

        except Exception as e:
            err_embed = discord.Embed(title="Критическая Ошибка", description=f"> `{e}`\nПроверьте права бота.", color=Colors.MAIN)
            await interaction.followup.send(embed=err_embed, ephemeral=True)

    @app_commands.command(name="raidstats", description="Посмотреть статистику участия в рейдах")
    async def raidstats_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = member or interaction.user
        user_data = await self.db.get_or_create_user(str(interaction.guild.id), str(target.id))
        attended = user_data.get('raids_attended', 0)
        balance = user_data.get('balance', 0)

        desc = (
            f"**Статистика участника {target.mention}**\n\n"
            f"> ⚔️ **Посещено рейдов:** `{attended}`\n"
            f"> 💰 **Монетки:** `{balance}`\n"
        )
        embed = discord.Embed(description=desc, color=Colors.MAIN)
        embed.set_author(name=f"Рейды: {target.display_name}", icon_url=target.display_avatar.url)
        embed.set_footer(text="Ayanami System", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.followup.send(embed=embed)

    # ==========================================
    #               SNIPE
    # ==========================================

    @app_commands.command(name="snipe", description="Объявить охоту (snipe) за игроком в Roblox")
    @app_commands.describe(roblox_link="Ссылка на профиль Roblox цели", reason="Причина охоты (необязательно)")
    async def snipe_slash(self, interaction: discord.Interaction, roblox_link: str, reason: str = "Без причины"):
        await interaction.response.defer(ephemeral=True)

        match = re.match(r"^https?:\/\/(www\.)?roblox\.com\/users\/(\d+)\/profile.*$", roblox_link.strip())
        if not match:
            return await interaction.followup.send(
                "❌ **Обнаружена подозрительная ссылка!**\nПожалуйста, укажите официальную ссылку на профиль Roblox.\n"
                "*Пример: https://www.roblox.com/users/12345678/profile*",
                ephemeral=True
            )

        roblox_id = match.group(2)
        username = "Неизвестно"
        display_name = "Неизвестно"
        avatar_url = None

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://users.roblox.com/v1/users/{roblox_id}") as resp:
                if resp.status != 200:
                    return await interaction.followup.send("❌ Не удалось найти пользователя с таким ID в Roblox.", ephemeral=True)
                r_data = await resp.json()
                username = r_data.get("name", username)
                display_name = r_data.get("displayName", display_name)

            av_req_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={roblox_id}&size=420x420&format=Png&isCircular=false"
            async with session.get(av_req_url) as resp:
                if resp.status == 200:
                    av_data = await resp.json()
                    if av_data.get("data"):
                        avatar_url = av_data["data"][0].get("imageUrl")

        embed = discord.Embed(title="🎯 ОХОТА ОБЪЯВЛЕНА", color=0x8b0000, timestamp=discord.utils.utcnow())
        embed.description = f"**Новая цель обнаружена!** Устранить при первой возможности.\n\n**Причина:**\n> {reason}"
        embed.add_field(name="Никнейм", value=f"`{username}`", inline=True)
        embed.add_field(name="Отображаемое имя", value=f"`{display_name}`", inline=True)
        embed.add_field(name="Ссылка на профиль", value=f"🔗 **[Перейти в Roblox](https://www.roblox.com/users/{roblox_id}/profile)**", inline=False)

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        snipe_channel_id = None
        config = await self.db.get_guild_config(str(interaction.guild.id))
        snipe_channel_id = config.get("snipe_channel_id")

        if snipe_channel_id:
            channel = self.bot.get_channel(int(snipe_channel_id))
            if channel:
                await channel.send(embed=embed)
                await interaction.followup.send("✅ Охота объявлена!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Канал для охот не найден.", ephemeral=True)
        else:
            await interaction.followup.send(embed=embed)

    # ==========================================
    #               STAGE
    # ==========================================

    @app_commands.command(name="stage", description="Установить параметры участника")
    @app_commands.choices(stage=[app_commands.Choice(name=f"Stage {i}", value=f"Stage {i}") for i in range(1, 6)])
    @app_commands.choices(rank=[app_commands.Choice(name=x, value=x) for x in ["High", "Mid", "Low"]])
    @app_commands.choices(power=[app_commands.Choice(name=x, value=x) for x in ["Strong", "Stable", "Weak"]])
    @app_commands.default_permissions(manage_roles=True)
    async def stage(self, interaction: discord.Interaction, member: discord.Member, stage: Optional[str] = None, rank: Optional[str] = None, power: Optional[str] = None, roblox_nick: Optional[str] = None):
        await interaction.response.defer()
        icon = interaction.guild.icon.url if interaction.guild.icon else None

        api_data = await self._fetch_roblox_data(interaction.guild.id, member.id)
        if roblox_nick:
            final_nick = roblox_nick
        elif api_data:
            final_nick = f"{api_data['display_name']} (@{api_data['username']})"
        else:
            user_data = await self.db.get_or_create_user(str(interaction.guild.id), str(member.id))
            final_nick = user_data.get('roblox_nick', member.display_name)

        await self.db.update_user_stats(str(interaction.guild.id), str(member.id), roblox_nick=final_nick)

        groups = {
            "stage": ["Stage 1", "Stage 2", "Stage 3", "Stage 4", "Stage 5"],
            "rank": ["High", "Mid", "Low"],
            "power": ["Strong", "Stable", "Weak"]
        }
        try:
            for key, new_val in [("stage", stage), ("rank", rank), ("power", power)]:
                if new_val:
                    role_obj = discord.utils.get(interaction.guild.roles, name=new_val)
                    if role_obj:
                        to_remove = [r for r in member.roles if r.name in groups[key]]
                        if to_remove:
                            await member.remove_roles(*to_remove)
                        await member.add_roles(role_obj)

            embed = discord.Embed(color=0x2b2d31)
            embed.set_author(name="Обновление данных участника", icon_url=member.display_avatar.url)
            embed.description = (
                f"**Участник:** {member.mention}\n"
                f"**Статус:** `{stage} | {rank}`\n\n"
                f"Роли были автоматически обновлены."
            )
            embed.set_footer(text="Ayanami System", icon_url=icon)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Ошибка: {e}")

    # ==========================================
    #               HELPERS
    # ==========================================

    async def _fetch_roblox_data(self, guild_id, user_id):
        try:
            url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{user_id}"
            headers = {"Authorization": self.bloxlink_api_key}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    roblox_id = data.get("robloxID")
                    if not roblox_id:
                        return None

                user_url = f"https://users.roblox.com/v1/users/{roblox_id}"
                async with session.get(user_url) as resp:
                    if resp.status != 200:
                        return None
                    user_data = await resp.json()
                    return {
                        "roblox_id": str(roblox_id),
                        "username": user_data.get("name"),
                        "display_name": user_data.get("displayName"),
                        "description": user_data.get("description", ""),
                    }
        except Exception:
            return None


async def setup(bot):
    await bot.add_cog(Commands(bot))
