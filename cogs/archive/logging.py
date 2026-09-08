# cogs/logging.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
from typing import Dict, Any
from db import Database
import asyncio

# ==========================================
#          ЭЛЕМЕНТЫ ИНТЕРФЕЙСА УПРАВЛЕНИЯ
# ==========================================
class ToggleLogButton(discord.ui.Button):
    def __init__(self, cog, guild_id: int, enabled: bool):
        style = discord.ButtonStyle.green if enabled else discord.ButtonStyle.red
        label = "✅ Логи Включены" if enabled else "❌ Логи Выключены"
        super().__init__(label=label, style=style, row=0)
        self.cog = cog
        self.guild_id = guild_id
        self.enabled = enabled
        
    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator: 
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await self.cog.update_guild_config(self.guild_id, enabled=not self.enabled)
        await self.view.update_message(interaction)

class LogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, cog, guild_id: int):
        super().__init__(placeholder="Выберите канал для логов...", channel_types=[discord.ChannelType.text], row=1)
        self.cog = cog
        self.guild_id = guild_id
        
    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator: 
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        channel_id = self.values[0].id
        await self.cog.update_guild_config(self.guild_id, log_channel_id=channel_id)
        await self.view.update_message(interaction)

class LogEventsSelect(discord.ui.Select):
    def __init__(self, cog, guild_id: int, current_events: dict):
        options = [
            discord.SelectOption(label="Сообщения", value="messages", description="Удаления и изменения сообщений", default=current_events.get("messages", True)),
            discord.SelectOption(label="Участники", value="members", description="Входы и выходы участников", default=current_events.get("members", True)),
            discord.SelectOption(label="Голосовые", value="voice", description="Вход и выход из войсов", default=current_events.get("voice", True)),
            discord.SelectOption(label="Роли и Ники", value="roles", description="Изменения профиля", default=current_events.get("roles", True)),
            discord.SelectOption(label="Каналы", value="channels", description="Создание и удаление", default=current_events.get("channels", True)),
            discord.SelectOption(label="Баны", value="bans", description="Блокировки и кики", default=current_events.get("bans", True)),
            discord.SelectOption(label="Команды", value="commands", description="Использование команд бота", default=current_events.get("commands", True)),
        ]
        super().__init__(placeholder="Какие события отслеживать?", min_values=0, max_values=7, options=options, row=2)
        self.cog = cog
        self.guild_id = guild_id
        
    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator: 
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        
        new_events = {
            "messages": "messages" in self.values,
            "members": "members" in self.values,
            "voice": "voice" in self.values,
            "roles": "roles" in self.values,
            "channels": "channels" in self.values,
            "bans": "bans" in self.values,
            "commands": "commands" in self.values,
        }
        await self.cog.update_guild_config(self.guild_id, enabled_events=new_events)
        await self.view.update_message(interaction)

