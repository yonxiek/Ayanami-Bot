import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Literal
from datetime import datetime, timezone, timedelta
from db import Database
from ui_components import Icons, Colors, AyanamiUI



class Quests(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.voice_sessions = {}
        self.daily_reset.start()
        self.random_quest_rotation.start()

    def cog_unload(self):
        self.daily_reset.cancel()
        self.random_quest_rotation.cancel()

    @tasks.loop(hours=1)
    async def daily_reset(self):
        now = datetime.now(timezone.utc)
        if now.hour == 0:
            for guild in self.bot.guilds:
                quests = await self.db.get_guild_quests(str(guild.id))
                for quest in quests:
                    if quest['reset_hour'] == 0:
                        await self.db.reset_daily_quests(str(guild.id))
                        break
                config = await self.db.get_guild_config(str(guild.id))
                sys_ch_id = config.get("system_channel_id")
                sys_ch = guild.get_channel(int(sys_ch_id)) if sys_ch_id else None
                if sys_ch and quests:
                    try:
                        quest_names = "\n".join([f"> **{q['name']}** — {q['quest_type']}" for q in quests[:5]])
                        embed = discord.Embed(
                            title="🔄 Ежедневные квесты сброшены!",
                            description=f"Доступны:\n{quest_names}",
                            color=Colors.MAIN
                        )
                        embed.set_footer(text="Ayanami System")
                        await sys_ch.send(embed=embed)
                    except discord.Forbidden:
                        pass

        expired_roles = await self.db.remove_expired_roles()
        for entry in expired_roles:
            guild = self.bot.get_guild(int(entry['guild_id']))
            if guild:
                member = guild.get_member(int(entry['user_id']))
                role = guild.get_role(int(entry['role_id']))
                if member and role:
                    try:
                        await member.remove_roles(role, reason="Истёк срок временной роли")
                    except discord.Forbidden:
                        pass

        expired_boosts = await self.db.remove_expired_boosts()
        for entry in expired_boosts:
            guild = self.bot.get_guild(int(entry['guild_id']))
            if guild:
                member = guild.get_member(int(entry['user_id']))
                if member:
                    try:
                        await member.send(f"⏰ Ваш XP-буст ({entry['multiplier']}x) на сервере **{guild.name}** истёк.")
                    except discord.Forbidden:
                        pass

    @tasks.loop(minutes=15)
    async def random_quest_rotation(self):
        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            config = await self.db.get_random_quest_config(str(guild.id))
            if not config.get('last_rotation'):
                continue
            try:
                last = datetime.fromisoformat(config['last_rotation'])
                hours_since = (now - last).total_seconds() / 3600
                if hours_since >= config['interval_hours']:
                    rotated = await self.db.rotate_random_quests(str(guild.id))
                    if rotated:
                        channel = guild.system_channel or guild.text_channels[0] if guild.text_channels else None
                        if channel:
                            names = "\n".join([f"> **{n}**" for n in rotated])
                            embed = discord.Embed(
                                title="🔄 Рандомные квесты обновлены",
                                description=names,
                                color=Colors.MAIN
                            )
                            embed.set_footer(text="Ayanami System")
                            await channel.send(embed=embed)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        completed = await self.db.increment_quest_progress(str(message.guild.id), str(message.author.id), "messages")
        if completed:
            for q in completed:
                try:
                    await message.author.send(
                        f"🎁 Квест **{q['name']}** выполнен! Награда **{q['reward']}** {AyanamiUI.E_RP} автоматически начислена."
                    )
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        if member.bot or not member.guild:
            return
        guild_id = member.guild.id
        user_id = member.id
        if before.channel is None and after.channel is not None:
            self.voice_sessions.setdefault(guild_id, {})[user_id] = datetime.now(timezone.utc)
        elif before.channel is not None and after.channel is None:
            start_time = self.voice_sessions.get(guild_id, {}).pop(user_id, None)
            if start_time:
                minutes = int((datetime.now(timezone.utc) - start_time).total_seconds() / 60)
                if minutes > 0:
                    completed = await self.db.increment_quest_progress(str(guild_id), str(user_id), "voice_join", minutes)
                    if completed:
                        for q in completed:
                            try:
                                await member.send(
                                    f"🎁 Квест **{q['name']}** выполнен! Награда **{q['reward']}** {AyanamiUI.E_RP} автоматически начислена."
                                )
                            except discord.Forbidden:
                                pass

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if not interaction.guild:
            return
        completed = await self.db.increment_quest_progress(str(interaction.guild.id), str(interaction.user.id), "commands")
        if completed:
            for q in completed:
                try:
                    await interaction.user.send(
                        f"🎁 Квест **{q['name']}** выполнен! Награда **{q['reward']}** {AyanamiUI.E_RP} автоматически начислена."
                    )
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or not reaction.message.guild:
            return
        completed = await self.db.increment_quest_progress(str(reaction.message.guild.id), str(user.id), "reactions")
        if completed:
            for q in completed:
                try:
                    await user.send(
                        f"🎁 Квест **{q['name']}** выполнен! Награда **{q['reward']}** {AyanamiUI.E_RP} автоматически начислена."
                    )
                except discord.Forbidden:
                    pass

    @app_commands.command(name="quests", description="Посмотреть доступные ежедневные квесты")
    async def quests(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        quests = await self.db.get_guild_quests(guild_id)

        if not quests:
            embed = discord.Embed(
                title="Ежедневные квесты",
                description="На этом сервере пока нет квестов.\nАдминистраторы могут создать их через `/quest create`.",
                color=Colors.MAIN,
            )
            return await interaction.followup.send(embed=embed)

        description = ""
        for quest in quests:
            progress_data = await self.db.get_user_quest_progress(guild_id, user_id, quest['quest_id'])
            if progress_data:
                progress = progress_data['progress']
                completed = progress_data['completed']
                claimed = progress_data['claimed']
            else:
                progress = 0
                completed = False
                claimed = False

            bar_length = 20
            filled = int(bar_length * min(progress / quest['target'], 1))
            bar = "█" * filled + "░" * (bar_length - filled)

            if claimed:
                status = "✅ Забрано"
            elif completed:
                status = "🎁 Готово к забору"
            else:
                status = f"{bar} `{progress}/{quest['target']}`"

            description += (
                f"### {quest['name']}\n"
                f"> {quest['description']}\n"
                f"> **Награда:** {quest['reward']} {AyanamiUI.E_RP}\n"
                f"> **Прогресс:** {status}\n\n"
            )

        embed = discord.Embed(
            title="Ежедневные квесты",
            description=description,
            color=Colors.MAIN,
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="daily", description="Забрать ежедневную награду")
    async def daily(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        success, reward, streak = await self.db.claim_daily_reward(guild_id, user_id, 100)

        if not success:
            embed = discord.Embed(
                title="Ежедневная награда",
                description="Вы уже забрали награду сегодня!\nПопробуйте завтра.",
                color=Colors.ERROR,
            )
            return await interaction.followup.send(embed=embed)

        streak_bonus = ""
        if streak > 1:
            streak_bonus = f"\n🔥 Серия дней: **{streak}** (+{(streak-1)*25} бонус)"

        embed = discord.Embed(
            title="Ежедневная награда",
            description=f"Вы получили **{reward}** {AyanamiUI.E_RP}!{streak_bonus}\n\nТекущая серия: **{streak}** дней",
            color=Colors.SUCCESS,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)


    @commands.command(name="quests")
    async def quests_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.quests.callback(self, InteractionAdapter(ctx))

    @app_commands.command(name="questdesk", description="Обзор всех квестов сервера (доска квестов)")
    @app_commands.default_permissions(administrator=True)
    async def questdesk(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        quests = await self.db.get_guild_quests(guild_id)
        pool = await self.db.get_random_quest_pool(guild_id)
        if not quests:
            embed = discord.Embed(
                title="📋 Доска квестов",
                description="Квестов пока нет. Создайте их через `/setup` → Квесты.",
                color=Colors.MAIN,
            )
            return await interaction.followup.send(embed=embed)

        stats = await self.db.get_quest_progress_stats(guild_id)

        desc_lines = []
        for q in quests:
            status = "🟢" if q['enabled'] else "🔴"
            st = stats.get(q['quest_id'], {})
            total_users = st.get('total', 0)
            done_users = st.get('done', 0)
            type_icons = {
                "messages": "💬",
                "commands": "🤖",
                "reactions": "🎭",
                "voice_join": "🎧",
            }
            icon = type_icons.get(q['quest_type'], "❓")
            desc_lines.append(
                f"{status} {icon} **{q['name']}** — `{q['quest_id']}`\n"
                f"> Тип: `{q['quest_type']}` | Цель: `{q['target']}` | Награда: `{q['reward']}` {AyanamiUI.E_RP}\n"
                f"> Участники: **{total_users}** | Выполнили: **{done_users}**\n"
            )

        desc = "\n".join(desc_lines)
        if pool:
            pool_names = ", ".join(p['name'] for p in pool)
            desc += f"\n**🎲 Пул рандомных ({len(pool)}):** {pool_names}"

        embed = discord.Embed(title="📋 Доска квестов", description=desc, color=Colors.MAIN)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)

    @commands.command(name="questdesk")
    async def questdesk_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.questdesk.callback(self, InteractionAdapter(ctx))

    @commands.command(name="daily")
    async def daily_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.daily.callback(self, InteractionAdapter(ctx))

async def setup(bot):
    await bot.add_cog(Quests(bot))
