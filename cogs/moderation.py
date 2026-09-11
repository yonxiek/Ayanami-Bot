import asyncio
import re
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from ui_components import AyanamiUI, Colors, Icons


def parse_duration(duration: str) -> timedelta | None:
    pattern = re.compile(r'(\d+)([smhd])')
    matches = pattern.findall(duration.lower())
    if not matches: return None
    time_dict = {}
    for value, unit in matches:
        if unit == 's': time_dict['seconds'] = int(value)
        elif unit == 'm': time_dict['minutes'] = int(value)
        elif unit == 'h': time_dict['hours'] = int(value)
        elif unit == 'd': time_dict['days'] = int(value)
    return timedelta(**time_dict)

class UnwarnModal(discord.ui.Modal, title="Снятие предупреждения"):
    warn_id = discord.ui.TextInput(label="ID Варна", placeholder="Введите числовой ID", required=True)
    
    def __init__(self, cog, target_member):
        super().__init__()
        self.cog = cog
        self.target_member = target_member
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.HTTPException as e:
            if e.code == 40060: pass
            else: raise

        embed = discord.Embed(color=discord.Color(0x2ecc71))
        embed.set_author(name="Снятие предупреждения")
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{self.target_member.mention} {self.target_member.name} {self.target_member.id}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.add_field(name="Причина", value=f"Предупреждение #{self.warn_id.value} снято", inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.cog.bot.user.display_avatar.url)

        await interaction.followup.send(embed=embed)
        self.cog.bot.dispatch("moderation_log", "unwarn", interaction.guild, self.target_member, interaction.user, reason=f"Снят варн #{self.warn_id.value}")
        await self.cog.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "unwarn", 1)

