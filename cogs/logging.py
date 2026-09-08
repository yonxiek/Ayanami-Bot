import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from db import Database
from ui_components import Icons


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.voice_sessions = {}  # {guild_id: {user_id: datetime}}
        self._log_cache = {}  # {(guild_id, event_key, user_id): datetime} — дедупликация
        self._cache_ttl = timedelta(seconds=5)  # окно дедупликации

    async def is_event_enabled(self, guild_id: int, event: str) -> bool:
        config = await self.db.get_guild_config(str(guild_id))
        log_events = config.get("log_events", {})
        if not log_events:
            return True
        return log_events.get(event, True)

    async def get_log_channel(self, guild_id: int):
        config = await self.db.get_guild_config(str(guild_id))
        ch_id = config.get("log_channel_id")
        if not ch_id:
            return None
        return self.bot.get_channel(int(ch_id))

    def _is_duplicate(self, guild_id: int, event_key: str, user_id: int = 0) -> bool:
        """Проверяет, не логировали ли мы это событие недавно. Возвращает True если дубликат."""
        now = datetime.now(timezone.utc)
        key = (guild_id, event_key, user_id)
        last = self._log_cache.get(key)
        if last and (now - last) < self._cache_ttl:
            return True
        self._log_cache[key] = now
        # Чистим старые записи раз в 100 вызовов
        if len(self._log_cache) > 200:
            self._log_cache = {k: v for k, v in self._log_cache.items() if (now - v) < self._cache_ttl}
        return False

    async def send_log(self, guild_id: int, embed: discord.Embed, mod_only: bool = False):
        config = await self.db.get_guild_config(str(guild_id))
        if mod_only:
            ch_id = config.get("mod_log_channel_id")
        else:
            ch_id = config.get("log_channel_id")
        if not ch_id:
            if not mod_only:
                return
            ch_id = config.get("log_channel_id")
        if not ch_id:
            return
        channel = self.bot.get_channel(int(ch_id))
        if not channel:
            return
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    async def get_audit_actor(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int = None, delay: float = 1.0) -> discord.Member | None:
        import asyncio
        await asyncio.sleep(delay)
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if target_id and entry.target and getattr(entry.target, 'id', None) != target_id:
                    continue
                if entry.user and isinstance(entry.user, discord.Member) and entry.user.id != self.bot.user.id:
                    return entry.user
        except (discord.NotFound, discord.HTTPException, Exception):
            pass
        return None

    def _actor_footer(self, text: str, actor):
        if actor:
            return f"{text}: {actor.display_name} ({actor.id})"
        return "Ayanami System"

    # ==========================================
    #               MESSAGES
    # ==========================================

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        if not await self.is_event_enabled(message.guild.id, "msg_delete"):
            return
        actor = await self.get_audit_actor(message.guild, discord.AuditLogAction.message_delete, message.author.id)

        embed = discord.Embed(title="Message Deleted", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="Author", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if actor and actor.id != message.author.id:
            embed.add_field(name="Deleted By", value=f"{actor.mention}", inline=True)
        if message.content:
            embed.add_field(name="Content", value=f"```\n{message.content[:1000]}\n```", inline=False)
        if message.attachments:
            files = "\n".join([a.filename for a in message.attachments[:5]])
            embed.add_field(name="Attachments", value=files, inline=False)
        embed.set_footer(text="Ayanami System")
        await self.send_log(message.guild.id, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.content == after.content or not before.guild or before.author.bot:
            return
        if not await self.is_event_enabled(before.guild.id, "msg_edit"):
            return

        embed = discord.Embed(title="Message Edited", color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        if before.content:
            embed.add_field(name="Before", value=f"```\n{before.content[:1000]}\n```", inline=False)
        if after.content:
            embed.add_field(name="After", value=f"```\n{after.content[:1000]}\n```", inline=False)
        embed.set_footer(text="Ayanami System")
        await self.send_log(before.guild.id, embed)

    # ==========================================
    #               MEMBERS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not await self.is_event_enabled(member.guild.id, "member_join"):
            return

        embed = discord.Embed(title="Member Joined", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"{member.mention} ({member.name}, ID: {member.id})", inline=False)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        if member.joined_at:
            embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
        if member.premium_since:
            embed.add_field(name="Boost", value=f"Active since <t:{int(member.premium_since.timestamp())}:R>", inline=True)
        embed.set_footer(text="Ayanami System")
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not await self.is_event_enabled(member.guild.id, "member_leave"):
            return

        embed = discord.Embed(title="Member Left", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"{member.name} (`{member.id}`)", inline=True)
        roles = [r.mention for r in member.roles if not r.is_default()]
        if roles:
            embed.add_field(name="Roles", value=", ".join(roles[:15]), inline=False)
        if member.joined_at:
            embed.add_field(name="Was On Server", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
        if member.premium_since:
            embed.add_field(name="Boost", value=f"Until <t:{int(member.premium_since.timestamp())}:R>", inline=True)
        embed.set_footer(text="Ayanami System")
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        guild_id = before.guild.id

        # === Roles (add/remove) ===
        if await self.is_event_enabled(guild_id, "role_add") or await self.is_event_enabled(guild_id, "role_remove"):
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            if added and await self.is_event_enabled(guild_id, "role_add"):
                if not self._is_duplicate(guild_id, "role_add", after.id):
                    actor = await self.get_audit_actor(after.guild, discord.AuditLogAction.member_role_update, after.id)
                    embed = discord.Embed(title="Role Added", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
                    embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                    embed.add_field(name="Member", value=f"{after.mention} ({after.name}, ID: {after.id})", inline=False)
                    embed.add_field(name="Roles", value=", ".join([r.mention for r in added]), inline=False)
                    embed.set_footer(text=self._actor_footer("By", actor))
                    await self.send_log(guild_id, embed)
            if removed and await self.is_event_enabled(guild_id, "role_remove"):
                if not self._is_duplicate(guild_id, "role_remove", after.id):
                    actor = await self.get_audit_actor(after.guild, discord.AuditLogAction.member_role_update, after.id)
                    embed = discord.Embed(title="Role Removed", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
                    embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                    embed.add_field(name="Member", value=f"{after.mention} ({after.name}, ID: {after.id})", inline=False)
                    embed.add_field(name="Roles", value=", ".join([r.mention for r in removed]), inline=False)
                    embed.set_footer(text=self._actor_footer("By", actor))
                    await self.send_log(guild_id, embed)

        # === Boost ===
        if await self.is_event_enabled(guild_id, "boost"):
            was_boosting = before.premium_since is not None
            is_boosting = after.premium_since is not None
            if was_boosting != is_boosting:
                if not self._is_duplicate(guild_id, "boost", after.id):
                    if is_boosting:
                        embed = discord.Embed(title="Boost Added", color=discord.Color.gold(), timestamp=datetime.now(timezone.utc))
                        embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                        embed.add_field(name="Member", value=f"{after.mention} ({after.name}, ID: {after.id})", inline=False)
                        embed.add_field(name="Started", value=f"<t:{int(after.premium_since.timestamp())}:R>", inline=True)
                    else:
                        embed = discord.Embed(title="Boost Removed", color=discord.Color.greyple(), timestamp=datetime.now(timezone.utc))
                        embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                        embed.add_field(name="Member", value=f"{after.mention} ({after.name}, ID: {after.id})", inline=False)
                    embed.set_footer(text="Ayanami System")
                    await self.send_log(guild_id, embed)

        # === Nickname ===
        if before.nick != after.nick:
            if not await self.is_event_enabled(guild_id, "nickname"):
                return
            if not self._is_duplicate(guild_id, "nickname", after.id):
                actor = await self.get_audit_actor(after.guild, discord.AuditLogAction.member_update, after.id)
                embed = discord.Embed(title="Nickname Changed", color=discord.Color.purple(), timestamp=datetime.now(timezone.utc))
                embed.set_author(name=after.name, icon_url=after.display_avatar.url)
                embed.add_field(name="Member", value=f"{after.mention} ({after.name}, ID: {after.id})", inline=False)
                embed.add_field(name="Old Nickname", value=before.nick or before.name, inline=True)
                embed.add_field(name="New Nickname", value=after.nick or after.name, inline=True)
                if actor and actor.id != after.id:
                    embed.set_footer(text=f"By: {actor.display_name} ({actor.id})")
                else:
                    embed.set_footer(text="Ayanami System")
                await self.send_log(guild_id, embed)

        # === Discord-native timeout ===
        if await self.is_event_enabled(guild_id, "voice_state"):
            try:
                before_timeout = before.timed_out
                after_timeout = after.timed_out
                if before_timeout != after_timeout:
                    if not self._is_duplicate(guild_id, "timeout", after.id):
                        if after_timeout:
                            embed = discord.Embed(title="Timeout (Discord)", color=discord.Color.greyple(), timestamp=datetime.now(timezone.utc))
                            embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                            embed.add_field(name="Member", value=f"{after.mention} ({after.name}, ID: {after.id})", inline=False)
                            embed.set_footer(text="Ayanami System")
                            await self.send_log(guild_id, embed)
                        else:
                            embed = discord.Embed(title="Timeout Removed (Discord)", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
                            embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                            embed.add_field(name="Member", value=f"{after.mention} ({after.name}, ID: {after.id})", inline=False)
                            embed.set_footer(text="Ayanami System")
                            await self.send_log(guild_id, embed)
            except AttributeError:
                pass

    # ==========================================
    #               ROLES (create/delete/update)
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        if not role.guild:
            return
        if not await self.is_event_enabled(role.guild.id, "role_create"):
            return
        actor = await self.get_audit_actor(role.guild, discord.AuditLogAction.role_create, role.id)

        embed = discord.Embed(title="Role Created", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=role.name, icon_url=role.icon.url if role.icon else discord.Embed.Empty)
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="ID", value=f"`{role.id}`", inline=True)
        embed.add_field(name="Color", value=str(role.color) if role.color != discord.Color.default() else "Not set", inline=True)
        embed.set_footer(text=self._actor_footer("Created By", actor))
        await self.send_log(role.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        if not role.guild:
            return
        if not await self.is_event_enabled(role.guild.id, "role_delete"):
            return
        actor = await self.get_audit_actor(role.guild, discord.AuditLogAction.role_delete, role.id)

        embed = discord.Embed(title="Role Deleted", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=role.name)
        embed.add_field(name="Role", value=f"`{role.name}` (`{role.id}`)", inline=True)
        embed.add_field(name="Color", value=str(role.color) if role.color != discord.Color.default() else "Not set", inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.set_footer(text=self._actor_footer("Deleted By", actor))
        await self.send_log(role.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if not after.guild:
            return
        if not await self.is_event_enabled(after.guild.id, "role_update"):
            return
        changes = []
        if before.name != after.name:
            changes.append(f"**Name**: `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color**: `{before.color}` → `{after.color}`")
        if before.permissions != after.permissions:
            old_p = set(before.permissions)
            new_p = set(after.permissions)
            added_perms = new_p - old_p
            removed_perms = old_p - new_p
            if added_perms:
                changes.append(f"**Permissions Added**: {', '.join([p[0] for p in added_perms])}")
            if removed_perms:
                changes.append(f"**Permissions Removed**: {', '.join([p[0] for p in removed_perms])}")
        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionable**: {'Yes' if after.mentionable else 'No'}")
        if before.hoist != after.hoist:
            changes.append(f"**Hoisted**: {'Yes' if after.hoist else 'No'}")
        if getattr(before, 'icon', None) != getattr(after, 'icon', None):
            old_icon = "Yes" if getattr(before, 'icon', None) else "No"
            new_icon = "Yes" if getattr(after, 'icon', None) else "No"
            changes.append(f"**Icon**: {old_icon} → {new_icon}")
        if not changes:
            return
        actor = await self.get_audit_actor(after.guild, discord.AuditLogAction.role_update, after.id)

        embed = discord.Embed(title="Role Updated", color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=after.name, icon_url=after.icon.url if after.icon else discord.Embed.Empty)
        embed.add_field(name="Role", value=after.mention, inline=True)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        embed.set_footer(text=self._actor_footer("Changed By", actor))
        await self.send_log(after.guild.id, embed)

    # ==========================================
    #               EMOJIS / STICKERS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        if not await self.is_event_enabled(guild.id, "emoji_sticker"):
            return
        added = [e for e in after if e not in before]
        removed = [e for e in before if e not in after]
        edited = []
        before_map = {e.id: e for e in before}
        for e in after:
            if e.id in before_map:
                old = before_map[e.id]
                if old.name != e.name or old.animated != e.animated:
                    edited.append((old, e))

        for emoji in added:
            actor = await self.get_audit_actor(guild, discord.AuditLogAction.emoji_create, emoji.id)
            embed = discord.Embed(title="Emoji Added", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=f":{emoji.name}:", icon_url=emoji.url if emoji.url else discord.Embed.Empty)
            embed.add_field(name="Animated", value="Yes" if emoji.animated else "No", inline=True)
            embed.set_footer(text=self._actor_footer("Added By", actor))
            await self.send_log(guild.id, embed)

        for emoji in removed:
            actor = await self.get_audit_actor(guild, discord.AuditLogAction.emoji_delete, emoji.id)
            embed = discord.Embed(title="Emoji Deleted", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=f":{emoji.name}:")
            embed.set_footer(text=self._actor_footer("Deleted By", actor))
            await self.send_log(guild.id, embed)

        for old_e, new_e in edited:
            actor = await self.get_audit_actor(guild, discord.AuditLogAction.emoji_update, new_e.id)
            embed = discord.Embed(title="Emoji Updated", color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=f":{new_e.name}:", icon_url=new_e.url if new_e.url else discord.Embed.Empty)
            embed.add_field(name="Old Name", value=f"`:{old_e.name}:`", inline=True)
            embed.add_field(name="New Name", value=f"`:{new_e.name}:`", inline=True)
            embed.set_footer(text=self._actor_footer("Changed By", actor))
            await self.send_log(guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild, before, after):
        if not await self.is_event_enabled(guild.id, "emoji_sticker"):
            return
        added = [s for s in after if s not in before]
        removed = [s for s in before if s not in after]
        edited = []
        before_map = {s.id: s for s in before}
        for s in after:
            if s.id in before_map:
                old = before_map[s.id]
                if old.name != s.name:
                    edited.append((old, s))

        for sticker in added:
            actor = await self.get_audit_actor(guild, discord.AuditLogAction.sticker_create, sticker.id)
            embed = discord.Embed(title="Sticker Added", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=sticker.name)
            if sticker.description:
                embed.add_field(name="Description", value=sticker.description[:100], inline=False)
            embed.set_footer(text=self._actor_footer("Added By", actor))
            await self.send_log(guild.id, embed)

        for sticker in removed:
            actor = await self.get_audit_actor(guild, discord.AuditLogAction.sticker_delete, sticker.id)
            embed = discord.Embed(title="Sticker Deleted", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=sticker.name)
            embed.set_footer(text=self._actor_footer("Deleted By", actor))
            await self.send_log(guild.id, embed)

        for old_s, new_s in edited:
            actor = await self.get_audit_actor(guild, discord.AuditLogAction.sticker_update, new_s.id)
            embed = discord.Embed(title="Sticker Updated", color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=new_s.name)
            embed.add_field(name="Old Name", value=f"`{old_s.name}`", inline=True)
            embed.add_field(name="New Name", value=f"`{new_s.name}`", inline=True)
            embed.set_footer(text=self._actor_footer("Changed By", actor))
            await self.send_log(guild.id, embed)

    # ==========================================
    #               SOUNDBOARD
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_soundboard_sound_create(self, sound):
        if not await self.is_event_enabled(sound.guild.id, "soundboard"):
            return
        embed = discord.Embed(title="Soundboard — Sound Added", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=sound.name)
        embed.add_field(name="Emoji", value=str(sound.emoji_name) if sound.emoji_name else "—", inline=True)
        if hasattr(sound, 'user') and sound.user:
            embed.add_field(name="Created By", value=f"{sound.user.mention}", inline=True)
        embed.set_footer(text="Ayanami System")
        await self.send_log(sound.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_soundboard_sound_delete(self, sound):
        if not await self.is_event_enabled(sound.guild.id, "soundboard"):
            return
        embed = discord.Embed(title="Soundboard — Sound Deleted", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=sound.name)
        embed.set_footer(text="Ayanami System")
        await self.send_log(sound.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_soundboard_sound_update(self, before, after):
        if not await self.is_event_enabled(before.guild.id, "soundboard"):
            return
        changes = []
        if before.name != after.name:
            changes.append(f"**Name**: `{before.name}` → `{after.name}`")
        if before.volume != after.volume:
            changes.append(f"**Volume**: `{before.volume}` → `{after.volume}`")
        if before.emoji_name != after.emoji_name:
            changes.append(f"**Emoji**: `{before.emoji_name}` → `{after.emoji_name}`")
        if not changes:
            return
        embed = discord.Embed(title="Soundboard — Sound Updated", color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=after.name)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        embed.set_footer(text="Ayanami System")
        await self.send_log(before.guild.id, embed)

    # ==========================================
    #               VOICE
    # ==========================================

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild:
            return

        guild_id = member.guild.id
        user_id = member.id

        if not before.channel and after.channel:
            self.voice_sessions.setdefault(guild_id, {})[user_id] = datetime.now(timezone.utc)
            if not await self.is_event_enabled(guild_id, "voice_connect"):
                return
            embed = discord.Embed(title="Voice Connected", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Channel", value=after.channel.mention, inline=True)
            embed.set_footer(text="Ayanami System")
            await self.send_log(guild_id, embed)

        elif before.channel and not after.channel:
            duration_text = ""
            sessions = self.voice_sessions.get(guild_id, {})
            start_time = sessions.pop(user_id, None)
            if start_time:
                delta = datetime.now(timezone.utc) - start_time
                total_seconds = int(delta.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                parts = []
                if hours:
                    parts.append(f"{hours}h")
                if minutes:
                    parts.append(f"{minutes}m")
                parts.append(f"{seconds}s")
                duration_text = " ".join(parts)

            if not await self.is_event_enabled(guild_id, "voice_disconnect"):
                return
            embed = discord.Embed(title="Voice Disconnected", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Channel", value=before.channel.mention, inline=True)
            if duration_text:
                embed.add_field(name="Duration", value=duration_text, inline=True)
            embed.set_footer(text="Ayanami System")
            await self.send_log(guild_id, embed)

        elif before.channel and after.channel and before.channel != after.channel:
            if not await self.is_event_enabled(guild_id, "voice_move"):
                return
            embed = discord.Embed(title="Voice Moved", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="From", value=before.channel.mention, inline=True)
            embed.add_field(name="To", value=after.channel.mention, inline=True)
            embed.set_footer(text="Ayanami System")
            await self.send_log(guild_id, embed)

        # === Mute / Deafen ===
        if before.self_mute != after.self_mute or before.self_deaf != after.self_deaf or before.mute != after.mute or before.deaf != after.deaf:
            if not await self.is_event_enabled(member.guild.id, "voice_state"):
                return
            changes = []
            if before.self_mute != after.self_mute:
                changes.append(f"**Microphone**: {'🔇 Off' if after.self_mute else '🔊 On'}")
            if before.self_deaf != after.self_deaf:
                changes.append(f"**Sound**: {'🔇 Off' if after.self_deaf else '🔊 On'}")
            if before.mute != after.mute:
                changes.append(f"**Mute (admin)**: {'🔇 Off' if after.mute else '🔊 On'}")
            if before.deaf != after.deaf:
                changes.append(f"**Deafen (admin)**: {'🔇 Off' if after.deaf else '🔊 On'}")
            if changes:
                embed = discord.Embed(title="Voice State Updated", color=discord.Color.teal(), timestamp=datetime.now(timezone.utc))
                embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
                embed.add_field(name="Member", value=member.mention, inline=True)
                embed.add_field(name="Channel", value=(after.channel or before.channel).mention, inline=True)
                embed.add_field(name="Changes", value="\n".join(changes), inline=False)
                embed.set_footer(text="Ayanami System")
                await self.send_log(member.guild.id, embed)

    # ==========================================
    #               SERVER
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        if not await self.is_event_enabled(after.id, "server_update"):
            return
        changes = []
        if before.name != after.name:
            changes.append(f"**Name**: `{before.name}` → `{after.name}`")
        if before.icon != after.icon:
            changes.append("**Icon**: updated" if after.icon else "**Icon**: removed")
        if before.splash != after.splash:
            changes.append("**Splash**: updated" if after.splash else "**Splash**: removed")
        if before.discovery_splash != after.discovery_splash:
            changes.append("**Discovery Splash**: updated" if after.discovery_splash else "**Discovery Splash**: removed")
        if before.banner != after.banner:
            changes.append("**Banner**: updated" if after.banner else "**Banner**: removed")
        if before.vanity_url_code != after.vanity_url_code:
            old_v = f"`{before.vanity_url_code}`" if before.vanity_url_code else "none"
            new_v = f"`{after.vanity_url_code}`" if after.vanity_url_code else "none"
            changes.append(f"**Vanity URL**: {old_v} → {new_v}")
        if before.owner_id != after.owner_id:
            changes.append(f"**Owner**: <@{before.owner_id}> → <@{after.owner_id}>")
        if before.description != after.description:
            changes.append(f"**Description**: `{(before.description or 'none')[:100]}` → `{(after.description or 'none')[:100]}`")
        if before.system_channel != after.system_channel:
            old_ch = before.system_channel.mention if before.system_channel else "none"
            new_ch = after.system_channel.mention if after.system_channel else "none"
            changes.append(f"**System Channel**: {old_ch} → {new_ch}")
        if before.rules_channel != after.rules_channel:
            old_ch = before.rules_channel.mention if before.rules_channel else "none"
            new_ch = after.rules_channel.mention if after.rules_channel else "none"
            changes.append(f"**Rules Channel**: {old_ch} → {new_ch}")
        if before.public_updates_channel != after.public_updates_channel:
            old_ch = before.public_updates_channel.mention if before.public_updates_channel else "none"
            new_ch = after.public_updates_channel.mention if after.public_updates_channel else "none"
            changes.append(f"**Updates Channel**: {old_ch} → {new_ch}")
        if before.verification_level != after.verification_level:
            changes.append(f"**Verification Level**: `{before.verification_level}` → `{after.verification_level}`")
        if before.explicit_content_filter != after.explicit_content_filter:
            changes.append(f"**Explicit Content Filter**: `{before.explicit_content_filter}` → `{after.explicit_content_filter}`")
        if before.default_notifications != after.default_notifications:
            changes.append(f"**Default Notifications**: `{before.default_notifications}` → `{after.default_notifications}`")
        if before.mfa_level != after.mfa_level:
            changes.append(f"**Require 2FA**: {'Yes' if after.mfa_level else 'No'}")
        if before.premium_tier != after.premium_tier:
            changes.append(f"**Boost Tier**: `{before.premium_tier}` → `{after.premium_tier}`")
        if before.premium_subscript_count != after.premium_subscript_count:
            changes.append(f"**Boost Count**: `{before.premium_subscript_count}` → `{after.premium_subscript_count}`")
        if not changes:
            return
        actor = await self.get_audit_actor(after, discord.AuditLogAction.guild_update, after.id)

        embed = discord.Embed(title="Server Updated", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
        if after.icon:
            embed.set_thumbnail(url=after.icon.url)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        embed.set_footer(text=self._actor_footer("Changed By", actor))
        await self.send_log(after.id, embed)

    # ==========================================
    #               THREADS
    # ==========================================

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        if not await self.is_event_enabled(thread.guild.id, "thread"):
            return
        actor = await self.get_audit_actor(thread.guild, discord.AuditLogAction.thread_create, thread.id)

        embed = discord.Embed(title="Thread Created", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=thread.name)
        embed.add_field(name="Thread", value=thread.mention, inline=True)
        embed.add_field(name="Channel", value=thread.parent.mention if thread.parent else "—", inline=True)
        embed.add_field(name="Auto-Archive", value=f"{thread.auto_archive_duration} min", inline=True)
        embed.set_footer(text=self._actor_footer("Created By", actor))
        await self.send_log(thread.guild.id, embed)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread):
        if not await self.is_event_enabled(thread.guild.id, "thread"):
            return
        actor = await self.get_audit_actor(thread.guild, discord.AuditLogAction.thread_delete, thread.id)

        embed = discord.Embed(title="Thread Deleted", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=thread.name)
        embed.add_field(name="Thread", value=f"`{thread.name}` (`{thread.id}`)", inline=True)
        embed.add_field(name="Channel", value=thread.parent.mention if thread.parent else "—", inline=True)
        embed.set_footer(text=self._actor_footer("Deleted By", actor))
        await self.send_log(thread.guild.id, embed)

    # ==========================================
    #               EVENTS
    # ==========================================

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event):
        if not await self.is_event_enabled(event.guild.id, "events"):
            return
        embed = discord.Embed(title="Event Created", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=event.name)
        embed.add_field(name="Name", value=event.name, inline=True)
        embed.add_field(name="Channel", value=event.channel.mention if event.channel else "—", inline=True)
        if event.description:
            embed.add_field(name="Description", value=event.description[:500], inline=False)
        embed.add_field(name="Start", value=f"<t:{int(event.start_time.timestamp())}:F>", inline=True)
        if event.end_time:
            embed.add_field(name="End", value=f"<t:{int(event.end_time.timestamp())}:F>", inline=True)
        embed.add_field(name="Status", value=str(event.status).title(), inline=True)
        if event.creator:
            embed.set_footer(text=f"Created By: {event.creator.display_name} ({event.creator.id})")
        else:
            embed.set_footer(text="Ayanami System")
        await self.send_log(event.guild.id, embed)

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before, after):
        if not await self.is_event_enabled(after.guild.id, "events"):
            return
        changes = []
        if before.name != after.name:
            changes.append(f"**Name**: `{before.name}` → `{after.name}`")
        if before.description != after.description:
            changes.append(f"**Description**: updated")
        if before.start_time != after.start_time:
            changes.append(f"**Start**: <t:{int(before.start_time.timestamp())}:R> → <t:{int(after.start_time.timestamp())}:R>")
        if before.end_time != after.end_time:
            if after.end_time:
                changes.append(f"**End**: <t:{int(after.end_time.timestamp())}:R>")
        if before.channel != after.channel:
            old_ch = before.channel.mention if before.channel else "none"
            new_ch = after.channel.mention if after.channel else "none"
            changes.append(f"**Channel**: {old_ch} → {new_ch}")
        if before.status != after.status:
            changes.append(f"**Status**: `{before.status}` → `{after.status}`")
        if not changes:
            return
        embed = discord.Embed(title="Event Updated", color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=after.name)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        embed.set_footer(text="Ayanami System")
        await self.send_log(after.guild.id, embed)

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event):
        if not await self.is_event_enabled(event.guild.id, "events"):
            return
        embed = discord.Embed(title="Event Deleted", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=event.name)
        embed.add_field(name="Name", value=f"`{event.name}`", inline=True)
        embed.add_field(name="Status", value=str(event.status).title(), inline=True)
        embed.set_footer(text="Ayanami System")
        await self.send_log(event.guild.id, embed)

    # ==========================================
    #               CHANNELS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not await self.is_event_enabled(channel.guild.id, "channel_create"):
            return
        actor = await self.get_audit_actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)

        embed = discord.Embed(title="Channel Created", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=channel.name)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        embed.set_footer(text=self._actor_footer("Created By", actor))
        await self.send_log(channel.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not await self.is_event_enabled(channel.guild.id, "channel_delete"):
            return
        actor = await self.get_audit_actor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)

        embed = discord.Embed(title="Channel Deleted", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=channel.name)
        embed.add_field(name="Channel", value=f"`{channel.name}` (`{channel.id}`)", inline=True)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        embed.set_footer(text=self._actor_footer("Deleted By", actor))
        await self.send_log(channel.guild.id, embed)

    # ==========================================
    #               PUNISHMENTS (via dispatch)
    # ==========================================

    @commands.Cog.listener()
    async def on_moderation_log(self, action: str, guild: discord.Guild, user, moderator, reason: str = None, duration: str = None):
        event_map = {
            "ban": "pun_ban", "unban": "pun_unban",
            "kick": "pun_kick",
            "mute": "pun_mute", "unmute": "pun_unmute",
            "warn": "pun_warn", "unwarn": "pun_unwarn",
            "blacklist": "pun_blacklist", "unblacklist": "pun_unblacklist",
        }
        event_key = event_map.get(action)
        if event_key and not await self.is_event_enabled(guild.id, event_key):
            return

        color_map = {
            "ban": discord.Color.dark_red(),
            "unban": discord.Color.green(),
            "kick": discord.Color.orange(),
            "mute": discord.Color.dark_purple(),
            "unmute": discord.Color.dark_teal(),
            "warn": discord.Color.gold(),
            "unwarn": discord.Color.dark_gold(),
            "blacklist": discord.Color.dark_red(),
            "unblacklist": discord.Color.green(),
        }
        title_map = {
            "ban": "User Banned",
            "unban": "User Unbanned",
            "kick": "User Kicked",
            "mute": "User Muted",
            "unmute": "User Unmuted",
            "warn": "User Warned",
            "unwarn": "User Unwarned",
            "blacklist": "User Blacklisted",
            "unblacklist": "User Unblacklisted",
        }

        embed = discord.Embed(title=title_map.get(action, action), color=color_map.get(action, discord.Color.red()), timestamp=datetime.now(timezone.utc))

        # Server icon as thumbnail
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # Server banner as image
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        # User: mention name id
        if hasattr(user, 'mention'):
            user_name = getattr(user, 'name', str(user))
            user_text = f"{user.mention} {user_name} {user.id}"
        else:
            user_text = str(user)
        embed.add_field(name="User", value=user_text, inline=False)

        # Moderator: mention name id
        if moderator:
            mod_name = getattr(moderator, 'name', str(moderator))
            mod_text = f"{moderator.mention} {mod_name} {moderator.id}"
        else:
            mod_text = "–"
        embed.add_field(name="Moderator", value=mod_text, inline=False)

        # Duration
        if duration:
            embed.add_field(name="Duration", value=duration, inline=False)

        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        bot_icon = self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty
        embed.set_footer(text="Ayanami System", icon_url=bot_icon)
        await self.send_log(guild.id, embed, mod_only=True)

    # ==========================================
    #               COMMANDS
    # ==========================================

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if not interaction.guild:
            return
        if not await self.is_event_enabled(interaction.guild.id, "commands"):
            return
        user = interaction.user
        user_text = f"{user.mention} {user.name} {user.id}"

        embed = discord.Embed(title="Command", color=discord.Color.teal(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=user_text, inline=False)
        embed.add_field(name="Command", value=f"`/{command.qualified_name}`", inline=True)
        embed.add_field(name="Channel", value=interaction.channel.mention, inline=True)
        embed.set_footer(text="Ayanami System")
        await self.send_log(interaction.guild.id, embed)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if not ctx.guild or not ctx.command:
            return
        if not await self.is_event_enabled(ctx.guild.id, "commands"):
            return
        user = ctx.author
        if user.bot:
            return
        user_text = f"{user.mention} {user.name} {user.id}"
        prefix = ctx.prefix or ""
        command = ctx.command
        command_text = f"`{prefix}{command.qualified_name}`"

        embed = discord.Embed(title="Command", color=discord.Color.teal(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=user_text, inline=False)
        embed.add_field(name="Command", value=command_text, inline=True)
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
        embed.set_footer(text="Ayanami System")
        await self.send_log(ctx.guild.id, embed)

    # ==========================================
    #               AVATAR / BANNER
    # ==========================================

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        if before.bot:
            return
        changes = []
        if before.display_avatar.url != after.display_avatar.url:
            changes.append(("Avatar", before.display_avatar.url, after.display_avatar.url))
        if getattr(before, 'banner', None) != getattr(after, 'banner', None):
            old_banner = before.banner.url if before.banner else "none"
            new_banner = after.banner.url if after.banner else "none"
            changes.append(("Banner", old_banner, new_banner))
        if before.name != after.name:
            changes.append(("Name", f"`{before.name}`", f"`{after.name}`"))
        if before.discriminator != after.discriminator:
            changes.append(("Discriminator", f"`{before.discriminator}`", f"`{after.discriminator}`"))

        if not changes:
            return

        for guild in after.mutual_guilds:
            if not await self.is_event_enabled(guild.id, "avatar"):
                continue
            embed = discord.Embed(title="Profile Updated", color=discord.Color.purple(), timestamp=datetime.now(timezone.utc))
            embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
            embed.add_field(name="Member", value=f"{after.mention} ({after.name}, ID: {after.id})", inline=False)
            for name, old_val, new_val in changes:
                if "URL" in name or name == "Avatar" or name == "Banner":
                    embed.add_field(name=f"{name} (Before)", value=old_val[:100] if old_val != "none" else "none", inline=True)
                    embed.add_field(name=f"{name} (After)", value=new_val[:100] if new_val != "none" else "none", inline=True)
                else:
                    embed.add_field(name=name, value=f"{old_val} → {new_val}", inline=True)
            embed.set_footer(text="Ayanami System")
            await self.send_log(guild.id, embed)

    # ==========================================
    #               PINS
    # ==========================================

    @commands.Cog.listener()
    async def on_message_pin(self, message):
        if not message.guild:
            return
        guild_id = message.guild.id
        if not await self.is_event_enabled(guild_id, "pins"):
            return

        embed = discord.Embed(title="Message Pinned", color=discord.Color.yellow(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="Author", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="Content", value=f"```\n{message.content[:1000]}\n```", inline=False)
        embed.add_field(name="Link", value=f"[Jump]({message.jump_url})", inline=True)
        embed.set_footer(text="Ayanami System")
        await self.send_log(guild_id, embed)


async def setup(bot):
    await bot.add_cog(Logging(bot))
