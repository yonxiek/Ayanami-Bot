import discord
from discord.ext import commands, tasks
from discord import app_commands
from db import Database

# ==================== БЛОК SERVER STATS ====================
class Voice(commands.Cog):
#    stats_group = app_commands.Group(name="stats", description="Управление статистикой сервера")

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.update_stats.start()

    def cog_unload(self): 
        self.update_stats.cancel()

    @tasks.loop(minutes=30)
    async def update_stats(self):
        for guild in self.bot.guilds:
            config = await self.db.get_guild_config(str(guild.id))
            stats_channels = config.get('stats_channels', {})
            if not stats_channels: continue
            
            data = { 'total': guild.member_count, 'online': len([m for m in guild.members if m.status != discord.Status.offline]) }
            
            for stat_type, channel_id in stats_channels.items():
                channel = guild.get_channel(channel_id)
                if not channel: continue
                new_name = f"{'Всего' if stat_type=='total' else 'Онлайн'}: {data.get(stat_type, 0)}"
                if channel.name != new_name:
                    try: await channel.edit(name=new_name)
                    except: pass

    @update_stats.before_loop
    async def before_update(self): await self.bot.wait_until_ready()

#    @stats_group.command(name="create", description="Создать каналы статистики")
    @app_commands.default_permissions(administrator=True)
    async def stats_create_slash(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await interaction.response.defer(ephemeral=True)
        ch1 = await interaction.guild.create_voice_channel(name=f"Всего: {interaction.guild.member_count}", category=category)
        
        config = await self.db.get_guild_config(str(interaction.guild.id))
        config['stats_channels'] = {'total': ch1.id}
        await self.db.update_guild_config(str(interaction.guild.id), **config)
        
        await interaction.followup.send("Каналы статистики успешно созданы.")

# ==================== БЛОК VOICE PRIVATE ====================

    async def get_user_room(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("VoicePrivate")
        owner_channel = await cog.db.get_user_voice_channel(str(interaction.guild.id), str(interaction.user.id))
        if not owner_channel:
            await interaction.response.send_message("У вас нет активной приватной комнаты.", ephemeral=True)
            return None, None
        return cog, interaction.guild.get_channel(int(owner_channel["channel_id"]))

    @discord.ui.button(label="Закрыть / Открыть", custom_id="gp_lock", style=discord.ButtonStyle.grey)
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, voice_channel = await self.get_user_room(interaction)
        if not voice_channel: return
        is_locked = voice_channel.overwrites_for(interaction.guild.default_role).connect == False
        await voice_channel.set_permissions(interaction.guild.default_role, connect=None if is_locked else False)
        await interaction.response.send_message("Комната открыта." if is_locked else "Комната закрыта.", ephemeral=True)

class VoicePrivate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def cog_load(self):
        self.bot.add_view(GlobalPrivatePanel())
        self.cleanup_empty_rooms.start()

    def cog_unload(self): 
        self.cleanup_empty_rooms.cancel()

    @tasks.loop(minutes=3)
    async def cleanup_empty_rooms(self):
        cursor = await self.db.conn.execute("SELECT channel_id, guild_id FROM voice_channels")
        for room in await cursor.fetchall():
            guild = self.bot.get_guild(int(room['guild_id']))
            if not guild: continue
            channel = guild.get_channel(int(room['channel_id']))
            if channel and len(channel.members) == 0:
                try:
                    await channel.delete(reason="Авто-очистка приватных комнат")
                    await self.db.conn.execute("DELETE FROM voice_channels WHERE channel_id = ?", (room['channel_id'],))
                    await self.db.conn.commit()
                except: pass

    @app_commands.command(name="setupvoice", description="Настроить систему приватных комнат")
    @app_commands.default_permissions(administrator=True)
    async def setupvoice_slash(self, interaction: discord.Interaction, trigger_channel: discord.VoiceChannel, category: discord.CategoryChannel, panel_channel: discord.TextChannel):
        config = await self.db.get_guild_config(str(interaction.guild.id))
        config["private_trigger_id"] = trigger_channel.id
        config["private_category_id"] = category.id
        await self.db.update_guild_config(str(interaction.guild.id), **config)
        
        await panel_channel.send(
            embed=discord.Embed(title="Приватные Комнаты", description="Управляйте вашей комнатой, нажимая на кнопки ниже.", color=discord.Color.blurple()), 
            view=GlobalPrivatePanel()
        )
        await interaction.response.send_message("Система приватных комнат настроена.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        config = await self.db.get_guild_config(str(member.guild.id))
        trigger_id = config.get("private_trigger_id")
        
        if after.channel and after.channel.id == trigger_id:
            category = member.guild.get_channel(config.get("private_category_id"))
            if not category: return
            try:
                new_ch = await member.guild.create_voice_channel(name=f"Комната {member.display_name}", category=category)
                await self.db.add_voice_channel(str(member.guild.id), str(new_ch.id), str(member.id), new_ch.name)
                await member.move_to(new_ch)
            except: pass

async def setup(bot):
    await bot.add_cog(Voice(bot))
