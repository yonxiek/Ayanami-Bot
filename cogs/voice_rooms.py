import discord
from discord.ext import commands
from db import Database
from ui_components import Colors



class KickSelectView(discord.ui.View):
    def __init__(self, channel, owner):
        super().__init__(timeout=60)
        self.channel = channel
        self.owner = owner
        members = [m for m in channel.members if m.id != owner.id and not m.bot]
        select = discord.ui.Select(
            placeholder="Выберите кого выгнать",
            min_values=1, max_values=1,
            options=[
                discord.ui.SelectOption(
                    label=m.display_name,
                    value=str(m.id),
                    emoji="👤"
                ) for m in members
            ]
        )
        select.callback = self.kick_callback
        self.add_item(select)

    async def kick_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner.id:
            return await interaction.response.send_message("❌ Только владелец!", ephemeral=True)
        target_id = int(interaction.data["values"][0])
        target = interaction.guild.get_member(target_id)
        if not target:
            return await interaction.response.send_message("❌ Участник не найден!", ephemeral=True)
        await interaction.response.defer()
        overwrites = self.channel.overwrites_for(target)
        overwrites.connect = False
        await self.channel.set_permissions(target, overwrite=overwrites, reason="Kick from voice room")
        if target.voice and target.voice.channel == self.channel:
            await target.move_to(None, reason="Kicked from voice room")
        await interaction.followup.send(f"👢 **{target.display_name}** выгнан!", ephemeral=True)
        self.stop()


class VoiceRoomManageView(discord.ui.LayoutView):
    def __init__(self, cog, channel, owner):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel = channel
        self.owner = owner
        self._build_ui()

    def _build_ui(self):
        self.clear_items()
        container = discord.ui.Container(accent_color=discord.Color(0x2b2d31))
        container.add_item(discord.ui.TextDisplay("### 🔊 Приватная комната"))
        container.add_item(discord.ui.TextDisplay(
            f"**👤 Владелец:** {self.owner.mention}\n"
            f"**📢 Канал:** {self.channel.mention}\n"
            f"**📊 Лимит:** {self.channel.user_limit or 'Без лимита'}\n"
            f"**👥 Участников:** {len(self.channel.members)}"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("*Управление доступно только владельцу*"))
        self.add_item(container)

        row0 = discord.ui.ActionRow()
        btn_limit = discord.ui.Button(label="Лимит", emoji="🔢", style=discord.ButtonStyle.secondary, custom_id="vrm_limit_btn")
        btn_limit.callback = self.btn_limit_callback
        row0.add_item(btn_limit)
        btn_rename = discord.ui.Button(label="Название", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="vrm_rename_btn")
        btn_rename.callback = self.btn_rename_callback
        row0.add_item(btn_rename)
        btn_lock = discord.ui.Button(label="Закрыть", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="vrm_lock_btn")
        btn_lock.callback = self.btn_lock_callback
        row0.add_item(btn_lock)
        self.add_item(row0)

        row1 = discord.ui.ActionRow()
        btn_unlock = discord.ui.Button(label="Открыть", emoji="🔓", style=discord.ButtonStyle.success, custom_id="vrm_unlock_btn")
        btn_unlock.callback = self.btn_unlock_callback
        row1.add_item(btn_unlock)
        btn_hide = discord.ui.Button(label="Скрыть", emoji="🙈", style=discord.ButtonStyle.danger, custom_id="vrm_hide_btn")
        btn_hide.callback = self.btn_hide_callback
        row1.add_item(btn_hide)
        btn_show = discord.ui.Button(label="Показать", emoji="🐵", style=discord.ButtonStyle.success, custom_id="vrm_show_btn")
        btn_show.callback = self.btn_show_callback
        row1.add_item(btn_show)
        self.add_item(row1)

        row2 = discord.ui.ActionRow()
        btn_delete = discord.ui.Button(label="Удалить", emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="vrm_delete_btn")
        btn_delete.callback = self.btn_delete_callback
        row2.add_item(btn_delete)
        btn_kick = discord.ui.Button(label="Кик", emoji="👢", style=discord.ButtonStyle.secondary, custom_id="vrm_kick_btn")
        btn_kick.callback = self.btn_kick_callback
        row2.add_item(btn_kick)
        self.add_item(row2)

    def _is_owner(self, user):
        return user.id == self.owner.id

    def _check(self, interaction):
        if not self._is_owner(interaction.user):
            interaction.response.send_message("❌ Только владелец комнаты!", ephemeral=True)
            return False
        return True

    async def btn_limit_callback(self, interaction: discord.Interaction):
        if not self._check(interaction): return
        await interaction.response.send_modal(VoiceRoomLimitModal(self.channel))

    async def btn_rename_callback(self, interaction: discord.Interaction):
        if not self._check(interaction): return
        await interaction.response.send_modal(VoiceRoomRenameModal(self.channel))

    async def btn_lock_callback(self, interaction: discord.Interaction):
        if not self._check(interaction): return
        await interaction.response.defer()
        everyone = discord.utils.get(interaction.guild.roles, name="@everyone")
        overwrites = self.channel.overwrites_for(everyone)
        overwrites.connect = False
        await self.channel.set_permissions(everyone, overwrite=overwrites, reason="Lock voice room")
        await interaction.followup.send("🔒 **Комната закрыта!**", ephemeral=True)

    async def btn_unlock_callback(self, interaction: discord.Interaction):
        if not self._check(interaction): return
        await interaction.response.defer()
        everyone = discord.utils.get(interaction.guild.roles, name="@everyone")
        overwrites = self.channel.overwrites_for(everyone)
        overwrites.connect = None
        await self.channel.set_permissions(everyone, overwrite=overwrites, reason="Unlock voice room")
        await interaction.followup.send("🔓 **Комната открыта!**", ephemeral=True)

    async def btn_hide_callback(self, interaction: discord.Interaction):
        if not self._check(interaction): return
        await interaction.response.defer()
        everyone = discord.utils.get(interaction.guild.roles, name="@everyone")
        overwrites = self.channel.overwrites_for(everyone)
        overwrites.view_channel = False
        await self.channel.set_permissions(everyone, overwrite=overwrites, reason="Hide voice room")
        await interaction.followup.send("🙈 **Комната скрыта!**", ephemeral=True)

    async def btn_show_callback(self, interaction: discord.Interaction):
        if not self._check(interaction): return
        await interaction.response.defer()
        everyone = discord.utils.get(interaction.guild.roles, name="@everyone")
        overwrites = self.channel.overwrites_for(everyone)
        overwrites.view_channel = None
        await self.channel.set_permissions(everyone, overwrite=overwrites, reason="Show voice room")
        await interaction.followup.send("🐵 **Комната видна!**", ephemeral=True)

    async def btn_delete_callback(self, interaction: discord.Interaction):
        if not self._check(interaction): return
        await interaction.response.defer()
        try:
            await self.channel.delete(reason="Owner deleted voice room")
        except Exception:
            pass

    async def btn_kick_callback(self, interaction: discord.Interaction):
        if not self._check(interaction): return
        members = [m for m in self.channel.members if m.id != self.owner.id and not m.bot]
        if not members:
            return await interaction.response.send_message("❌ В комнате никого кроме тебя!", ephemeral=True)
        view = KickSelectView(self.channel, self.owner)
        await interaction.response.send_message("Выбери кого выгнать:", view=view, ephemeral=True)


class VoiceRoomLimitModal(discord.ui.Modal, title="🔢 Лимит участников"):
    limit_input = discord.ui.TextInput(
        label="Максимум (0 = без лимита)",
        placeholder="Например: 5",
        max_length=2,
        required=True
    )

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.limit_input.value)
            if limit < 0 or limit > 99:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Введите число от 0 до 99!", ephemeral=True)
        await self.channel.edit(user_limit=limit if limit > 0 else 0, reason="Voice room limit")
        text = f"**{limit}** участников" if limit > 0 else "Без лимита"
        await interaction.response.send_message(f"✅ Лимит: {text}", ephemeral=True)


