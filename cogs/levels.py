import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import Database
from ui_components import Colors


class Levels(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.xp_cooldowns = {}

    async def cog_load(self):
        try:
            self.bg_task = self.bot.loop.create_task(self._voice_roles_loop())
        except (RuntimeError, AttributeError):
            pass

    async def cog_unload(self):
        if hasattr(self, "bg_task"):
            self.bg_task.cancel()

    def get_config(self, guild_id: str, config: dict) -> dict:
        return {
            'xp_per_message': config.get('xp_per_message', 15),
            'xp_voice_per_minute': config.get('xp_voice_per_minute', 10),
            'xp_cooldown_seconds': config.get('xp_cooldown_seconds', 60),
            'booster_xp_boost': config.get('booster_xp_boost', 0.65),
            'level_up_channel_id': config.get('level_up_channel_id'),
            'level_up_message': config.get('level_up_message', '🎉 {user} повысил уровень до **{level}**!'),
            'level_up_enabled': config.get('level_up_enabled', True),
            'xp_enabled': config.get('xp_enabled', True),
            'role_rewards_enabled': config.get('role_rewards_enabled', True),
            'voice_roles': config.get('voice_roles', []),
        }

    async def _voice_roles_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._check_voice_roles()
            except Exception as e:
                print(f"Ошибка ролей за голосовую активность: {e}")
            await asyncio.sleep(120)

    async def _check_voice_roles(self):
        """Выдаёт роли тем, кто набрал нужно число минут в голосовом канале."""
        for guild in self.bot.guilds:
            config = await self.db.get_guild_config(str(guild.id))
            voice_roles = config.get('voice_roles', [])
            if not voice_roles:
                continue
            for entry in sorted(voice_roles, key=lambda x: int(x.get('minutes', 0))):
                minutes = int(entry.get('minutes', 0))
                role_id = str(entry.get('role_id', ''))
                role = guild.get_role(int(role_id)) if role_id.lstrip('-').isdigit() else None
                if not role:
                    continue
                rows = await self.db.get_users_by_voice_minutes(str(guild.id), minutes)
                for row in rows:
                    member = guild.get_member(int(row['user_id']))
                    if not member or member.bot or role in member.roles:
                        continue
                    try:
                        await member.add_roles(role, reason=f"Активность: {minutes}+ минут в голосе")
                    except discord.Forbidden:
                        pass

    def calc_level(self, xp: int) -> int:
        return int((xp / 100) ** 0.5) + 1

    def calc_progress(self, xp: int, level: int) -> float:
        current_level_xp = (level - 1) ** 2 * 100
        next_level_xp = level ** 2 * 100
        if next_level_xp == current_level_xp:
            return 1.0
        return (xp - current_level_xp) / (next_level_xp - current_level_xp)

    def build_xp_bar(self, progress: float, length: int = 10) -> str:
        filled = int(progress * length)
        empty = length - filled
        return '█' * filled + '░' * empty

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await self.db.get_guild_config(str(message.guild.id))
        cfg = self.get_config(str(message.guild.id), config)

        if not cfg['xp_enabled']:
            return

        user_id = str(message.author.id)
        guild_id = str(message.guild.id)

        now = datetime.now(timezone.utc)
        last_xp = self.xp_cooldowns.get(f"{guild_id}:{user_id}")
        if last_xp and (now - last_xp).total_seconds() < cfg['xp_cooldown_seconds']:
            return

        base_xp = cfg['xp_per_message']
        xp = base_xp

        if message.author.premium_since:
            xp = int(xp * (1 + cfg['booster_xp_boost']))

        boost = await self.db.get_xp_boost(guild_id, user_id)
        if boost:
            xp = int(xp * boost['multiplier'])

        guild_boost = config.get('guild_xp_boost')
        if guild_boost:
            try:
                expires = datetime.fromisoformat(guild_boost['expires_at'])
                if expires > now:
                    xp = int(xp * float(guild_boost.get('multiplier', 1.5)))
            except Exception:
                pass

        result = await self.db.add_xp(guild_id, user_id, xp)
        self.xp_cooldowns[f"{guild_id}:{user_id}"] = now

        if result['leveled_up']:
            await self.handle_level_up(message.guild, message.author, result['new_level'], cfg)
            try:
                from cogs.achievements import award_achievement
                new_level = result['new_level']
                awards = {"level_5": 5, "level_10": 10, "level_20": 20}
                for aid, req in awards.items():
                    if new_level >= req:
                        await award_achievement(self.db, guild_id, user_id, aid, message.author)
            except Exception:
                pass

    async def handle_level_up(self, guild: discord.Guild, member: discord.Member, new_level: int, cfg: dict):
        if not cfg['level_up_enabled']:
            return

        channel = guild.get_channel(int(cfg['level_up_channel_id'])) if cfg['level_up_channel_id'] else guild.system_channel
        if not channel:
            return

        msg = cfg['level_up_message'].format(
            user=member.mention,
            level=new_level,
            server=guild.name,
            username=member.display_name,
        )

        embed = discord.Embed(
            title=f"⬆️ Уровень {new_level}",
            description=msg,
            color=Colors.LEVEL_UP if hasattr(Colors, 'LEVEL_UP') else discord.Color(0xf1c40f),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Ayanami System")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

        if cfg['role_rewards_enabled']:
            level_roles = await self.db.get_level_roles(str(guild.id))
            for lr in level_roles:
                if lr['level'] == new_level:
                    role = guild.get_role(int(lr['role_id']))
                    if role:
                        try:
                            await member.add_roles(role, reason=f"Level {new_level} reward")
                        except discord.Forbidden:
                            pass


async def setup(bot):
    await bot.add_cog(Levels(bot))
