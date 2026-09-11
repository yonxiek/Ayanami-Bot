import asyncio
from datetime import datetime

import discord
from discord.ext import commands

from db import Database
from voice_tracker import VoiceTrackerMixin


def current_week_key() -> str:
    iso = datetime.now().isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


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



async def setup(bot):
    await bot.add_cog(WeeklyStats(bot))