class Moderation(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def get_config_value(self, guild_id: int, key: str, default=None):
        config = await self.db.get_guild_config(str(guild_id))
        return config.get(key, default)

    @app_commands.command(name="clear", description="Очистить сообщения")
    @app_commands.describe(amount="Количество сообщений")
    @app_commands.default_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.set_author(name="Очистка")
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{interaction.channel.name} {len(deleted)}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.add_field(name="Причина", value=f"Удалено {len(deleted)} сообщений в {interaction.channel.mention}", inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="modstats", description="Статистика модератора")
    async def modstats(self, interaction: discord.Interaction, moderator: discord.Member = None):
        target = moderator or interaction.user
        stats = await self.db.get_mod_stats(str(interaction.guild.id), str(target.id))
        
        fields_map = {
            "mute": "Муты", "unmute": "Снятие мутов",
            "warn": "Варны", "unwarn": "Снятие варнов",
            "kick": "Кики", "ban": "Баны", "unban": "Разбаны",
            "blacklist": "ЧС", "unblacklist": "Снятие ЧС",
            "report_resolved": "Закрытые жалобы"
        }

        desc = ""
        total = 0
        for key, label in fields_map.items():
            count = stats.get(key, 0)
            desc += f"> **{label}:** `{count}`\n"
            total += count

        desc += f"> **Всего:** `{total}`"

        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.title = "Статистика модератора"
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Действия", value=desc, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="modstatsset", description="Установить или добавить значение статистики модератору")
    @app_commands.describe(member="Модератор",action="Тип действия (mute, warn, report_resolved, blacklist и т.д.)",mode="Режим (Установить точное число ИЛИ добавить к текущему)",count="Значение")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Установить (Set)", value="set"),
        app_commands.Choice(name="Добавить (Add)", value="add")
    ])
    @app_commands.default_permissions(administrator=True)
    async def modstats_set(self, interaction: discord.Interaction, member: discord.Member, action: str, mode: app_commands.Choice[str], count: int):
        try: await interaction.response.defer(ephemeral=True)
        except discord.HTTPException as e:
            if e.code == 40060: pass
            else: raise
            
        if mode.value == "set":
            await self.db.conn.execute('INSERT OR REPLACE INTO mod_stats (guild_id, moderator_id, action_type, count) VALUES (?, ?, ?, ?)', 
                                     (str(interaction.guild.id), str(member.id), action, count))
            await self.db.conn.commit()
        else:
            await self.db.increment_mod_stat(str(interaction.guild.id), str(member.id), action, count)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.title = "Изменение статистики"
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{member.mention} {member.name} {member.id}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        for name, value in [("Действие", action), ("Значение", str(count))]:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def send_punishment_notice(self, member, action: str, reason: str, guild: discord.Guild):
        try:
            embed = discord.Embed(color=discord.Color(0x2b2d31))
            embed.set_author(name="Модерация сервера", icon_url=self.bot.user.display_avatar.url)
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.add_field(name="Действие", value=f"Вы были **{action}**", inline=False)
            embed.add_field(name="Сервер", value=guild.name, inline=False)
            embed.add_field(name="Причина", value=reason or "Не указана", inline=False)
            embed.set_footer(text="Ayanami System")
            await member.send(embed=embed)
        except discord.HTTPException:
            pass
        except Exception:
            pass

    @app_commands.command(name="lock", description="Закрыть канал")
    async def lock(self, interaction: discord.Interaction):
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.title = "Канал закрыт"
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{interaction.channel.name}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unlock", description="Открыть канал")
    async def unlock(self, interaction: discord.Interaction):
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.title = "Канал открыт"
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{interaction.channel.name}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="mute", description="Выдать тайм-аут пользователю")
    @app_commands.describe(member="Участник", duration="Длительность (10s, 5m, 2h, 1d)", reason="Причина")
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: str,
                   reason: str = "Не указана"):
        delta = parse_duration(duration)
        if not delta:
            error_embed = discord.Embed(color=Colors.ERROR, title="❌ Ошибка формата", description="Используйте: `10s`, `5m`, `2h`, `1d`.")
            return await interaction.response.send_message(embed=error_embed, ephemeral=True)

        await interaction.response.defer()

        try:
            until = discord.utils.utcnow() + delta
            await member.timeout(until, reason=reason)
            await self.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "mute", 1)
            self.bot.dispatch("moderation_log", "mute", interaction.guild, member, interaction.user, reason=reason, duration=AyanamiUI.format_duration_ru(duration))

            embed = discord.Embed(color=Colors.MAIN)
            embed.set_author(name="Мут", icon_url=Icons.MUTE)
            if interaction.guild.icon:
                embed.set_thumbnail(url=interaction.guild.icon.url)
            if interaction.guild.banner:
                embed.set_image(url=interaction.guild.banner.url)
            mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
            user_line = f"{member.mention} {member.name} {member.id}"
            embed.add_field(name="Модератор", value=mod_line, inline=False)
            embed.add_field(name="Участник", value=user_line, inline=False)
            embed.add_field(name="Длительность", value=AyanamiUI.format_duration_ru(duration), inline=False)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        
            await self.send_punishment_notice(member, "замучены (тайм-аут)", reason, interaction.guild)
            await interaction.followup.send(embed=embed)

        except discord.Forbidden:
            error_embed = discord.Embed(color=Colors.ERROR, description="❌ У меня нет прав мутить этого пользователя.")
            await interaction.followup.send(embed=error_embed)
        except Exception as e:
            error_embed = discord.Embed(color=Colors.ERROR, description=f"❌ Ошибка: {e}")
            await interaction.followup.send(embed=error_embed)

    @app_commands.command(name="unmute", description="Снять тайм-аут (мут) с участника")
    @app_commands.describe(member="Участник", reason="Причина снятия")
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Снято модератором"):
        await interaction.response.defer()

        try:
            await member.timeout(None, reason=reason)
            
            await self.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "unmute", 1)
            self.bot.dispatch("moderation_log", "unmute", interaction.guild, member, interaction.user, reason=reason)

            embed = discord.Embed(color=discord.Color(0x2b2d31))
            embed.set_author(name="Снятие мута", icon_url=Icons.UNMUTE)
            if interaction.guild.icon:
                embed.set_thumbnail(url=interaction.guild.icon.url)
            if interaction.guild.banner:
                embed.set_image(url=interaction.guild.banner.url)
            mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
            user_line = f"{member.mention} {member.name} {member.id}"
            embed.add_field(name="Модератор", value=mod_line, inline=False)
            embed.add_field(name="Участник", value=user_line, inline=False)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)

            await interaction.followup.send(embed=embed)

        except discord.Forbidden:
            await interaction.followup.send("❌ У меня недостаточно прав для управления этим пользователем (возможно, его роль выше моей).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Произошла ошибка: {e}", ephemeral=True)

    @app_commands.command(name="warn", description="Выдать предупреждение участнику")
    @app_commands.describe(member="Участник", reason="Причина")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
        await self.db.conn.execute(
            'INSERT INTO warns (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)',
            (str(interaction.guild.id), str(member.id), str(interaction.user.id), reason, datetime.now().isoformat()))
        await self.db.conn.commit()
        await self.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "warn", 1)
        self.bot.dispatch("moderation_log", "warn", interaction.guild, member, interaction.user, reason=reason)

        # === Текущее количество варнов ===
        cursor = await self.db.conn.execute(
            'SELECT COUNT(*) FROM warns WHERE guild_id = ? AND user_id = ?',
            (str(interaction.guild.id), str(member.id)))
        row = await cursor.fetchone()
        warn_count = row[0] if row else 0

        # === Warn limit → автодействие ===
        config = await self.db.get_guild_config(str(interaction.guild.id))
        warn_limit = config.get("warn_limit", 0)
        warn_action = config.get("warn_action", "kick")
        if warn_limit > 0:
            if warn_count >= warn_limit:
                try:
                    if warn_action == "ban":
                        await interaction.guild.ban(member, reason=f"Достигнут лимит варнов ({warn_count}/{warn_limit})")
                        self.bot.dispatch("moderation_log", "ban", interaction.guild, member, interaction.user, reason=f"Автобан: {warn_count} варнов")
                        action_text = "забанен"
                    else:
                        await member.kick(reason=f"Достигнут лимит варнов ({warn_count}/{warn_limit})")
                        self.bot.dispatch("moderation_log", "kick", interaction.guild, member, interaction.user, reason=f"Автокик: {warn_count} варнов")
                        action_text = "кикнут"
                    # Удаляем все варны после автодействия
                    await self.db.conn.execute(
                        'DELETE FROM warns WHERE guild_id = ? AND user_id = ?',
                        (str(interaction.guild.id), str(member.id)))
                    await self.db.conn.commit()
                except discord.Forbidden:
                    action_text = None
                except Exception:
                    action_text = None
            else:
                action_text = None
        else:
            action_text = None

        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.set_author(name="Предупреждение", icon_url=Icons.WARN)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{member.mention} {member.name} {member.id}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        value_text = str(warn_count)
        if warn_limit > 0:
            value_text += f" / {warn_limit}"
            if action_text:
                value_text += f" → {action_text}"
        embed.add_field(name="Варнов", value=value_text, inline=False)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await self.send_punishment_notice(member, "предупреждены", reason, interaction.guild)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="warns", description="Посмотреть список предупреждений участника")
    @app_commands.describe(member="Участник (оставьте пустым для себя)")
    async def warns(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        cursor = await self.db.conn.execute(
            'SELECT id, moderator_id, reason, timestamp FROM warns WHERE guild_id = ? AND user_id = ?',
            (str(interaction.guild.id), str(target.id)))
        rows = await cursor.fetchall()

        description = ""
        if not rows:
            description = "Чисто! У участника нет активных предупреждений."
        else:
            warn_text = ""
            for r in rows:
                warn_text += f"**ID: `{r[0]}`** | Модератор: <@{r[1]}>\n> {r[2]}\n\n"
            description = warn_text

        embed = discord.Embed(title=f"### Нарушения: {target.name}", description=description, color=discord.Color(0x2b2d31))
        embed.set_footer(text="Ayanami System")

        view = discord.ui.View()
        if interaction.user.guild_permissions.moderate_members:
            unwarn_button = discord.ui.Button(label="Снять варн", style=discord.ButtonStyle.danger, emoji="🗑️")

            async def unwarn_callback(interaction: discord.Interaction):
                await interaction.response.send_modal(UnwarnModal(self, target))

            unwarn_button.callback = unwarn_callback
            view.add_item(unwarn_button)

        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="kick", description="Исключить участника с сервера")
    @app_commands.describe(member="Участник", reason="Причина исключения")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
        await member.kick(reason=reason)
        await self.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "kick", 1)
        self.bot.dispatch("moderation_log", "kick", interaction.guild, member, interaction.user, reason=reason)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.set_author(name="Кик", icon_url=Icons.KICK)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{member.mention} {member.name} {member.id}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        
        await self.send_punishment_notice(member, "кикнуты", reason, interaction.guild)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ban", description="Забанить участника (или ID, если его нет на сервере)")
    @app_commands.describe(member="Участник или его ID, которого нужно забанить",reason="Причина бана (необязательно)")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.User, reason: str = "Не указана"):
            await interaction.guild.ban(member, reason=reason)
            self.bot.dispatch("moderation_log", "ban", interaction.guild, member, interaction.user, reason=reason)
        
            embed = discord.Embed(color=discord.Color(0x2b2d31))
            embed.set_author(name="Бан", icon_url=Icons.BAN)
            if interaction.guild.icon:
                embed.set_thumbnail(url=interaction.guild.icon.url)
            if interaction.guild.banner:
                embed.set_image(url=interaction.guild.banner.url)
            mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
            user_line = f"{member.mention if hasattr(member, 'mention') else str(member.id)} {member.name} {member.id!s}"
            embed.add_field(name="Модератор", value=mod_line, inline=False)
            embed.add_field(name="Участник", value=user_line, inline=False)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
            await self.send_punishment_notice(member, "забанены", reason, interaction.guild)
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unban", description="Разбанить участника")
    @app_commands.describe(member="Пользователь или его ID, которого нужно разбанить")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, member: discord.User, reason: str = "Не указана"):

        await interaction.guild.unban(member)
        await self.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "unban", 1)
        self.bot.dispatch("moderation_log", "unban", interaction.guild, member, interaction.user, reason=reason)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.set_author(name="Разбан", icon_url=Icons.UNBAN)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{member.mention if hasattr(member, 'mention') else str(member.id)} {member.name} {member.id!s}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    async def sync_blacklist_role(self, guild: discord.Guild, role: discord.Role):
        try:
            await role.edit(permissions=discord.Permissions.none())
        except Exception: pass
        
        for category in guild.categories:
            try:
                await category.set_permissions(role, view_channel=False, send_messages=False, connect=False)
                await asyncio.sleep(0.1) 
            except Exception: pass
            
        for channel in guild.channels:
            if channel.category is None or not channel.permissions_synced:
                try:
                    await channel.set_permissions(role, view_channel=False, send_messages=False, connect=False)
                    await asyncio.sleep(0.1)
                except Exception: pass

    @app_commands.command(name="blacklist", description="Внести участника в ЧС и снять все роли")
    @app_commands.describe(user="Участник или ID", reason="Причина")
    @app_commands.default_permissions(manage_roles=True)
    async def blacklist(self, interaction: discord.Interaction, user: discord.User, reason: str = "Нарушение правил"):
        await interaction.response.defer()

        target_member = interaction.guild.get_member(user.id)
        role_id = 1539691318739992730
        role = interaction.guild.get_role(role_id)

        if not role:
            return await interaction.followup.send(f"❌ Ошибка: Роль ЧС (ID: `{role_id}`) не найдена на сервере.")

        if target_member:
            try:
                if target_member.top_role >= interaction.guild.me.top_role and interaction.user.id != interaction.guild.owner_id:
                    return await interaction.followup.send(
                        "❌ Я не могу внести в ЧС этого участника, так как его роль выше моей или равна ей.")

                roles_to_remove = [
                    r for r in target_member.roles
                    if r != interaction.guild.default_role
                       and not r.managed
                       and r < interaction.guild.me.top_role
                ]

                if roles_to_remove:
                    await target_member.remove_roles(*roles_to_remove, reason=f"Blacklist by {interaction.user}")

                await target_member.add_roles(role, reason=f"Blacklisted by {interaction.user}")

                try:
                    await target_member.edit(nick="Blacklisted")
                except:
                    pass

            except discord.Forbidden:
                return await interaction.followup.send(
                    "❌ Ошибка доступа: Проверьте, что моя роль находится выше всех остальных ролей.")
            except Exception as e:
                return await interaction.followup.send(f"❌ Произошла техническая ошибка: {e}")
        else:
            try:
                await interaction.guild.ban(user, reason=f"Blacklist (Offline) by {interaction.user}: {reason}")
            except discord.Forbidden:
                return await interaction.followup.send(
                    "❌ Не удалось забанить пользователя оффлайн (недостаточно прав).")

        await self.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "blacklist", 1)
        self.bot.dispatch("moderation_log", "blacklist", interaction.guild, user, interaction.user, reason=reason)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.set_author(name="Чёрный список", icon_url=Icons.BLACKLIST)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{user.mention if hasattr(user, 'mention') else str(user.id)} {user.name} {user.id!s}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await self.send_punishment_notice(user, "внесены в Чёрный список", reason, interaction.guild)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="unblacklist", description="Удалить участника из Чёрного списка")
    @app_commands.describe(user="Участник или ID")
    @app_commands.default_permissions(manage_roles=True)
    async def unblacklist(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer()

        target_member = interaction.guild.get_member(user.id)
        role_id = 1539691318739992730
        role = interaction.guild.get_role(role_id)

        found_in_logs = False

        if target_member:
            if role and role in target_member.roles:
                try:
                    await target_member.remove_roles(role, reason="Unblacklist")
                    await target_member.edit(nick=None)
                    found_in_logs = True
                except:
                    pass

        try:
            await interaction.guild.unban(user, reason=f"Unblacklist by {interaction.user}")
            found_in_logs = True
        except discord.NotFound:
            pass
        except discord.Forbidden:
            return await interaction.followup.send("❌ Ошибка прав: Не могу разбанить пользователя.")

        if found_in_logs or target_member:
            await self.db.increment_mod_stat(str(interaction.guild.id), str(interaction.user.id), "unblacklist", 1)
        self.bot.dispatch("moderation_log", "unblacklist", interaction.guild, user, interaction.user)

        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.set_author(name="Снятие с ЧС", icon_url=Icons.UNBAN)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{user.mention if hasattr(user, 'mention') else str(user.id)} {user.name} {user.id!s}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await interaction.followup.send(embed=embed)


    @app_commands.command(name="promote", description="Повысить участника в должности")
    @app_commands.describe(member="Участник", role="Новая должность")
    @app_commands.default_permissions(administrator=True)
    async def promote(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        staff_roles = await self.get_config_value(interaction.guild.id, "staff_roles", [])
        try:
            roles_to_remove = [r for r in member.roles if r.id in staff_roles and r.id != role.id]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Promote by {interaction.user}")
            await member.add_roles(role, reason=f"Promote by {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Недостаточно прав для управления ролями.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.title = "Повышение"
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{member.mention} {member.name} {member.id}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.add_field(name="Причина", value=f"Повышен до {role.mention}", inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        
        log_channel_id = await self.get_config_value(interaction.guild.id, "promote_log_channel_id")
        log_channel = self.bot.get_channel(int(log_channel_id)) if log_channel_id else None
        if log_channel:
            log_embed = discord.Embed(color=discord.Color.green())
            log_embed.title = "Повышение"
            if interaction.guild.icon:
                log_embed.set_thumbnail(url=interaction.guild.icon.url)
            if interaction.guild.banner:
                log_embed.set_image(url=interaction.guild.banner.url)
            mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
            user_line = f"{member.mention} {member.name} {member.id}"
            log_embed.add_field(name="Модератор", value=mod_line, inline=False)
            log_embed.add_field(name="Участник", value=user_line, inline=False)
            log_embed.add_field(name="Причина", value=f"Повышен до {role.mention}", inline=False)
            log_embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
            await log_channel.send(embed=log_embed)
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="demote", description="Снять участника с должности")
    @app_commands.describe(member="Участник", role="Снимаемая роль")
    @app_commands.default_permissions(administrator=True)
    async def demote(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            await member.remove_roles(role, reason=f"Demote by {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Недостаточно прав для управления ролями.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
        
        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.title = "Понижение"
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{member.mention} {member.name} {member.id}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.add_field(name="Причина", value=f"Снят с должности {role.mention}", inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        
        log_channel_id = await self.get_config_value(interaction.guild.id, "demote_log_channel_id")
        log_channel = self.bot.get_channel(int(log_channel_id)) if log_channel_id else None
        if log_channel:
            log_embed = discord.Embed(color=discord.Color.red())
            log_embed.title = "Понижение"
            if interaction.guild.icon:
                log_embed.set_thumbnail(url=interaction.guild.icon.url)
            if interaction.guild.banner:
                log_embed.set_image(url=interaction.guild.banner.url)
            mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
            user_line = f"{member.mention} {member.name} {member.id}"
            log_embed.add_field(name="Модератор", value=mod_line, inline=False)
            log_embed.add_field(name="Участник", value=user_line, inline=False)
            log_embed.add_field(name="Причина", value=f"Снят с должности {role.mention}", inline=False)
            log_embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
            await log_channel.send(embed=log_embed)
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="modnote", description="Добавить заметку модератора об участнике")
    @app_commands.describe(member="Участник", note="Текст заметки")
    @app_commands.default_permissions(moderate_members=True)
    async def modnote(self, interaction: discord.Interaction, member: discord.Member, note: str):
        await self.db.conn.execute(
            'INSERT INTO mod_notes (guild_id, user_id, moderator_id, note, timestamp) VALUES (?, ?, ?, ?, ?)',
            (str(interaction.guild.id), str(member.id), str(interaction.user.id), note, datetime.now().isoformat()))
        await self.db.conn.commit()

        embed = discord.Embed(color=discord.Color(0x2b2d31))
        embed.title = "Заметка модератора"
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if interaction.guild.banner:
            embed.set_image(url=interaction.guild.banner.url)
        mod_line = f"{interaction.user.mention} {interaction.user.name} {interaction.user.id}"
        user_line = f"{member.mention} {member.name} {member.id}"
        embed.add_field(name="Модератор", value=mod_line, inline=False)
        embed.add_field(name="Участник", value=user_line, inline=False)
        embed.add_field(name="Причина", value=note, inline=False)
        embed.set_footer(text="Ayanami System", icon_url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="history", description="История наказаний и заметок участника")
    @app_commands.describe(member="Участник")
    @app_commands.default_permissions(moderate_members=True)
    async def history(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        cursor = await self.db.conn.execute(
            'SELECT id, moderator_id, reason, timestamp FROM warns WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC',
            (str(interaction.guild.id), str(member.id)))
        warns = await cursor.fetchall()

        cursor = await self.db.conn.execute(
            'SELECT moderator_id, note, timestamp FROM mod_notes WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC',
            (str(interaction.guild.id), str(member.id)))
        notes = await cursor.fetchall()

        lines = []
        if warns:
            lines.append(f"### ⚠️ Варны ({len(warns)})")
            for w in warns:
                lines.append(f"• **#{w[0]}** от <@{w[1]}> — {w[2]} (<t:{int(datetime.fromisoformat(w[3]).timestamp())}:R>)")
        if notes:
            lines.append(f"\n### 📝 Заметки ({len(notes)})")
            for n in notes:
                lines.append(f"• от <@{n[0]}> — {n[1]} (<t:{int(datetime.fromisoformat(n[2]).timestamp())}:R>)")

        if not lines:
            lines.append(f"### {member.name}\nУ участника нет варнов или заметок.")

        embed = discord.Embed(title=f"История: {member.name}", description="\n".join(lines), color=discord.Color(0x2b2d31))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ============================================================
    #            ПРЕФИКСНЫЕ (текстовые) ВЕРСИИ КОМАНД
    # ============================================================

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def clear_prefix(self, ctx, amount: int):
        from prefix_adapter import InteractionAdapter
        await self.clear.callback(self, InteractionAdapter(ctx), amount)

    @commands.command(name="modstats")
    async def modstats_prefix(self, ctx, moderator: discord.Member = None):
        from prefix_adapter import InteractionAdapter
        await self.modstats.callback(self, InteractionAdapter(ctx), moderator)

    @commands.command(name="modstatsset")
    @commands.has_permissions(administrator=True)
    async def modstats_set_prefix(self, ctx, member: discord.Member, action: str, mode: str, count: int):
        from prefix_adapter import InteractionAdapter, make_choice
        await self.modstats_set.callback(self, InteractionAdapter(ctx), member, action, make_choice(mode), count)

    @commands.command(name="lock")
    async def lock_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.lock.callback(self, InteractionAdapter(ctx))

    @commands.command(name="unlock")
    async def unlock_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.unlock.callback(self, InteractionAdapter(ctx))

    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def mute_prefix(self, ctx, member: discord.Member, duration: str, *, reason: str = "Не указана"):
        from prefix_adapter import InteractionAdapter
        await self.mute.callback(self, InteractionAdapter(ctx), member, duration, reason)

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def unmute_prefix(self, ctx, member: discord.Member, *, reason: str = "Снято модератором"):
        from prefix_adapter import InteractionAdapter
        await self.unmute.callback(self, InteractionAdapter(ctx), member, reason)

    @commands.command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def warn_prefix(self, ctx, member: discord.Member, *, reason: str = "Не указана"):
        from prefix_adapter import InteractionAdapter
        await self.warn.callback(self, InteractionAdapter(ctx), member, reason)

    @commands.command(name="warns")
    async def warns_prefix(self, ctx, member: discord.Member = None):
        from prefix_adapter import InteractionAdapter
        await self.warns.callback(self, InteractionAdapter(ctx), member)

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick_prefix(self, ctx, member: discord.Member, *, reason: str = "Не указана"):
        from prefix_adapter import InteractionAdapter
        await self.kick.callback(self, InteractionAdapter(ctx), member, reason)

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban_prefix(self, ctx, member, *, reason: str = "Не указана"):
        from prefix_adapter import InteractionAdapter
        try:
            m = await commands.UserConverter().convert(ctx, member)
        except commands.BadArgument:
            try:
                m = await commands.MemberConverter().convert(ctx, member)
            except commands.BadArgument:
                return await ctx.send("❌ Участник или ID не найден.")
        await self.ban.callback(self, InteractionAdapter(ctx), m, reason)

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban_prefix(self, ctx, member, *, reason: str = "Не указана"):
        from prefix_adapter import InteractionAdapter
        try:
            m = await commands.UserConverter().convert(ctx, member)
        except commands.BadArgument:
            return await ctx.send("❌ Пользователь или ID не найден.")
        await self.unban.callback(self, InteractionAdapter(ctx), m, reason)

    @commands.command(name="blacklist")
    @commands.has_permissions(manage_roles=True)
    async def blacklist_prefix(self, ctx, user, *, reason: str = "Нарушение правил"):
        from prefix_adapter import InteractionAdapter
        try:
            u = await commands.UserConverter().convert(ctx, user)
        except commands.BadArgument:
            try:
                u = await commands.MemberConverter().convert(ctx, user)
            except commands.BadArgument:
                return await ctx.send("❌ Участник или ID не найден.")
        await self.blacklist.callback(self, InteractionAdapter(ctx), u, reason)

    @commands.command(name="unblacklist")
    @commands.has_permissions(manage_roles=True)
    async def unblacklist_prefix(self, ctx, user):
        from prefix_adapter import InteractionAdapter
        try:
            u = await commands.UserConverter().convert(ctx, user)
        except commands.BadArgument:
            try:
                u = await commands.MemberConverter().convert(ctx, user)
            except commands.BadArgument:
                return await ctx.send("❌ Участник или ID не найден.")
        await self.unblacklist.callback(self, InteractionAdapter(ctx), u)

    @commands.command(name="promote")
    @commands.has_permissions(administrator=True)
    async def promote_prefix(self, ctx, member: discord.Member, role: discord.Role):
        from prefix_adapter import InteractionAdapter
        await self.promote.callback(self, InteractionAdapter(ctx), member, role)

    @commands.command(name="demote")
    @commands.has_permissions(administrator=True)
    async def demote_prefix(self, ctx, member: discord.Member, role: discord.Role):
        from prefix_adapter import InteractionAdapter
        await self.demote.callback(self, InteractionAdapter(ctx), member, role)

    @commands.command(name="modnote")
    @commands.has_permissions(moderate_members=True)
    async def modnote_prefix(self, ctx, member: discord.Member, *, note: str):
        from prefix_adapter import InteractionAdapter
        await self.modnote.callback(self, InteractionAdapter(ctx), member, note)

    @commands.command(name="history")
    @commands.has_permissions(moderate_members=True)
    async def history_prefix(self, ctx, member: discord.Member):
        from prefix_adapter import InteractionAdapter
        await self.history.callback(self, InteractionAdapter(ctx), member)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
