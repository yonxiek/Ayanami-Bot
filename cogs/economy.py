import discord
from discord.ext import commands
from discord import app_commands
import re
from typing import Optional
import aiohttp
from db import Database
from datetime import datetime
from ui_components import Icons, Colors, AyanamiUI
import config
from voice_tracker import VoiceTrackerMixin



class Economy(VoiceTrackerMixin, commands.Cog):
    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        self.db = Database()
        self.bloxlink_api_key = config.BLOXLINK_API_KEY
        self.SNIPE_WEBHOOK_URL = config.SNIPE_WEBHOOK_URL

    async def cog_load(self):
        self.restore_voice_sessions(self.bot)

    async def fetch_roblox_data_from_api(self, guild_id: int, user_id: int) -> Optional[dict]:
        url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{user_id}"
        headers = {"Authorization": self.bloxlink_api_key}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200: return None
                    data = await resp.json()
                    roblox_id = data.get("robloxID")
                if not roblox_id: return None
                rbx_url = f"https://users.roblox.com/v1/users/{roblox_id}"
                async with session.get(rbx_url) as r_resp:
                    if r_resp.status == 200:
                        r_data = await r_resp.json()
                        return {"username": r_data.get("name"), "display_name": r_data.get("displayName")}
        except Exception: return None
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        guild_id, user_id = str(message.guild.id), str(message.author.id)
        await self.db.create_user(guild_id, user_id)
        await self.db.conn.execute('UPDATE users SET total_messages = total_messages + 1 WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        await self.db.conn.commit()
        try:
            cursor = await self.db.conn.execute('SELECT total_messages FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
            row = await cursor.fetchone()
            total = row['total_messages'] if row else 0
            from cogs.achievements import award_achievement
            await award_achievement(self.db, guild_id, user_id, "first_message", message.author)
            if total >= 100:
                await award_achievement(self.db, guild_id, user_id, "messages_100", message.author)
            if total >= 1000:
                await award_achievement(self.db, guild_id, user_id, "messages_1000", message.author)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot: return
        if before.channel is None and after.channel is not None:
            self.track_voice_join(member.guild.id, member.id)
            await self.db.update_activity(str(member.guild.id), str(member.id), "voice_join")
        elif before.channel is not None and after.channel is None:
            minutes, _ = self.track_voice_leave(member.guild.id, member.id)
            if minutes > 0:
                guild_id, user_id = str(member.guild.id), str(member.id)
                await self.db.create_user(guild_id, user_id)
                await self.db.conn.execute('UPDATE users SET total_voice_minutes = total_voice_minutes + ? WHERE guild_id = ? AND user_id = ?', (minutes, guild_id, user_id))
                await self.db.conn.commit()
                try:
                    cursor = await self.db.conn.execute('SELECT total_voice_minutes FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
                    row = await cursor.fetchone()
                    total_voice = row['total_voice_minutes'] if row else 0
                    from cogs.achievements import award_achievement
                    if total_voice >= 60:
                        await award_achievement(self.db, guild_id, user_id, "voice_60", member)
                    if total_voice >= 300:
                        await award_achievement(self.db, guild_id, user_id, "voice_300", member)
                except Exception:
                    pass

    def format_time(self, minutes: int) -> str:
        if minutes < 60: return f"{minutes} мин."
        return f"{minutes // 60} ч. {minutes % 60} мин."

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        member = payload.member
        if not member or member.bot:
            return
        await self.db.update_activity(str(payload.guild_id), str(member.id), "reactions")

    @app_commands.command(name="profile", description="Профиль")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        if not interaction.guild: return
        await interaction.response.defer()
        target = member or interaction.user
        guild_icon = interaction.guild.icon.url if interaction.guild.icon else None
        data = await self.db.get_or_create_user(str(interaction.guild.id), str(target.id))
        api_data = await self.fetch_roblox_data_from_api(interaction.guild.id, target.id)
        if api_data:
            roblox_nick = f"{api_data['display_name']} (@{api_data['username']})"
            await self.db.update_user_stats(str(interaction.guild.id), str(target.id), roblox_nick=roblox_nick)
        else: roblox_nick = data.get('roblox_nick', target.display_name)

        bal = data.get('balance', 0)
        total_msgs = data.get('total_messages', 0)
        total_voice = data.get('total_voice_minutes', 0)
        total_commands = data.get('total_commands', 0)
        level = data.get('level', 1)
        exp = data.get('exp', 0)
        ongoing = self.get_ongoing_minutes(interaction.guild.id, target.id)
        if ongoing:
            total_voice += ongoing

        activities = await self.db.get_user_activities(str(interaction.guild.id), str(target.id))
        voice_joins = activities.get('voice_join', 0)
        reactions = activities.get('reactions', 0)

        streak = await self.db.get_daily_streak(str(interaction.guild.id), str(target.id))

        ach_count = 0
        try:
            from cogs.achievements import award_achievement
            if bal >= 1000:
                await award_achievement(self.db, str(interaction.guild.id), str(target.id), "rich_1000", target)
            if bal >= 10000:
                await award_achievement(self.db, str(interaction.guild.id), str(target.id), "rich_10000", target)
            ach_count = await self.db.count_achievements(str(interaction.guild.id), str(target.id))
        except Exception:
            pass

        titles = await self.db.get_user_titles(str(interaction.guild.id), str(target.id))
        active_title = next((t['emoji'] + " " + t['title'] for t in titles if t['active']), None)
        title_text = f"\n> {active_title}" if active_title else ""

        next_level_xp = level ** 2 * 100
        current_level_xp = (level - 1) ** 2 * 100
        xp_in_level = exp - current_level_xp
        xp_needed = next_level_xp - current_level_xp
        progress = min(xp_in_level / xp_needed, 1.0) if xp_needed > 0 else 1.0
        filled = int(progress * 20)
        bar = "█" * filled + "░" * (20 - filled)

        top = await self.db.get_top_users_by_level(str(interaction.guild.id), 100)
        rank_pos = next((i + 1 for i, u in enumerate(top) if u['user_id'] == str(target.id)), len(top) + 1)

        is_booster = target.premium_since is not None
        booster_text = " ⚡ Бустер (+65% XP)" if is_booster else ""

        description = (
            f"### {target.display_name}{title_text}\n"
            f"> 👤 Discord: {target.name}\n"
            f"> 🎮 Roblox: {roblox_nick}\n"
            f"> 📅 На сервере: <t:{int(target.joined_at.timestamp())}:R>\n\n"
            f"### 📊 Активность\n"
            f"> 💬 Сообщения: **{total_msgs}**\n"
            f"> 🎙️ Голос: **{self.format_time(total_voice)}**\n"
            f"> ⚡ Команды: **{total_commands}**\n"
            f"> 🔗 Входы в голос: **{voice_joins}**\n"
            f"> 😊 Реакции: **{reactions}**\n"
            f"> 🔥 Серия дней: **{streak}**\n\n"
            f"### 💰 Баланс: **{bal}** {AyanamiUI.E_RP}\n"
            f"> 🏆 Достижения: **{ach_count}** из 19\n\n"
            f"### 📈 Уровень {level} | Ранг #{rank_pos}{booster_text}\n"
            f"> `{bar}` `{xp_in_level}/{xp_needed}` XP"
        )

        embed = discord.Embed(
            title=f"Профиль — {target.display_name}",
            description=description,
            color=Colors.MAIN,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="top", description="Таблица лидеров")
    @app_commands.describe(tab="Категория топа")
    @app_commands.choices(tab=[
        app_commands.Choice(name="Монетки", value="coins"),
        app_commands.Choice(name="Уровень", value="level"),
        app_commands.Choice(name="Сообщения", value="messages"),
        app_commands.Choice(name="Голос", value="voice"),
    ])
    async def top(self, interaction: discord.Interaction, tab: str = "coins"):
        if not interaction.guild:
            return
        await interaction.response.defer()
        guild_id = str(interaction.guild.id)
        medals = ["🥇", "🥈", "🥉"]

        if tab == "level":
            top_users = await self.db.get_top_users_by_level(guild_id, 15)
            desc = ""
            for i, entry in enumerate(top_users):
                member = interaction.guild.get_member(int(entry['user_id']))
                name = member.display_name if member else f"ID: {entry['user_id']}"
                place = medals[i] if i < 3 else f"`{i+1}.`"
                desc += f"{place} **{name}** — Ур. `{entry['level']}` (`{entry['exp']}` XP)\n"
            title = "🏆 Топ по уровню"
            color = discord.Color(0xf1c40f)

        elif tab == "messages":
            cursor = await self.db.conn.execute(
                'SELECT user_id, total_messages FROM users WHERE guild_id = ? AND total_messages > 0 ORDER BY total_messages DESC LIMIT 15',
                (guild_id,)
            )
            rows = await cursor.fetchall()
            desc = ""
            for i, row in enumerate(rows):
                member = interaction.guild.get_member(int(row['user_id']))
                name = member.display_name if member else f"ID: {row['user_id']}"
                place = medals[i] if i < 3 else f"`{i+1}.`"
                desc += f"{place} **{name}** — {row['total_messages']} сообщений\n"
            title = "🏆 Топ по сообщениям"
            color = discord.Color(0x3498db)

        elif tab == "voice":
            cursor = await self.db.conn.execute(
                'SELECT user_id, total_voice_minutes FROM users WHERE guild_id = ? AND total_voice_minutes > 0 ORDER BY total_voice_minutes DESC LIMIT 15',
                (guild_id,)
            )
            rows = await cursor.fetchall()
            desc = ""
            for i, row in enumerate(rows):
                member = interaction.guild.get_member(int(row['user_id']))
                name = member.display_name if member else f"ID: {row['user_id']}"
                place = medals[i] if i < 3 else f"`{i+1}.`"
                mins = row['total_voice_minutes']
                time_text = f"{mins // 60}ч {mins % 60}м" if mins >= 60 else f"{mins}м"
                desc += f"{place} **{name}** — {time_text}\n"
            title = "🏆 Топ по голосу"
            color = discord.Color(0x9b59b6)

        else:
            top_users = await self.db.get_top_users(guild_id, 15)
            desc = ""
            for i, entry in enumerate(top_users):
                member = interaction.guild.get_member(int(entry['user_id']))
                name = member.display_name if member else f"ID: {entry['user_id']}"
                place = medals[i] if i < 3 else f"`{i+1}.`"
                desc += f"{place} **{name}** — {entry['balance']} {AyanamiUI.E_RP}\n"
            title = "🏆 Топ по монеткам"
            color = Colors.MAIN

        if not desc:
            desc = "*Пусто*"

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="give", description="Выдать монетки")
    @app_commands.default_permissions(administrator=True)
    async def give_slash(self, interaction: discord.Interaction, amount: int, users: str):
        await interaction.response.defer()
        mentions = []
        for word in users.split():
            clean_id = re.sub(r'\D', '', word)
            if clean_id:
                m = interaction.guild.get_member(int(clean_id))
                if m and not m.bot:
                    await self.db.update_user_balance(str(interaction.guild.id), str(m.id), amount)
                    mentions.append(m.mention)
        if not mentions: return await interaction.followup.send("❌ Пользователи не найдены.", ephemeral=True)
        embed = discord.Embed(title="Выдача монеток", description=f"Выдано **{amount}** монеток: {', '.join(mentions[:10])}", color=Colors.MAIN)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="remove", description="Забрать монетки у пользователей")
    @app_commands.default_permissions(administrator=True)
    async def remove_slash(self, interaction: discord.Interaction, amount: int, users: str):
        await interaction.response.defer()
        mentions = []
        for word in users.split():
            clean_id = re.sub(r'\D', '', word)
            if clean_id:
                m = interaction.guild.get_member(int(clean_id))
                if m and not m.bot:
                    await self.db.update_user_balance(str(interaction.guild.id), str(m.id), -amount)
                    new_data = await self.db.get_or_create_user(str(interaction.guild.id), str(m.id))
                    if new_data.get('balance', 0) < 0:
                        await self.db.conn.execute('UPDATE users SET balance = 0 WHERE guild_id = ? AND user_id = ?', (str(interaction.guild.id), str(m.id)))
                        await self.db.conn.commit()
                    mentions.append(m.mention)
        if not mentions: return await interaction.followup.send("❌ Пользователи не найдены.", ephemeral=True)
        embed = discord.Embed(title="Изъятие монеток", description=f"Изъято **{amount}** монеток у: {', '.join(mentions[:15])}", color=Colors.MAIN)
        await interaction.followup.send(embed=embed)

    @commands.command(name="profile")
    async def profile_prefix(self, ctx, member: discord.Member = None):
        from prefix_adapter import InteractionAdapter
        await self.profile.callback(self, InteractionAdapter(ctx), member)

    @commands.command(name="top")
    async def top_prefix(self, ctx, tab: str = "coins"):
        from prefix_adapter import InteractionAdapter
        await self.top.callback(self, InteractionAdapter(ctx), tab)

    @commands.command(name="give")
    @commands.has_permissions(administrator=True)
    async def give_prefix(self, ctx, amount: int, *, users: str):
        from prefix_adapter import InteractionAdapter
        await self.give_slash.callback(self, InteractionAdapter(ctx), amount, users)

    @commands.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def remove_prefix(self, ctx, amount: int, *, users: str):
        from prefix_adapter import InteractionAdapter
        await self.remove_slash.callback(self, InteractionAdapter(ctx), amount, users)

async def setup(bot):
    await bot.add_cog(Economy(bot))
