import discord
from discord.ext import commands
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from db import Database
from ui_components import Colors, Icons



class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.ban_tracker = defaultdict(lambda: defaultdict(list))
        self.kick_tracker = defaultdict(lambda: defaultdict(list))
        self.channel_delete_tracker = defaultdict(lambda: defaultdict(list))
        self.channel_create_tracker = defaultdict(lambda: defaultdict(list))
        self.role_delete_tracker = defaultdict(lambda: defaultdict(list))
        self.role_create_tracker = defaultdict(lambda: defaultdict(list))
        self.role_assign_tracker = defaultdict(lambda: defaultdict(list))
        self.webhook_tracker = defaultdict(lambda: defaultdict(list))
        self.punished_users = defaultdict(lambda: defaultdict(float))

    async def get_config(self, guild_id: int) -> dict:
        config = await self.db.get_guild_config(str(guild_id))
        sec = config.get("security", {})
        return {
            "enabled": sec.get("enabled", True),
            "warn_limit": sec.get("warn_limit", 3),
            "warn_expiry_hours": sec.get("warn_expiry_hours", 24),
            "punishment": sec.get("punishment", "ban"),
            "ban_limit": sec.get("ban_limit", 3),
            "ban_time": sec.get("ban_time", 60),
            "kick_limit": sec.get("kick_limit", 3),
            "kick_time": sec.get("kick_time", 60),
            "channel_delete_limit": sec.get("channel_delete_limit", 2),
            "channel_delete_time": sec.get("channel_delete_time", 60),
            "channel_create_limit": sec.get("channel_create_limit", 3),
            "channel_create_time": sec.get("channel_create_time", 60),
            "role_delete_limit": sec.get("role_delete_limit", 2),
            "role_delete_time": sec.get("role_delete_time", 60),
            "role_create_limit": sec.get("role_create_limit", 3),
            "role_create_time": sec.get("role_create_time", 60),
            "role_assign_limit": sec.get("role_assign_limit", 5),
            "role_assign_time": sec.get("role_assign_time", 30),
            "webhook_limit": sec.get("webhook_limit", 2),
            "webhook_time": sec.get("webhook_time", 60),
            "bot_admin_protection": sec.get("bot_admin_protection", True),
            "owner_immunity": sec.get("owner_immunity", True),
            "log_channel_id": config.get("log_channel_id", sec.get("log_channel_id", 0)),
        }

    async def issue_warning(self, guild: discord.Guild, user: discord.Member, reason: str, actor: discord.Member = None):
        cfg = await self.get_config(guild.id)
        await self.db.add_security_warning(str(guild.id), str(user.id), reason, expires_in_hours=cfg["warn_expiry_hours"])
        active_warns = await self.db.get_active_warnings(str(guild.id), str(user.id))
        await self._send_log(guild, self._build_warn_view(user, reason, active_warns, cfg["warn_limit"], actor))
        if active_warns >= cfg["warn_limit"]:
            await self._punish_user(guild, user, cfg["punishment"], f"Достигнут лимит предупреждений ({active_warns}/{cfg['warn_limit']})")
            await self.db.clear_user_warnings(str(guild.id), str(user.id))

    def _build_warn_view(self, user: discord.Member, reason: str, current: int, limit: int, actor: discord.Member = None) -> discord.ui.LayoutView:
        title = "⚠️ Предупреждение (Anti-Nuke)"
        color = discord.Color.gold()
        if current >= limit:
            title = "🚨 Лимит варнов достигнут — наказание применено"
            color = discord.Color.red()
        fields = [("Участник", f"{user.mention} (`{user.id}`)")]
        if actor:
            fields.append(("Обнаружено автоматически", "Системой защиты"))
        embed = discord.Embed(
            title=title,
            description=f"**Причина:** {reason}\n**Варны:** `{current}/{limit}`",
            color=color,
        )
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        return embed

    async def _punish_user(self, guild: discord.Guild, user: discord.Member, punishment: str, reason: str):
        if self._is_already_punished(guild.id, user.id):
            return
        self._mark_punished(guild.id, user.id)
        punishment_names = {"ban": "🔨 Забанен", "kick": "👢 Изгнан", "strip": "🛡️ Роли сняты"}
        punishment_text = punishment_names.get(punishment, punishment)
        try:
            if punishment == "ban":
                await guild.ban(user, reason=f"Anti-Nuke: {reason}")
            elif punishment == "kick":
                await guild.kick(user, reason=f"Anti-Nuke: {reason}")
            elif punishment == "strip":
                roles = [r for r in user.roles if not r.is_default() and not r.managed and r < guild.me.top_role]
                if roles:
                    await user.remove_roles(*roles, reason=f"Anti-Nuke: {reason}")
            embed = discord.Embed(
                title="🚨 Anti-Nuke — Наказание",
                description=f"**Причина:** {reason}\n**Мера:** {punishment_text}",
                color=discord.Color.red(),
            )
            for name, value in [("Участник", f"{user.mention} (`{user.id}`)")]:
                embed.add_field(name=name, value=value, inline=False)
            await self._send_log(guild, view)
        except discord.Forbidden:
            pass
        except Exception:
            pass

    def _is_already_punished(self, guild_id: int, user_id: int) -> bool:
        last = self.punished_users[guild_id].get(user_id, 0)
        return datetime.now(timezone.utc).timestamp() - last < 10

    def _mark_punished(self, guild_id: int, user_id: int):
        self.punished_users[guild_id][user_id] = datetime.now(timezone.utc).timestamp()

    async def _send_log(self, guild: discord.Guild, view: discord.ui.LayoutView):
        cfg = await self.get_config(guild.id)
        log_id = cfg.get("log_channel_id")
        if not log_id:
            return
        channel = guild.get_channel(int(log_id))
        if not channel:
            return
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    async def _check_and_warn(self, guild: discord.Guild, tracker: dict, limit: int, time_window: int, reason: str, audit_action: discord.AuditLogAction):
        await asyncio.sleep(1)
        now = datetime.now(timezone.utc)
        try:
            async for entry in guild.audit_logs(limit=1, action=audit_action):
                actor = entry.user
                if not isinstance(actor, discord.Member):
                    return
                if actor.id == self.bot.user.id:
                    return
                if actor.bot:
                    return
                cfg = await self.get_config(guild.id)
                if cfg["owner_immunity"] and actor.id == guild.owner_id:
                    return
                if self._is_already_punished(guild.id, actor.id):
                    return
                if isinstance(entry.target, discord.Member):
                    if entry.target.top_role >= guild.me.top_role:
                        return
                events = tracker[guild.id][actor.id]
                events = [t for t in events if now - t < timedelta(seconds=time_window)]
                events.append(now)
                tracker[guild.id][actor.id] = events
                if len(events) >= limit:
                    tracker[guild.id][actor.id].clear()
                    await self.issue_warning(guild, actor, reason)
                return
        except (discord.NotFound, discord.HTTPException, Exception):
            return

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        cfg = await self.get_config(guild.id)
        if not cfg["enabled"]:
            return
        await self._check_and_warn(guild, self.ban_tracker, cfg["ban_limit"], cfg["ban_time"], "Массовый бан участников", discord.AuditLogAction.ban)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not member.guild:
            return
        cfg = await self.get_config(member.guild.id)
        if not cfg["enabled"]:
            return
        await asyncio.sleep(1)
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id:
                    actor = entry.user
                    if isinstance(actor, discord.Member) and actor.id != self.bot.user.id and not actor.bot:
                        if cfg["owner_immunity"] and actor.id == member.guild.owner_id:
                            return
                        now = datetime.now(timezone.utc)
                        events = self.kick_tracker[member.guild.id][actor.id]
                        events = [t for t in events if now - t < timedelta(seconds=cfg["kick_time"])]
                        events.append(now)
                        self.kick_tracker[member.guild.id][actor.id] = events
                        if len(events) >= cfg["kick_limit"]:
                            self.kick_tracker[member.guild.id][actor.id].clear()
                            await self.issue_warning(member.guild, actor, "Массовый кик участников")
                    break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not channel.guild:
            return
        cfg = await self.get_config(channel.guild.id)
        if not cfg["enabled"]:
            return
        await self._check_and_warn(channel.guild, self.channel_delete_tracker, cfg["channel_delete_limit"], cfg["channel_delete_time"], "Массовое удаление каналов", discord.AuditLogAction.channel_delete)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not channel.guild:
            return
        cfg = await self.get_config(channel.guild.id)
        if not cfg["enabled"]:
            return
        await self._check_and_warn(channel.guild, self.channel_create_tracker, cfg["channel_create_limit"], cfg["channel_create_time"], "Массовое создание каналов", discord.AuditLogAction.channel_create)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        if not role.guild:
            return
        cfg = await self.get_config(role.guild.id)
        if not cfg["enabled"]:
            return
        await self._check_and_warn(role.guild, self.role_delete_tracker, cfg["role_delete_limit"], cfg["role_delete_time"], "Массовое удаление ролей", discord.AuditLogAction.role_delete)
        if role < role.guild.me.top_role:
            await asyncio.sleep(1)
            try:
                async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
                    actor = entry.user
                    if isinstance(actor, discord.Member) and actor.id != self.bot.user.id and not actor.bot:
                        await self.issue_warning(role.guild, actor, "Удаление роли бота")
                    break
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        if not role.guild:
            return
        cfg = await self.get_config(role.guild.id)
        if not cfg["enabled"]:
            return
        await self._check_and_warn(role.guild, self.role_create_tracker, cfg["role_create_limit"], cfg["role_create_time"], "Массовое создание ролей", discord.AuditLogAction.role_create)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if not after.guild:
            return
        cfg = await self.get_config(after.guild.id)
        if not cfg["enabled"]:
            return
        added_roles = [r for r in after.roles if r not in before.roles]
        if not added_roles:
            return
        if cfg["bot_admin_protection"]:
            for role in added_roles:
                if role.permissions.administrator and after.bot:
                    await asyncio.sleep(1)
                    try:
                        async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                            actor = entry.user
                            if isinstance(actor, discord.Member) and actor.id != self.bot.user.id:
                                await self.issue_warning(after.guild, actor, f"Выдача админ-роли боту ({after.mention})")
                                try:
                                    await after.remove_roles(role, reason="Anti-Nuke: admin role on bot")
                                except Exception:
                                    pass
                            break
                    except Exception:
                        pass
                    break
        now = datetime.now(timezone.utc)
        await asyncio.sleep(1)
        try:
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                actor = entry.user
                if isinstance(actor, discord.Member) and actor.id != self.bot.user.id and not actor.bot:
                    if cfg["owner_immunity"] and actor.id == after.guild.owner_id:
                        return
                    events = self.role_assign_tracker[after.guild.id][actor.id]
                    events = [t for t in events if now - t < timedelta(seconds=cfg["role_assign_time"])]
                    events.append(now)
                    self.role_assign_tracker[after.guild.id][actor.id] = events
                    if len(events) >= cfg["role_assign_limit"]:
                        self.role_assign_tracker[after.guild.id][actor.id].clear()
                        await self.issue_warning(after.guild, actor, "Массовая выдача ролей")
                break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_webhook_update(self, channel):
        if not channel.guild:
            return
        cfg = await self.get_config(channel.guild.id)
        if not cfg["enabled"]:
            return
        await asyncio.sleep(1)
        now = datetime.now(timezone.utc)
        try:
            async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
                actor = entry.user
                if isinstance(actor, discord.Member) and actor.id != self.bot.user.id and not actor.bot:
                    if cfg["owner_immunity"] and actor.id == channel.guild.owner_id:
                        return
                    events = self.webhook_tracker[channel.guild.id][actor.id]
                    events = [t for t in events if now - t < timedelta(seconds=cfg["webhook_time"])]
                    events.append(now)
                    self.webhook_tracker[channel.guild.id][actor.id] = events
                    if len(events) >= cfg["webhook_limit"]:
                        self.webhook_tracker[channel.guild.id][actor.id].clear()
                        await self.issue_warning(channel.guild, actor, "Массовое создание вебхуков")
                break
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Security(bot))