class LogSettingsView(discord.ui.View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild_id = guild_id

    async def build_ui(self):
        self.clear_items()
        cfg = await self.cog.get_guild_config(self.guild_id)
        
        self.add_item(ToggleLogButton(self.cog, self.guild_id, cfg['enabled']))
        self.add_item(LogChannelSelect(self.cog, self.guild_id))
        self.add_item(LogEventsSelect(self.cog, self.guild_id, cfg.get('enabled_events', {})))

    async def update_message(self, interaction: discord.Interaction):
        await self.build_ui()
        embed = await self.cog.get_status_embed(self.guild_id)
        await interaction.response.edit_message(embed=embed, view=self)


# ==========================================
#               ОСНОВНОЙ КОГ
# ==========================================
class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.guild_config_cache = {}
        self.cleanup_task = self.bot.loop.create_task(self.periodic_cleanup())

    def cog_unload(self):
        if self.cleanup_task: self.cleanup_task.cancel()

    async def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        gid = str(guild_id)
        if gid in self.guild_config_cache: return self.guild_config_cache[gid]

        config = await self.db.get_guild_config(gid)
        if 'logging' not in config:
            config['logging'] = self.get_default_guild_config()
            await self.db.update_guild_config(gid, **config)

        cfg = config['logging']
        self.guild_config_cache[gid] = cfg
        return cfg

    async def update_guild_config(self, guild_id: int, **kwargs):
        gid = str(guild_id)
        config = await self.db.get_guild_config(gid)
        if 'logging' not in config: config['logging'] = self.get_default_guild_config()
        config['logging'].update(kwargs)
        config['logging']['updated_at'] = datetime.now(timezone.utc).isoformat()
        await self.db.update_guild_config(gid, **config)
        self.guild_config_cache[gid] = config['logging']

    def get_default_guild_config(self) -> dict:
        return {
            'enabled': True, 'log_channel_id': None, 'points_log_channel_id': None, 'log_level': 'normal',
            'ignored_commands': [], 'ignored_users': [], 'ignored_channels': [],
            'created_at': datetime.now(timezone.utc).isoformat(),
            'enabled_events': {
                'messages': True, 'members': True, 'voice': True, 
                'roles': True, 'channels': True, 'bans': True, 'commands': True
            }
        }

    async def periodic_cleanup(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try: await self.db.cleanup_old_logs(90)
            except: pass
            await asyncio.sleep(86400)

    async def get_status_embed(self, guild_id: int) -> discord.Embed:
        cfg = await self.get_guild_config(guild_id)
        embed = discord.Embed(title="⚙️ Панель управления логированием", color=discord.Color.blurple())
        
        status = "🟢 Включено" if cfg['enabled'] else "🔴 Выключено"
        channel = f"<#{cfg['log_channel_id']}>" if cfg['log_channel_id'] else "`Не выбран`"
        
        embed.add_field(name="Статус системы", value=status, inline=True)
        embed.add_field(name="Канал отправки", value=channel, inline=True)
        
        events = cfg.get("enabled_events", {})
        events_map = {
            "messages": "Сообщения", "members": "Участники", "voice": "Голосовые",
            "roles": "Роли и Ники", "channels": "Каналы", "bans": "Баны", "commands": "Команды бота"
        }
        
        events_str = "\n".join([f"{'✅' if events.get(k, True) else '❌'} {v}" for k, v in events_map.items()])
        embed.add_field(name="Отслеживаемые события", value=events_str, inline=False)
        return embed

    async def send_log(self, guild_id: int, embed: discord.Embed):
        cfg = await self.get_guild_config(guild_id)
        if not cfg['enabled'] or not cfg.get('log_channel_id'): return

        channel = self.bot.get_channel(cfg['log_channel_id'])
        if not channel: return

        embed.timestamp = datetime.now(timezone.utc)
        
        try:
            webhooks = await channel.webhooks()
            webhook = discord.utils.get(webhooks, user=self.bot.user)
            
            if not webhook:
                webhook = await channel.create_webhook(name=f"{self.bot.user.name} Logger")

            await webhook.send(embed=embed, username="Система Логирования", avatar_url=self.bot.user.display_avatar.url)
        except discord.Forbidden:
            try: await channel.send(embed=embed)
            except: pass
        except Exception: pass

    # ==========================================
    #                  EVENTS
    # ==========================================

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot: return
        cfg = await self.get_guild_config(message.guild.id)
        if not cfg.get('enabled_events', {}).get('messages', True): return
        
        embed = discord.Embed(title="🗑️ Сообщение удалено", color=discord.Color.red())
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="Автор", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name="Канал", value=message.channel.mention, inline=True)
        if message.content: 
            embed.add_field(name="Содержание", value=f"```\n{message.content[:1010]}\n```", inline=False)
        
        await self.send_log(message.guild.id, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.content == after.content or not before.guild or before.author.bot: return
        cfg = await self.get_guild_config(before.guild.id)
        if not cfg.get('enabled_events', {}).get('messages', True): return

        embed = discord.Embed(title="✏️ Сообщение изменено", url=after.jump_url, color=discord.Color.orange())
        embed.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
        embed.add_field(name="Автор", value=f"{before.author.mention} (`{before.author.id}`)", inline=True)
        embed.add_field(name="Канал", value=before.channel.mention, inline=True)
        embed.add_field(name="Было", value=f"```\n{before.content[:1010] or 'Пусто'}\n```", inline=False)
        embed.add_field(name="Стало", value=f"```\n{after.content[:1010] or 'Пусто'}\n```", inline=False)
        
        await self.send_log(before.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        cfg = await self.get_guild_config(member.guild.id)
        if not cfg.get('enabled_events', {}).get('members', True): return

        embed = discord.Embed(title="📥 Участник присоединился", color=discord.Color.green())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Участник", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Аккаунт создан", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=False)
        
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        cfg = await self.get_guild_config(member.guild.id)
        if not cfg.get('enabled_events', {}).get('members', True): return

        embed = discord.Embed(title="📤 Участник покинул сервер", color=discord.Color.red())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Участник", value=f"{member.mention} (`{member.id}`)", inline=False)
        
        if member.joined_at:
            embed.add_field(name="Был на сервере с", value=f"<t:{int(member.joined_at.timestamp())}:f>", inline=False)
            
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        cfg = await self.get_guild_config(before.guild.id)
        if not cfg.get('enabled_events', {}).get('roles', True): return
        
        if len(before.roles) != len(after.roles):
            added = [r.mention for r in after.roles if r not in before.roles]
            removed = [r.mention for r in before.roles if r not in after.roles]
            if added or removed:
                embed = discord.Embed(title="🎭 Изменение ролей", color=discord.Color.blue())
                embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                embed.add_field(name="Участник", value=f"{after.mention} (`{after.id}`)", inline=False)
                if added: embed.add_field(name="Выданы", value=", ".join(added), inline=True)
                if removed: embed.add_field(name="Сняты", value=", ".join(removed), inline=True)
                await self.send_log(before.guild.id, embed)

        if before.nick != after.nick:
            embed = discord.Embed(title="📝 Изменение никнейма", color=discord.Color.purple())
            embed.set_author(name=after.name, icon_url=after.display_avatar.url)
            embed.add_field(name="Участник", value=f"{after.mention} (`{after.id}`)", inline=False)
            embed.add_field(name="Старый ник", value=before.nick or before.name, inline=True)
            embed.add_field(name="Новый ник", value=after.nick or after.name, inline=True)
            await self.send_log(before.guild.id, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        cfg = await self.get_guild_config(member.guild.id)
        if not cfg.get('enabled_events', {}).get('voice', True): return
        
        embed = None
        if not before.channel and after.channel:
            embed = discord.Embed(title="🎙️ Подключение к Voice", description=f"{member.mention} зашел в канал {after.channel.mention}", color=discord.Color.green())
        elif before.channel and not after.channel:
            embed = discord.Embed(title="🔇 Отключение от Voice", description=f"{member.mention} вышел из канала {before.channel.mention}", color=discord.Color.red())
        elif before.channel and after.channel and before.channel != after.channel:
            embed = discord.Embed(title="🔀 Перемещение в Voice", description=f"{member.mention} перешел из {before.channel.mention} в {after.channel.mention}", color=discord.Color.blue())
            
        if embed:
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        cfg = await self.get_guild_config(guild.id)
        if not cfg.get('enabled_events', {}).get('bans', True): return
        
        embed = discord.Embed(title="🔨 Пользователь забанен", description=f"{user.mention} (`{user.id}`) был заблокирован на сервере.", color=discord.Color.dark_red())
        embed.set_thumbnail(url=user.display_avatar.url)
        await self.send_log(guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        cfg = await self.get_guild_config(channel.guild.id)
        if not cfg.get('enabled_events', {}).get('channels', True): return
        
        embed = discord.Embed(title="📁 Канал создан", description=f"Канал {channel.mention} (`{channel.name}`) был создан.", color=discord.Color.green())
        await self.send_log(channel.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        cfg = await self.get_guild_config(channel.guild.id)
        if not cfg.get('enabled_events', {}).get('channels', True): return
        
        embed = discord.Embed(title="🗑️ Канал удален", description=f"Канал `{channel.name}` был удален.", color=discord.Color.red())
        await self.send_log(channel.guild.id, embed)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if not interaction.guild: return
        cfg = await self.get_guild_config(interaction.guild.id)
        if not cfg.get('enabled_events', {}).get('commands', True): return

        user = interaction.user
        options_text = "Без параметров"
        if interaction.data.get('options'):
            def parse_opts(opts):
                res = []
                for opt in opts:
                    if 'value' in opt: res.append(f"**{opt['name']}**: `{opt['value']}`")
                    elif 'options' in opt: res.extend(parse_opts(opt['options']))
                return res
            parsed = parse_opts(interaction.data['options'])
            if parsed: options_text = "\n".join(parsed)

        embed = discord.Embed(title="💻 Использована слэш-команда", color=discord.Color.teal())
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.add_field(name="Команда", value=f"`/{command.qualified_name}`", inline=True)
        embed.add_field(name="Пользователь", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Канал", value=interaction.channel.mention, inline=True)
        embed.add_field(name="Параметры", value=options_text, inline=False)

        await self.send_log(interaction.guild.id, embed)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if not ctx.guild: return
        cfg = await self.get_guild_config(ctx.guild.id)
        if not cfg.get('enabled_events', {}).get('commands', True): return

        embed = discord.Embed(title="⌨️ Использована текстовая команда", color=discord.Color.dark_teal())
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Команда", value=f"`{ctx.command.qualified_name}`", inline=True)
        embed.add_field(name="Пользователь", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
        embed.add_field(name="Канал", value=ctx.channel.mention, inline=True)
        embed.add_field(name="Полное сообщение", value=f"```text\n{ctx.message.content}\n```", inline=False)

        await self.send_log(ctx.guild.id, embed)

    # ==========================================
    #     ЕДИНАЯ КОМАНДА ДЛЯ НАСТРОЙКИ (/logs)
    # ==========================================

#    @app_commands.command(name="logs", description="Открыть панель управления логированием сервера")
    @app_commands.default_permissions(administrator=True)
    async def logs_slash(self, interaction: discord.Interaction):
        view = LogSettingsView(self, interaction.guild.id)
        await view.build_ui()
        embed = await self.get_status_embed(interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

#    @commands.command(name="logs")
    @commands.has_permissions(administrator=True)
    async def logs_prefix(self, ctx):
        view = LogSettingsView(self, ctx.guild.id)
        await view.build_ui()
        embed = await self.get_status_embed(ctx.guild.id)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Logging(bot))