class VoiceRoomRenameModal(discord.ui.Modal, title="✏️ Переименовать"):
    name_input = discord.ui.TextInput(
        label="Название",
        placeholder="Название комнаты",
        max_length=50,
        required=True
    )

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()[:50]
        await self.channel.edit(name=name, reason="Rename voice room")
        await interaction.response.send_message(f"✅ Название: **{name}**", ephemeral=True)


class VoiceRooms(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.channel_owners = {}
        self.control_messages = {}

    async def cog_load(self):
        pass

    def is_voice_room(self, channel_id: int) -> bool:
        return channel_id in self.channel_owners

    def get_owner(self, channel_id: int) -> int:
        return self.channel_owners.get(channel_id)

    async def send_controls(self, voice_channel, owner):
        view = VoiceRoomManageView(self, voice_channel, owner)
        try:
            msg = await voice_channel.send(embed=embed)
            self.control_messages[voice_channel.id] = msg
            print(f"[VoiceRooms] Панель отправлена в {voice_channel.name} для {owner.name}")
        except Exception as e:
            print(f"[VoiceRooms] Ошибка отправки панели в {voice_channel.name}: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild:
            return
        config = await self.db.get_guild_config(str(member.guild.id))
        vr_config = config.get("voice_rooms", {})
        trigger_id = vr_config.get("trigger_channel_id")
        if not trigger_id:
            return
        trigger_id = int(trigger_id)

        if after.channel and after.channel.id == trigger_id:
            guild = member.guild
            category_id = vr_config.get("category_id")
            category = guild.get_channel(int(category_id)) if category_id else None
            room_type = vr_config.get("room_type", "personal")
            type_map = {"personal": 1, "duo": 2, "group": 5, "team": 10}
            user_limit = type_map.get(room_type, 0)
            type_names = {"personal": "👤 Личная", "duo": "👥 Дуэт", "group": "👨‍👩‍👧‍👦 Группа", "team": "🏠 Команда"}
            channel_name = f"{type_names.get(room_type, '🔒')} {member.display_name}"
            try:
                channel = await guild.create_voice_channel(name=channel_name, category=category, user_limit=user_limit, reason=f"Private room for {member.name}")
            except Exception as e:
                print(f"[VoiceRooms] Ошибка создания канала: {e}")
                return
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False),
                member: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)
            }
            await channel.edit(overwrites=overwrites)
            self.channel_owners[channel.id] = member.id
            try:
                await member.move_to(channel, reason="Auto voice room")
            except Exception:
                await channel.delete(reason="Failed to move member")
                return
            await self.send_controls(channel, member)

        if before.channel and before.channel.id != trigger_id:
            channel = before.channel
            if channel.id in self.control_messages:
                try:
                    await self.control_messages[channel.id].delete()
                except Exception:
                    pass
                del self.control_messages[channel.id]
            if len(channel.members) == 0:
                if channel.id in self.channel_owners:
                    del self.channel_owners[channel.id]
                try:
                    await channel.delete(reason="Voice room empty")
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or not message.author:
            return
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.VoiceChannel):
            return
        if not self.is_voice_room(message.channel.id):
            return
        if message.interaction or message.embeds:
            return
        try:
            await message.delete()
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(VoiceRooms(bot))
