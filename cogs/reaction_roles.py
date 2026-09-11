import discord
from discord.ext import commands

from db import Database


class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member.bot:
            return
        config = await self.db.get_guild_config(str(payload.guild_id))
        reaction_roles = config.get("reaction_roles", {})
        key = f"{payload.channel_id}:{payload.message_id}"
        if key not in reaction_roles:
            return
        mapping = reaction_roles[key]
        emoji_str = str(payload.emoji)
        if emoji_str in mapping:
            role_id = int(mapping[emoji_str])
            role = payload.member.guild.get_role(role_id)
            if role:
                try:
                    await payload.member.add_roles(role, reason="Reaction role")
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        config = await self.db.get_guild_config(str(payload.guild_id))
        reaction_roles = config.get("reaction_roles", {})
        key = f"{payload.channel_id}:{payload.message_id}"
        if key not in reaction_roles:
            return
        mapping = reaction_roles[key]
        emoji_str = str(payload.emoji)
        if emoji_str in mapping:
            role_id = int(mapping[emoji_str])
            role = guild.get_role(role_id)
            if role:
                try:
                    await member.remove_roles(role, reason="Reaction role remove")
                except Exception:
                    pass


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
