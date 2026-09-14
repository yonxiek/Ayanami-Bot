import discord
from discord.ext import commands

from db import Database


class Invites(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self._invites: dict[int, dict[str, int]] = {}

    async def cog_load(self):
        self._invites = await self._fetch_all()

    @commands.Cog.listener()
    async def on_ready(self):
        self._invites = await self._fetch_all()

    async def _fetch_all(self) -> dict[int, dict[str, int]]:
        cache = {}
        for guild in self.bot.guilds:
            cache[guild.id] = await self._fetch_guild(guild)
        return cache

    async def _fetch_guild(self, guild: discord.Guild) -> dict[str, int]:
        try:
            invites = await guild.invites()
            return {inv.code: inv.uses for inv in invites}
        except Exception:
            return {}

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None:
            return
        self._invites.setdefault(invite.guild.id, {})[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild is None:
            return
        self._invites.setdefault(invite.guild.id, {}).pop(invite.code, None)
        self._invites[invite.guild.id] = await self._fetch_guild(invite.guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        inviter_code = None
        current: dict[str, int] = {}
        try:
            current = await self._fetch_guild(guild)
            prev = self._invites.get(guild.id, {})
            for code, uses in current.items():
                if uses == (prev.get(code, 0) or 0) + 1:
                    inviter_code = code
                    break
        except Exception:
            pass
        finally:
            self._invites[guild.id] = current or self._invites.get(guild.id, {})

        if not inviter_code:
            try:
                await self._fetch_guild(guild)
            except Exception:
                pass
            return

        inviter_id = None
        try:
            for inv in await guild.invites():
                if inv.code == inviter_code and inv.inviter and not inv.inviter.bot:
                    inviter_id = str(inv.inviter.id)
                    break
        except Exception:
            pass

        if inviter_id and inviter_id != str(member.id):
            await self.db.record_invite(str(guild.id), inviter_id, str(member.id), inviter_code)


async def setup(bot):
    await bot.add_cog(Invites(bot))