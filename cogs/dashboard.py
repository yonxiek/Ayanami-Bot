import discord
from discord.ext import commands
from discord import app_commands
from ui_components import AyanamiUI, Icons, Colors
from db import Database



# ==========================================
#   КНОПКА «НАЗАД»
# ==========================================

class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀️ Назад", style=discord.ButtonStyle.secondary, row=4)

    async def callback(self, interaction: discord.Interaction):
        db = Database()
        config = await db.get_guild_config(str(self.view.guild_id))
        quests = await db.get_guild_quests(str(self.view.guild_id))
        shop_items = await db.get_shop_items(str(self.view.guild_id))
        view = DashboardView(self.view.cog, self.view.guild_id, config, len(quests), len(shop_items))
        await interaction.response.edit_message(view=view)


# ==========================================
#   ОСНОВНОЕ МЕНЮ
# ==========================================

class DashboardView(discord.ui.LayoutView):
    def __init__(self, cog, guild_id: int, config: dict, quest_count: int, shop_count: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id

        sec = config.get("security", {})
        log_ch = config.get("log_channel_id")
        log_events = config.get("log_events", {})
        enabled_logs = sum(1 for v in log_events.values() if v) if log_events else 0
        total_logs = len(log_events) if log_events else 10

        status_lines = []
        status_lines.append(f"🛡️ **Безопасность:** {'🟢 Вкл' if sec.get('enabled', True) else '🔴 Выкл'} | Наказание: `{sec.get('punishment', 'ban')}`")
        status_lines.append(f"📋 **Логи:** {enabled_logs}/{total_logs} событий | Канал: {f'<#{log_ch}>' if log_ch else '❌ Не настроен'}")
        status_lines.append(f"📜 **Квесты:** {quest_count} активных | 🛒 **Магазин:** {shop_count} товаров")
        status_lines.append(f"📊 **Уровни:** {'🟢 Вкл' if config.get('xp_enabled', True) else '🔴 Выкл'} | ⚡ XP/сообщение: `{config.get('xp_per_message', 15)}`")
        automod = config.get('automod', {})
        automod_on = sum(1 for k, v in automod.items() if v is True and k.startswith('anti_'))
        status_lines.append(f"🤖 **Авто-мод:** {automod_on} фильтров | Действие: `{automod.get('action', 'warn')}`")

        welcome = '🟢' if config.get('welcome_enabled') else '🔴'
        leave = '🟢' if config.get('leave_enabled') else '🔴'
        boost = '🟢' if config.get('boost_enabled') else '🔴'
        autorole = '🟢' if config.get('autorole_enabled') else '🔴'
        status_lines.append(f"👋 **Приветствия:** {welcome} Привет | {leave} Прощание | {boost} Буст | {autorole} Автороли")
        status_lines.append(f"📝 **Префикс:** `{config.get('prefix', '!')}` | 🟢 **Статус:** `{config.get('bot_status_text', '') or '—'}`")

        container = discord.ui.Container(accent_color=Colors.MAIN)
        container.add_item(discord.ui.TextDisplay("### Ayanami System | Настройка"))
        container.add_item(discord.ui.TextDisplay("\n".join(status_lines)))
        container.add_item(discord.ui.Separator(visible=False))
        container.add_item(discord.ui.TextDisplay("*Выберите модуль в меню ниже. В каждом разделе есть кнопка «Текущие настройки» или «Справка».*"))

        options = [
            discord.SelectOption(label="Основные настройки", value="general", description="Настройки сервера, бустер-бонус, авто-модерация"),
            discord.SelectOption(label="Рейды", value="raids", emoji="⚔️", description="Роли и каналы для организации рейдов"),
            discord.SelectOption(label="Логирование", value="logging", emoji="📋", description="Канал логов и отслеживаемые события"),
            discord.SelectOption(label="Приветствия", value="greetings", emoji="👋", description="Привет, прощание, буст и автороли"),
            discord.SelectOption(label="Реакции", value="reactions", emoji="🎭", description="Авто-реакции на определённые слова"),
            discord.SelectOption(label="Reaction Roles", value="reaction_roles", emoji="🎯", description="Роли по реакциям на сообщениях"),
            discord.SelectOption(label="Приватные голосовые", value="voice", emoji="🔊", description="Триггер-канал и типы приватных комнат"),
            discord.SelectOption(label="Каналы и Роли", value="channels", emoji="📢", description="Жалобы, логи повышений и персонал"),
            discord.SelectOption(label="Роли", value="roles", emoji="🛡️", description="Роль чёрного списка и иммунитета"),
            discord.SelectOption(label="Безопасность", value="security", emoji="🚨", description="Anti-Nuke защита и пороги срабатывания"),
            discord.SelectOption(label="Уровни", value="levels", emoji="📊", description="Система уровней, XP, роли за уровни"),
            discord.SelectOption(label="Авто-модерация", value="automod", emoji="🤖", description="Анти-спам, капс, ссылки, 크аптча"),
            discord.SelectOption(label="Приватные команды", value="private", emoji="🔐", description="Скрытие команд от определённых ролей"),
            discord.SelectOption(label="Права команд", value="perms", emoji="🔒", description="Доступ к командам по ролям"),
            discord.SelectOption(label="Квесты", value="quests", emoji="📜", description="Ежедневные квесты и награды за прогресс"),
            discord.SelectOption(label="Магазин", value="shop", emoji="🛒", description="Товары, цены и стоки магазина"),
            discord.SelectOption(label="Титулы", value="titles", emoji="🏷️", description="Выдача и управление титулами участников"),
            discord.SelectOption(label="Модерация", value="moderation", emoji="⚖️", description="Лимит варнов, автодействия, канал логов модерации"),
        ]
        select = discord.ui.Select(placeholder="Выберите модуль для настройки...", options=options)
        select.callback = self.menu_callback

        action_row = discord.ui.ActionRow(select)
        container.add_item(action_row)
        self.add_item(container)

    async def menu_callback(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        db = Database()

        view_map = {
            "general": lambda: SetupAdminView(self.cog, db, self.guild_id),
            "raids": lambda: SetupRaidView(self.cog, db, self.guild_id),
            "logging": lambda: SetupLoggingView(self.cog, db, self.guild_id),
            "greetings": lambda: SetupGreetingsView(self.cog, db, self.guild_id),
            "reactions": lambda: SetupReactionsView(self.cog, db, self.guild_id),
            "reaction_roles": lambda: SetupReactionRolesView(self.cog, db, self.guild_id),
            "voice": lambda: SetupVoiceRoomsView(self.cog, db, self.guild_id),
            "roles": lambda: SetupRolesView(self.cog, db, self.guild_id),
            "channels": lambda: SetupChannelsView(self.cog, db, self.guild_id),
            "security": lambda: SetupSecurityView(self.cog, db, self.guild_id),
            "levels": lambda: SetupLevelsView(self.cog, db, self.guild_id),
            "automod": lambda: SetupAutomodView(self.cog, db, self.guild_id),
            "private": lambda: SetupPrivateCommandsView(self.cog, db, self.guild_id),
            "quests": lambda: SetupQuestsView(self.cog, db, self.guild_id),
            "shop": lambda: SetupShopView(self.cog, db, self.guild_id),
            "titles": lambda: SetupTitlesView(self.cog, db, self.guild_id),
            "moderation": lambda: SetupModerationView(self.cog, db, self.guild_id),
        }

        if val == "perms":
            cog = interaction.client.get_cog("Permissions")
            if cog:
                await cog._logic_perms_menu(interaction)
            else:
                await interaction.followup.send("❌ Модуль прав отключен.", ephemeral=True)
            return

        factory = view_map.get(val)
        if not factory:
            return

        try:
            view = factory()
            await interaction.response.edit_message(embed=None, view=view)
        except Exception as e:
            print(f"[Dashboard] menu_callback error ({val}): {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)
            except Exception:
                pass


# ==========================================
#   ОСНОВНЫЕ НАСТРОЙКИ
# ==========================================

class BoosterBoostModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Бустер XP-бонус")
        self.db = db
        self.guild_id = guild_id

        self.boost_input = discord.ui.TextInput(
            label="Процент буста (0-200)",
            placeholder="Например: 65 (означает +65% к XP)",
            required=True,
            max_length=5
        )
        self.add_item(self.boost_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            boost = int(self.boost_input.value)
            if not 0 <= boost <= 200:
                raise ValueError
        except ValueError:
            return await interaction.followup.send("❌ Введите число от 0 до 200!", ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "booster_xp_boost", boost / 100)
        await interaction.followup.send(f"✅ Бустер XP-бонус: **+{boost}%**", ephemeral=True)


class SetupAdminView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    async def _build_settings_info(self, interaction: discord.Interaction) -> discord.ui.LayoutView:
        config = await self.db.get_guild_config(str(self.guild_id))
        admin_roles = config.get("admin_roles", [])
        staff_roles = config.get("staff_roles", [])
        sys_ch = config.get("system_channel_id")
        modules = config.get("modules", {})
        boost = config.get("booster_xp_boost", 0)

        def role_list(ids):
            if not ids:
                return "Не заданы"
            parts = []
            for rid in ids[:10]:
                r = interaction.guild.get_role(int(rid))
                parts.append(r.mention if r else f"`{rid}`")
            return ", ".join(parts) + (f" +{len(ids)-10}" if len(ids) > 10 else "")

        mod_names = {"levels": "Уровни", "quests": "Квесты", "shop": "Магазин", "raids": "Рейды", "automod": "Автомод", "logging": "Логи"}
        enabled = [mod_names.get(m, m) for m, v in modules.items() if v]
        disabled = [mod_names.get(m, m) for m, v in modules.items() if not v]

        lines = [
            f"### Основные настройки",
            f"**Префикс:** `{config.get('prefix', '!')}`",
            f"**Админ-роли:** {role_list(admin_roles)}",
            f"**Роли персонала:** {role_list(staff_roles)}",
            f"**Системный канал:** {f'<#{sys_ch}>' if sys_ch else 'Не задан'}",
            f"**Бустер XP-бонус:** +{int(boost*100)}%",
            f"**Модули включены:** {', '.join(enabled) if enabled else 'никакие'}",
        ]
        if disabled:
            lines.append(f"**Модули выключены:** {', '.join(disabled)}")
        lines.append("\n*Выберите角色 или канал в меню ниже для изменения.*")

        embed = discord.Embed(title="⚙️ Текущие настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        return embed

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=4)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = await self._build_settings_info(interaction)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Роли администраторов", min_values=0, max_values=25, row=0)
    async def select_admin_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await interaction.response.defer(ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "admin_roles", [r.id for r in select.values])
        if select.values:
            await interaction.followup.send(f"✅ Роли администраторов: {', '.join([r.mention for r in select.values])}", ephemeral=True)
        else:
            await interaction.followup.send("✅ Роли администраторов очищены.", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Роли персонала", min_values=0, max_values=25, row=1)
    async def select_staff_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await interaction.response.defer(ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "staff_roles", [r.id for r in select.values])
        if select.values:
            await interaction.followup.send(f"✅ Роли персонала: {', '.join([r.mention for r in select.values])}", ephemeral=True)
        else:
            await interaction.followup.send("✅ Роли персонала очищены.", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Системный канал (уведомления бота)",
        max_values=1, row=2
    )
    async def select_system_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer(ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "system_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Системный канал: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Включить/выключить модули",
        min_values=0, max_values=6,
        options=[
            discord.SelectOption(label="Система уровней", value="levels", emoji="📊", description="Начисление XP и уровни"),
            discord.SelectOption(label="Квесты", value="quests", emoji="📜", description="Ежедневные квесты"),
            discord.SelectOption(label="Магазин", value="shop", emoji="🛒", description="Магазин товаров"),
            discord.SelectOption(label="Рейды", value="raids", emoji="⚔️", description="Организация рейдов"),
            discord.SelectOption(label="Авто-модерация", value="automod", emoji="🤖", description="Анти-спам и фильтры"),
            discord.SelectOption(label="Логирование", value="logging", emoji="📋", description="Логи действий"),
        ],
        row=3
    )
    async def select_modules(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(self.guild_id))
        modules = config.get("modules", {})
        all_modules = ["levels", "quests", "shop", "raids", "automod", "logging"]
        for m in all_modules:
            modules[m] = m in select.values
        await self.db.update_config_field(str(self.guild_id), "modules", modules)
        enabled = [e for e in select.values]
        disabled = [m for m in all_modules if m not in enabled]
        text = f"✅ Включены: {', '.join(enabled) if enabled else 'ничего'}"
        if disabled:
            text += f"\n❌ Выключены: {', '.join(disabled)}"
        await interaction.followup.send(text, ephemeral=True)

    @discord.ui.button(label="Бустер XP-бонус", emoji="⚡", style=discord.ButtonStyle.green, row=4)
    async def btn_booster_boost(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BoosterBoostModal(self.db, self.guild_id))

    @discord.ui.button(label="Статус бота", emoji="🟢", style=discord.ButtonStyle.blurple, row=4)
    async def btn_bot_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        status_type = config.get("bot_status_type", "playing")
        status_text = config.get("bot_status_text", "")
        modal = BotStatusModal(self.db, self.guild_id)
        modal.status_type.default = status_type
        modal.status_text.default = status_text
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Префикс сервера", emoji="📝", style=discord.ButtonStyle.green, row=4)
    async def btn_server_prefix(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        modal = PrefixModal(self.db, self.guild_id)
        modal.prefix_input.default = config.get("prefix", "!")
        await interaction.response.send_modal(modal)


class PrefixModal(discord.ui.Modal, title="Префикс сервера"):
    prefix_input = discord.ui.TextInput(
        label="Префикс команд",
        placeholder="Например: !",
        required=True,
        max_length=3,
    )

    def __init__(self, db, guild_id):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        prefix = self.prefix_input.value.strip()
        if not prefix:
            return await interaction.response.send_message("❌ Префикс не может быть пустым!", ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "prefix", prefix)
        await interaction.response.send_message(f"✅ Префикс сервера: `{prefix}`", ephemeral=True)


class BotStatusModal(discord.ui.Modal, title="Статус бота"):
    status_type = discord.ui.TextInput(
        label="Тип статуса",
        placeholder="playing, listening, watching, competing, streaming",
        required=True,
        max_length=20,
    )
    status_text = discord.ui.TextInput(
        label="Текст статуса",
        placeholder="Minecraft / @user / стрим / пусто = без статуса",
        required=False,
        max_length=128,
    )

    def __init__(self, db, guild_id):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        status_map = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing,
            "streaming": discord.ActivityType.streaming,
        }
        type_str = self.status_type.value.lower().strip()
        activity_type = status_map.get(type_str)
        if not activity_type:
            return await interaction.response.send_message(
                "❌ Допустимые типы: `playing`, `listening`, `watching`, `competing`, `streaming`", ephemeral=True
            )

        text = self.status_text.value.strip() if self.status_text.value else ""
        await self.db.update_config_field(str(self.guild_id), "bot_status_type", type_str)
        await self.db.update_config_field(str(self.guild_id), "bot_status_text", text)

        if text:
            if type_str == "streaming":
                activity = discord.Streaming(name=text, url="https://twitch.tv/")
            else:
                activity = discord.Activity(type=activity_type, name=text)
            await interaction.client.change_presence(activity=activity)
            await interaction.response.send_message(f"✅ Статус: **{type_str}** {text}", ephemeral=True)
        else:
            await interaction.client.change_presence(activity=None)
            await interaction.response.send_message("✅ Статус снят.", ephemeral=True)


# ==========================================
#   РЕЙДЫ
# ==========================================

class SetupRaidView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.ping_role = None
        self.line_channel = None
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=2)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        ping_role_id = config.get("raid_ping_role_id")
        line_ch_id = config.get("raid_line_channel_id")
        ping_role = interaction.guild.get_role(int(ping_role_id)) if ping_role_id else None

        lines = [
            f"### Рейды",
            f"**Роль для пинга:** {ping_role.mention if ping_role else 'Не задана'}",
            f"**Канал для лайнов:** {f'<#{line_ch_id}>' if line_ch_id else 'Не задан'}",
            "\n*Выберите роль и канал, затем нажмите «Сохранить».*",
        ]
        embed = discord.Embed(title="⚔️ Рейды — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="1. Роль для пинга", max_values=1, row=0)
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.ping_role = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="2. Канал для лайнов", max_values=1, row=1)
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.line_channel = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Сохранить", style=discord.ButtonStyle.success, row=2)
    async def save_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.ping_role or not self.line_channel:
            return await interaction.response.send_message("❌ Выберите и роль, и канал!", ephemeral=True)
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "raid_ping_role_id", self.ping_role.id)
        await self.db.update_config_field(str(self.guild_id), "raid_line_channel_id", self.line_channel.id)
        await interaction.followup.send("✅ Настройки рейдов сохранены!", ephemeral=True)


# ==========================================
#   ЛОГИРОВАНИЕ
# ==========================================

class ImportConfigModal(discord.ui.Modal, title="Импорт конфига"):
    config_json = discord.ui.TextInput(label="JSON конфиг", placeholder="Вставьте JSON...", required=True, style=discord.TextStyle.long, max_length=4000)

    def __init__(self, db, guild_id):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        import json
        try:
            config = json.loads(self.config_json.value)
        except json.JSONDecodeError as e:
            return await interaction.response.send_message(f"❌ Невалидный JSON: {e}", ephemeral=True)
        if not isinstance(config, dict):
            return await interaction.response.send_message("❌ JSON должен быть объектом.", ephemeral=True)
        await self.db.conn.execute('INSERT OR REPLACE INTO guild_config (guild_id, config) VALUES (?, ?)',
            (str(self.guild_id), json.dumps(config, ensure_ascii=False)))
        await self.db.conn.commit()
        await interaction.response.send_message("✅ Конфиг успешно импортирован!", ephemeral=True)


class SetupLoggingView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=2)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        log_ch = config.get("log_channel_id")
        log_events = config.get("log_events", {})
        event_names = {
            "msg_delete": "Удаление сообщений", "msg_edit": "Редактирование",
            "member_join": "Вход участника", "member_leave": "Выход участника",
            "nickname": "Никнейм",
            "role_add": "Выдача ролей", "role_remove": "Снятие ролей",
            "role_create": "Создание ролей", "role_delete": "Удаление ролей",
            "role_update": "Изменение ролей",
            "voice_connect": "Подключение (голос)", "voice_disconnect": "Отключение (голос)",
            "voice_move": "Перемещение (голос)", "voice_state": "Голос (мут/деаф)",
            "boost": "Буст", "channel_create": "Создание каналов",
            "channel_delete": "Удаление каналов", "thread": "Треды",
            "server_update": "Настройки сервера", "events": "Ивенты",
            "pun_ban": "Бан", "pun_unban": "Разбан", "pun_kick": "Кик",
            "pun_mute": "Мут", "pun_unmute": "Снятие мута",
            "pun_warn": "Варн", "pun_unwarn": "Снятие варна",
            "pun_blacklist": "Чёрный список", "pun_unblacklist": "Снятие с ЧС",
            "emoji_sticker": "Эмодзи/стикеры", "soundboard": "Саундборд",
            "commands": "Команды", "avatar": "Аватар/баннер", "pins": "Закрепление",
        }
        enabled = [event_names.get(k, k) for k, v in log_events.items() if v]
        disabled = [event_names.get(k, k) for k, v in log_events.items() if not v]

        lines = [
            f"### Логирование",
            f"**Канал:** {f'<#{log_ch}>' if log_ch else '❌ Не настроен'}",
            f"**Включено ({len(enabled)}):** {', '.join(enabled) if enabled else 'никакие'}",
        ]
        if disabled:
            lines.append(f"**Выключено ({len(disabled)}):** {', '.join(disabled)}")

        embed = discord.Embed(title="📋 Логи — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Канал для логов", max_values=1, row=0)
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "log_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал логов: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Что логировать?",
        min_values=0, max_values=32,
        options=[
            discord.SelectOption(label="Удаление сообщений", value="msg_delete", emoji="🗑️", description="Удалённые сообщения"),
            discord.SelectOption(label="Редактирование сообщений", value="msg_edit", emoji="✏️", description="Изменённые сообщения"),
            discord.SelectOption(label="Вход участника", value="member_join", emoji="🟢", description="Участник вошёл на сервер"),
            discord.SelectOption(label="Выход участника", value="member_leave", emoji="🔴", description="Участник вышел с сервера"),
            discord.SelectOption(label="Никнейм", value="nickname", emoji="📝", description="Смена никнейма"),
            discord.SelectOption(label="Выдача ролей", value="role_add", emoji="🟢", description="Участник получил роль"),
            discord.SelectOption(label="Снятие ролей", value="role_remove", emoji="🔴", description="Участник потерял роль"),
            discord.SelectOption(label="Создание ролей", value="role_create", emoji="➕", description="Создана новая роль"),
            discord.SelectOption(label="Удаление ролей", value="role_delete", emoji="➖", description="Роль удалена"),
            discord.SelectOption(label="Изменение ролей", value="role_update", emoji="📝", description="Имя, цвет, права роли"),
            discord.SelectOption(label="Подключение (голос)", value="voice_connect", emoji="🔊", description="Зашёл в голосовой"),
            discord.SelectOption(label="Отключение (голос)", value="voice_disconnect", emoji="🔇", description="Вышел из голосового"),
            discord.SelectOption(label="Перемещение (голос)", value="voice_move", emoji="➡️", description="Перемещён между каналами"),
            discord.SelectOption(label="Голос (мут/деаф)", value="voice_state", emoji="🎤", description="Изменение состояния"),
            discord.SelectOption(label="Буст", value="boost", emoji="💎", description="Начал/прекратил буст"),
            discord.SelectOption(label="Создание каналов", value="channel_create", emoji="📁", description="Новый канал"),
            discord.SelectOption(label="Удаление каналов", value="channel_delete", emoji="🗑️", description="Канал удалён"),
            discord.SelectOption(label="Треды", value="thread", emoji="🧵", description="Создание/удаление тредов"),
            discord.SelectOption(label="Настройки сервера", value="server_update", emoji="⚙️", description="Название, иконка, баннер..."),
            discord.SelectOption(label="Ивенты", value="events", emoji="📅", description="Scheduled events"),
            discord.SelectOption(label="Бан", value="pun_ban", emoji="🔨", description="Участник забанен"),
            discord.SelectOption(label="Разбан", value="pun_unban", emoji="✅", description="Участник разбанен"),
            discord.SelectOption(label="Кик", value="pun_kick", emoji="👢", description="Участник кикнут"),
            discord.SelectOption(label="Мут", value="pun_mute", emoji="🔇", description="Участник замьючен"),
            discord.SelectOption(label="Снятие мута", value="pun_unmute", emoji="🔊", description="Мут снят"),
            discord.SelectOption(label="Варн", value="pun_warn", emoji="⚠️", description="Выдано предупреждение"),
            discord.SelectOption(label="Снятие варна", value="pun_unwarn", emoji="🗑️", description="Предупреждение снято"),
            discord.SelectOption(label="Чёрный список", value="pun_blacklist", emoji="🚫", description="Участник внесён в ЧС"),
            discord.SelectOption(label="Снятие с ЧС", value="pun_unblacklist", emoji="♻️", description="Участник снят с ЧС"),
            discord.SelectOption(label="Эмодзи и стикеры", value="emoji_sticker", emoji="😀", description="Добавление/удаление/изменение"),
            discord.SelectOption(label="Саундборд", value="soundboard", emoji="🔊", description="Звуки саундборда"),
            discord.SelectOption(label="Команды", value="commands", emoji="💻", description="Использование slash-команд"),
            discord.SelectOption(label="Аватар/баннер", value="avatar", emoji="🖼️", description="Смена аватара или баннера"),
            discord.SelectOption(label="Закрепление", value="pins", emoji="📌", description="Закреп сообщений"),
        ],
        row=1
    )
    async def select_events(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        all_events = ["msg_delete", "msg_edit", "member_join", "member_leave", "nickname", "role_add", "role_remove", "role_create", "role_delete", "role_update", "voice_connect", "voice_disconnect", "voice_move", "voice_state", "boost", "channel_create", "channel_delete", "thread", "server_update", "events", "pun_ban", "pun_unban", "pun_kick", "pun_mute", "pun_unmute", "pun_warn", "pun_unwarn", "pun_blacklist", "pun_unblacklist", "emoji_sticker", "soundboard", "commands", "avatar", "pins"]
        log_events = {e: e in select.values for e in all_events}
        await self.db.update_config_field(str(self.guild_id), "log_events", log_events)
        enabled = [e for e in select.values]
        disabled = [e for e in all_events if e not in enabled]
        text = f"✅ Логируются: {', '.join(enabled) if enabled else 'ничего'}"
        if disabled:
            text += f"\n❌ Не логируются: {', '.join(disabled)}"
        await interaction.followup.send(text, ephemeral=True)

    @discord.ui.button(label="Тест лога", emoji="🧪", style=discord.ButtonStyle.green, row=2)
    async def btn_test_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        log_ch = config.get("log_channel_id")
        if not log_ch:
            return await interaction.response.send_message("❌ Сначала настройте канал логов.", ephemeral=True)
        channel = interaction.guild.get_channel(int(log_ch))
        if not channel:
            return await interaction.response.send_message("❌ Канал логов не найден.", ephemeral=True)
        embed = discord.Embed(title="🧪 Тест логирования", description="Если вы видите это сообщение — логи работают!\n\nЭто тестовый embed для проверки настройки лог-канала.", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.set_footer(text="Ayanami System")
        try:
            await channel.send(embed=embed)
            await interaction.response.send_message(f"✅ Тестовый лог отправлен в {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

    @discord.ui.button(label="Экспорт конфига", emoji="📥", style=discord.ButtonStyle.grey, row=2)
    async def btn_export_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        import json
        config = await self.db.get_guild_config(str(self.guild_id))
        if not config:
            return await interaction.response.send_message("❌ Конфиг пуст.", ephemeral=True)
        config_json = json.dumps(config, ensure_ascii=False, indent=2)
        if len(config_json) > 1900:
            import io
            file = discord.File(io.BytesIO(config_json.encode()), filename="config.json")
            await interaction.response.send_message("📥 Конфиг слишком большой, отправлен файлом:", file=file, ephemeral=True)
        else:
            await interaction.response.send_message(f"```json\n{config_json}\n```", ephemeral=True)

    @discord.ui.button(label="Импорт конфига", emoji="📤", style=discord.ButtonStyle.grey, row=2)
    async def btn_import_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ImportConfigModal(self.db, self.guild_id)
        await interaction.response.send_modal(modal)


# ==========================================
#   МОДЕРАЦИЯ (ВАРНЫ, АВТОДЕЙСТВИЯ, MOD LOG)
# ==========================================

class WarnLimitModal(discord.ui.Modal, title="Лимит варнов"):
    limit = discord.ui.TextInput(label="Лимит варнов (0 = отключено)", placeholder="Например: 3", required=True, max_length=3)
    action = discord.ui.TextInput(label="Действие: kick или ban", placeholder="kick", required=True, max_length=4)

    def __init__(self, cog, guild_id, db):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit_val = int(self.limit.value)
        except ValueError:
            return await interaction.response.send_message("❌ Лимит должен быть числом.", ephemeral=True)
        action_val = self.action.value.lower().strip()
        if action_val not in ("kick", "ban"):
            return await interaction.response.send_message("❌ Действие должно быть `kick` или `ban`.", ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "warn_limit", limit_val)
        await self.db.update_config_field(str(self.guild_id), "warn_action", action_val)
        await interaction.response.send_message(f"✅ Лимит варнов: **{limit_val}** → **{'кик' if action_val == 'kick' else 'бан'}**", ephemeral=True)


class ModLogChannelSelect(discord.ui.View):
    def __init__(self, cog, db, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Канал для логов модерации", channel_types=[discord.ChannelType.text], row=0)
    async def select_mod_log_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        channel = select.values[0]
        await self.db.update_config_field(str(self.guild_id), "mod_log_channel_id", str(channel.id))

    @discord.ui.button(label="Убрать канал мод.логов", style=discord.ButtonStyle.red, row=1)
    async def btn_remove_mod_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "mod_log_channel_id", None)


class SetupModerationView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id

    @discord.ui.button(label="Лимит варнов", emoji="⚠️", style=discord.ButtonStyle.blurple, row=0)
    async def btn_warn_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        limit = config.get("warn_limit", 0)
        action = config.get("warn_action", "kick")
        modal = WarnLimitModal(self.cog, self.guild_id, self.db)
        modal.limit.default = str(limit)
        modal.action.default = action
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Канал мод.логов", emoji="📋", style=discord.ButtonStyle.blurple, row=0)
    async def btn_mod_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        mod_ch = config.get("mod_log_channel_id")
        view = ModLogChannelSelect(self.cog, self.db, self.guild_id)
        await interaction.response.send_message(
            f"**Текущий канал мод.логов:** {f'<#{mod_ch}>' if mod_ch else '❌ Не настроен (используется общий лог)'}\n\nВыберите канал:",
            view=view, ephemeral=True
        )

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=1)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        warn_limit = config.get("warn_limit", 0)
        warn_action = config.get("warn_action", "kick")
        mod_log_ch = config.get("mod_log_channel_id")

        lines = [
            "### Модерация",
            f"**Лимит варнов:** {'Выключен' if warn_limit == 0 else f'{warn_limit} → **{warn_action}**'}",
            f"**Канал мод.логов:** {f'<#{mod_log_ch}>' if mod_log_ch else '❌ Не настроен (общий лог)'}",
        ]
        embed = discord.Embed(title="⚖️ Модерация — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Назад", emoji="⬅️", style=discord.ButtonStyle.grey, row=1)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = Database()
        config = await db.get_guild_config(str(self.guild_id))
        quests = await db.get_guild_quests(str(self.guild_id))
        shop_items = await db.get_shop_items(str(self.guild_id))
        view = DashboardView(self.cog, self.guild_id, config, len(quests), len(shop_items))
        await interaction.response.edit_message(view=view)


# ==========================================
#   РОЛИ (ЧС + ИММУНИТЕТ)
# ==========================================

class SetupRolesView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.blacklist_role = None
        self.immunity_role = None
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=2)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        bl_id = config.get("blacklist_role_id")
        im_id = config.get("immunity_role_id")
        bl_role = interaction.guild.get_role(int(bl_id)) if bl_id else None
        im_role = interaction.guild.get_role(int(im_id)) if im_id else None

        lines = [
            f"### Роли",
            f"**Чёрный список:** {bl_role.mention if bl_role else 'Не задана'}",
            f"**Иммунитет:** {im_role.mention if im_role else 'Не задана'}",
            "\n*Выберите роли в меню ниже. Участники с ролью иммунитета защищены от наказаний.*",
        ]
        embed = discord.Embed(title="🛡️ Роли — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="1. Роль Чёрного списка", max_values=1, row=0)
    async def select_blacklist(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.blacklist_role = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="2. Роль иммунитета", max_values=1, row=1)
    async def select_immunity(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.immunity_role = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Сохранить", style=discord.ButtonStyle.success, row=2)
    async def save_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.blacklist_role and not self.immunity_role:
            return await interaction.response.send_message("❌ Выберите хотя бы одну роль!", ephemeral=True)
        await interaction.response.defer()
        if self.blacklist_role:
            await self.db.update_config_field(str(self.guild_id), "blacklist_role_id", self.blacklist_role.id)
        if self.immunity_role:
            await self.db.update_config_field(str(self.guild_id), "immunity_role_id", self.immunity_role.id)
        await interaction.followup.send("✅ Роли сохранены!", ephemeral=True)


# ==========================================
#   ПРИВЕТСТВИЯ / ПРОЩАНИЯ / БУСТЫ
# ==========================================

class SetupGreetingsView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=4)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        welcome = '🟢' if config.get('welcome_enabled') else '🔴'
        leave = '🟢' if config.get('leave_enabled') else '🔴'
        boost = '🟢' if config.get('boost_enabled') else '🔴'
        autorole = '🟢' if config.get('autorole_enabled') else '🔴'
        w_ch = config.get("welcome_channel_id")
        l_ch = config.get("leave_channel_id")
        b_ch = config.get("boost_channel_id")
        ar_roles = config.get("autorole_roles", [])

        def ch(id):
            return f"<#{id}>" if id else "Не задан"

        ar_text = ", ".join([interaction.guild.get_role(int(r)).mention if interaction.guild.get_role(int(r)) else str(r) for r in ar_roles[:5]]) if ar_roles else "Не заданы"

        lines = [
            f"### Приветствия",
            f"{welcome} **Приветствия:** {ch(w_ch)}",
            f"{leave} **Прощания:** {ch(l_ch)}",
            f"{boost} **Бусты:** {ch(b_ch)}",
            f"{autorole} **Автороли:** {ar_text}",
            "\n*Используйте кнопки ниже для настройки текста и баннеров. Переменные: {user}, {server}, {username}*",
        ]
        embed = discord.Embed(title="👋 Приветствия — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Канал приветствий", max_values=1, row=0)
    async def select_welcome(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "welcome_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал приветствий: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Канал для сообщений прощания", max_values=1, row=1)
    async def select_leave(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "leave_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал прощаний: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Канал для уведомлений о бустах", max_values=1, row=2)
    async def select_boost(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "boost_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал бустов: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Включить/выключить",
        min_values=0, max_values=4,
        options=[
            discord.SelectOption(label="Приветствия", value="welcome", emoji="👋", description="Отправлять приветственные сообщения при входе"),
            discord.SelectOption(label="Прощания", value="leave", emoji="👋", description="Отправлять прощальные сообщения при выходе"),
            discord.SelectOption(label="Бусты", value="boost", emoji="💎", description="Отправлять уведомления о бустах сервера"),
            discord.SelectOption(label="Автороли", value="autorole", emoji="🔰", description="Выдавать роли автоматически при входе"),
        ],
        row=3
    )
    async def select_toggles(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "welcome_enabled", "welcome" in select.values)
        await self.db.update_config_field(str(self.guild_id), "leave_enabled", "leave" in select.values)
        await self.db.update_config_field(str(self.guild_id), "boost_enabled", "boost" in select.values)
        await self.db.update_config_field(str(self.guild_id), "autorole_enabled", "autorole" in select.values)
        enabled = [e for e in select.values]
        disabled = ["welcome", "leave", "boost", "autorole"]
        for v in enabled:
            if v in disabled:
                disabled.remove(v)
        text = f"✅ Включены: {', '.join(enabled) if enabled else 'ничего'}"
        if disabled:
            text += f"\n❌ Выключены: {', '.join(disabled)}"
        await interaction.followup.send(text, ephemeral=True)

    @discord.ui.button(label="Настроить автороли", emoji="🔰", style=discord.ButtonStyle.secondary, row=4)
    async def btn_autoroles(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SetupAutorolesView(self.cog, self.db, self.guild_id)
        await interaction.response.edit_message(embed=None, view=view)

    @discord.ui.button(label="Настроить текст", style=discord.ButtonStyle.blurple, row=4)
    async def btn_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SetupGreetingsMessagesView(self.cog, self.db, self.guild_id)
        await interaction.response.edit_message(embed=None, view=view)

    @discord.ui.button(label="Тест приветствия", emoji="🧪", style=discord.ButtonStyle.green, row=4)
    async def btn_test_greeting(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        welcome_ch = config.get("welcome_channel_id")
        if not welcome_ch:
            return await interaction.response.send_message("❌ Сначала настройте канал приветствий.", ephemeral=True)
        channel = interaction.guild.get_channel(int(welcome_ch))
        if not channel:
            return await interaction.response.send_message("❌ Канал приветствий не найден.", ephemeral=True)
        template = config.get("welcome_message", "Добро пожаловать, {user}!")
        banner = config.get("welcome_banner")
        text = template.replace("{user}", interaction.user.mention).replace("{username}", interaction.user.name).replace("{server}", interaction.guild.name).replace("{server_count}", str(interaction.guild.member_count))
        embed = discord.Embed(description=text, color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        if banner:
            embed.set_image(url=banner)
        embed.set_footer(text="Ayanami System | Тест приветствия")
        try:
            await channel.send(embed=embed)
            await interaction.response.send_message(f"✅ Тестовое приветствие отправлено в {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)


class SetupAutorolesView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Роли для автовыдачи (при входе)", min_values=1, max_values=10, row=0)
    async def select_autoroles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "autorole_roles", [r.id for r in select.values])
        await interaction.followup.send(f"✅ Автороли: {', '.join([r.mention for r in select.values])}", ephemeral=True)


class SetupGreetingsMessagesView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Настроить приветствие", style=discord.ButtonStyle.green, row=0)
    async def btn_welcome(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GreetingMessageModal(
                self.db, self.guild_id,
                key="welcome_message",
                title="Текст приветствия",
                placeholder="Привет {user}, добро пожаловать на {server}!"
            )
        )

    @discord.ui.button(label="Настроить прощание", style=discord.ButtonStyle.red, row=0)
    async def btn_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GreetingMessageModal(
                self.db, self.guild_id,
                key="leave_message",
                title="Текст прощания",
                placeholder="{username} покинул {server}. Пока!"
            )
        )

    @discord.ui.button(label="Настроить буст", style=discord.ButtonStyle.blurple, row=0)
    async def btn_boost(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GreetingMessageModal(
                self.db, self.guild_id,
                key="boost_message",
                title="Текст буста",
                placeholder="Спасибо {user} за буст сервера {server}!"
            )
        )

    @discord.ui.button(label="Баннер приветствия", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_welcome_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GreetingBannerModal(self.db, self.guild_id, key="welcome_banner", title="Баннер приветствия")
        )

    @discord.ui.button(label="Баннер прощания", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_leave_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GreetingBannerModal(self.db, self.guild_id, key="leave_banner", title="Баннер прощания")
        )

    @discord.ui.button(label="Баннер буста", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_boost_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GreetingBannerModal(self.db, self.guild_id, key="boost_banner", title="Баннер буста")
        )

    @discord.ui.button(label="Убрать баннеры", emoji="🗑️", style=discord.ButtonStyle.danger, row=2)
    async def btn_clear_banners(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "welcome_banner", "")
        await self.db.update_config_field(str(self.guild_id), "leave_banner", "")
        await self.db.update_config_field(str(self.guild_id), "boost_banner", "")
        await interaction.followup.send("✅ Все баннеры удалены!", ephemeral=True)

    @discord.ui.button(label="Примеры переменных", style=discord.ButtonStyle.grey, row=3)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        help_text = (
            "**Доступные переменные:**\n"
            "`{user}` — упоминание участника\n"
            "`{username}` — имя участника\n"
            "`{user_id}` — ID участника\n"
            "`{nickname}` — никнейм участника\n"
            "`{server}` — название сервера\n"
            "`{server_id}` — ID сервера\n"
            "`{server_count}` — количество участников\n"
            "`{boost_count}` — количество бустов сервера\n"
            "`{role_count}` — количество ролей участника\n"
            "`{top_role}` — главная роль участника\n"
            "`{created_at}` — когда создан аккаунт\n"
            "`{joined_at}` — когда вошёл на сервер\n"
            "`{boost}` — инфо о бусте\n"
            "`{boost_since}` — когда начал бустить\n\n"
            "**Пример:** `Привет {user}, добро пожаловать на {server}! У нас уже {server_count} человек и {boost_count} бустов!`"
        )
        await interaction.response.send_message(help_text, ephemeral=True)


class GreetingMessageModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int, key: str, title: str, placeholder: str):
        super().__init__(title=title)
        self.db = db
        self.guild_id = guild_id
        self.key = key

        self.input = discord.ui.TextInput(
            label="Текст сообщения",
            style=discord.TextStyle.paragraph,
            placeholder=placeholder,
            required=False,
            max_length=500
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), self.key, self.input.value)
        await interaction.followup.send("✅ Текст сохранён!", ephemeral=True)


class GreetingBannerModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int, key: str, title: str):
        super().__init__(title=title)
        self.db = db
        self.guild_id = guild_id
        self.key = key

        self.url_input = discord.ui.TextInput(
            label="URL изображения (баннера)",
            style=discord.TextStyle.short,
            placeholder="https://example.com/image.png",
            required=True,
            max_length=500
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        url = self.url_input.value.strip()
        if not url.startswith(("http://", "https://")):
            return await interaction.followup.send("❌ URL должен начинаться с `http://` или `https://`", ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), self.key, url)
        await interaction.followup.send("✅ Баннер сохранён!", ephemeral=True)


# ==========================================
#   РЕАКЦИИ
# ==========================================

class ReactionAddModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Добавить реакцию")
        self.db = db
        self.guild_id = guild_id

        self.trigger_input = discord.ui.TextInput(
            label="Слово-триггер",
            placeholder="Например: спс, привет, лол",
            required=True,
            max_length=50
        )
        self.emoji_input = discord.ui.TextInput(
            label="Эмодзи (через запятую или пробел)",
            placeholder="Например: ❤️ 🔥 👍 или <:name:123>",
            required=True,
            max_length=200
        )
        self.add_item(self.trigger_input)
        self.add_item(self.emoji_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        trigger = self.trigger_input.value.lower().strip()

        raw_input = self.emoji_input.value.strip()
        raw_emojis = [e.strip() for e in raw_input.replace(";", ",").replace(" ", ",").split(",") if e.strip()]

        if not raw_emojis:
            return await interaction.followup.send("❌ Укажите хотя бы один эмодзи!", ephemeral=True)

        valid_emojis = []
        invalid_emojis = []
        for emoji_str in raw_emojis:
            is_custom = emoji_str.startswith("<:") or emoji_str.startswith("<a:")
            if is_custom:
                partial = discord.PartialEmoji.from_str(emoji_str)
                if partial.id:
                    valid_emojis.append(emoji_str)
                else:
                    invalid_emojis.append(emoji_str)
            elif emoji_str.startswith(":") and emoji_str.endswith(":"):
                invalid_emojis.append(emoji_str)
            else:
                valid_emojis.append(emoji_str)

        if invalid_emojis:
            return await interaction.followup.send(
                f"❌ Не удалось распознать эмодзи: {', '.join(invalid_emojis)}\n\n"
                "Используйте:\n"
                "• Юникод-эмодзи: ❤️🔥👍⑥⑦\n"
                "• Кастомные: перетащите эмодзи из сервера (получите `<:name:id>`)\n\n"
                "⚠️ `:six:` — это не эмодзи! Используйте真正的 эмодзи.",
                ephemeral=True
            )

        config = await self.db.get_guild_config(str(self.guild_id))
        reactions = config.get("reactions", {})
        existing = reactions.get(trigger, [])
        if isinstance(existing, str):
            existing = [existing]

        merged = list(dict.fromkeys(existing + valid_emojis))
        reactions[trigger] = merged
        await self.db.update_config_field(str(self.guild_id), "reactions", reactions)
        emojis_text = " ".join(merged)
        await interaction.followup.send(f"✅ На **{trigger}** реагирует: {emojis_text}", ephemeral=True)


class ReactionRemoveModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Удалить реакцию")
        self.db = db
        self.guild_id = guild_id

        self.trigger_input = discord.ui.TextInput(
            label="Слово-триггер для удаления",
            placeholder="Например: спс",
            required=True,
            max_length=50
        )
        self.add_item(self.trigger_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        trigger = self.trigger_input.value.lower().strip()

        config = await self.db.get_guild_config(str(self.guild_id))
        reactions = config.get("reactions", {})

        if trigger not in reactions:
            return await interaction.followup.send(f"❌ Реакция на **{trigger}** не найдена!", ephemeral=True)

        del reactions[trigger]
        await self.db.update_config_field(str(self.guild_id), "reactions", reactions)
        await interaction.followup.send(f"✅ Реакция на **{trigger}** удалена!", ephemeral=True)


class SetupReactionsView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Справка", emoji="❓", style=discord.ButtonStyle.grey, row=1)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        reactions = config.get("reactions", {})
        lines = [
            f"### Реакции — справка",
            f"**Кастомных реакций:** {len(reactions)}",
            "",
            "**Как использовать:**",
            "➕ **Добавить реакцию** — введите слово-триггер и эмодзи через запятую",
            "🗑️ **Удалить реакцию** — введите слово-триггер для удаления",
            "📋 **Список реакций** — посмотреть все триггеры",
            "",
            "*Бот будет автоматически реагировать эмодзи на сообщения containing триггер.*",
        ]
        embed = discord.Embed(title="🎭 Реакции — справка", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Добавить реакцию", style=discord.ButtonStyle.success, row=0)
    async def btn_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReactionAddModal(self.db, self.guild_id))

    @discord.ui.button(label="Удалить реакцию", style=discord.ButtonStyle.danger, row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReactionRemoveModal(self.db, self.guild_id))

    @discord.ui.button(label="Список реакций", style=discord.ButtonStyle.grey, row=1)
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        custom = config.get("reactions", {})

        if not custom:
            return await interaction.response.send_message("📋 Кастомных реакций нет.", ephemeral=True)

        lines = []
        for trigger, emojis in custom.items():
            emoji_list = emojis if isinstance(emojis, list) else [emojis]
            lines.append(f"`{trigger}` → {' '.join(emoji_list)}")

        embed = discord.Embed(
            title="🎭 Кастомные реакции",
            description="\n".join(lines[:30]),
            color=discord.Color(0x9b59b6),
        )
        embed.set_footer(text=f"Всего: {len(custom)} | Управление через /setup → Реакции")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
#   REACTION ROLES
# ==========================================

class ReactionRoleAddModal(discord.ui.Modal, title="Добавить Reaction Role"):
    message_id = discord.ui.TextInput(label="ID сообщения", placeholder="1234567890", required=True, max_length=20)
    channel_id = discord.ui.TextInput(label="ID канала", placeholder="1234567890", required=True, max_length=20)
    emoji = discord.ui.TextInput(label="Эмодзи", placeholder="❤️ или <:name:id>", required=True, max_length=50)
    role_id = discord.ui.TextInput(label="ID роли", placeholder="1234567890", required=True, max_length=20)

    def __init__(self, db, guild_id):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        import re
        try:
            msg_id = int(self.message_id.value)
            ch_id = int(self.channel_id.value)
            r_id = int(self.role_id.value)
        except ValueError:
            return await interaction.response.send_message("❌ ID должны быть числами.", ephemeral=True)

        channel = interaction.guild.get_channel(ch_id)
        if not channel:
            return await interaction.response.send_message("❌ Канал не найден.", ephemeral=True)
        try:
            message = await channel.fetch_message(msg_id)
        except Exception:
            return await interaction.response.send_message("❌ Сообщение не найдено.", ephemeral=True)
        role = interaction.guild.get_role(r_id)
        if not role:
            return await interaction.response.send_message("❌ Роль не найдена.", ephemeral=True)

        emoji_str = self.emoji.value.strip()
        config = await self.db.get_guild_config(str(self.guild_id))
        reaction_roles = config.get("reaction_roles", {})
        key = f"{ch_id}:{msg_id}"
        if key not in reaction_roles:
            reaction_roles[key] = {}
        reaction_roles[key][emoji_str] = str(r_id)
        await self.db.update_config_field(str(self.guild_id), "reaction_roles", reaction_roles)

        try:
            await message.add_reaction(emoji_str)
        except Exception:
            pass

        await interaction.response.send_message(
            f"✅ Reaction role: {emoji_str} → {role.mention} на [сообщении]({message.jump_url})",
            ephemeral=True
        )


class ReactionRoleRemoveModal(discord.ui.Modal, title="Удалить Reaction Role"):
    message_id = discord.ui.TextInput(label="ID сообщения", placeholder="1234567890", required=True, max_length=20)
    channel_id = discord.ui.TextInput(label="ID канала", placeholder="1234567890", required=True, max_length=20)
    emoji = discord.ui.TextInput(label="Эмодзи для удаления", placeholder="❤️ или <:name:id>", required=True, max_length=50)

    def __init__(self, db, guild_id):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            msg_id = int(self.message_id.value)
            ch_id = int(self.channel_id.value)
        except ValueError:
            return await interaction.response.send_message("❌ ID должны быть числами.", ephemeral=True)

        config = await self.db.get_guild_config(str(self.guild_id))
        reaction_roles = config.get("reaction_roles", {})
        key = f"{ch_id}:{msg_id}"
        emoji_str = self.emoji.value.strip()

        if key in reaction_roles and emoji_str in reaction_roles[key]:
            del reaction_roles[key][emoji_str]
            if not reaction_roles[key]:
                del reaction_roles[key]
            await self.db.update_config_field(str(self.guild_id), "reaction_roles", reaction_roles)
            await interaction.response.send_message(f"✅ Reaction role {emoji_str} удалён.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Reaction role не найден.", ephemeral=True)


class SetupReactionRolesView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Справка", emoji="❓", style=discord.ButtonStyle.grey, row=1)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        rr = config.get("reaction_roles", {})
        total = sum(len(v) for v in rr.values())
        lines = [
            f"### Reaction Roles — справка",
            f"**Привязок:** {total} в {len(rr)} сообщениях",
            "",
            "**Как использовать:**",
            "➕ **Добавить** — укажите ID сообщения, канала, эмодзи и роли",
            "🗑️ **Удалить** — укажите ID сообщения, канала и эмодзи",
            "📋 **Список** — все текущие привязки",
            "",
            "*Бот выдаёт/снимает роль когда участник ставит/убирает реакцию.*",
        ]
        embed = discord.Embed(title="🎭 Reaction Roles — справка", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Добавить", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def btn_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReactionRoleAddModal(self.db, self.guild_id))

    @discord.ui.button(label="Удалить", emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReactionRoleRemoveModal(self.db, self.guild_id))

    @discord.ui.button(label="Список", emoji="📋", style=discord.ButtonStyle.grey, row=1)
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        rr = config.get("reaction_roles", {})
        if not rr:
            return await interaction.response.send_message("📋 Reaction roles не настроены.", ephemeral=True)

        lines = []
        for key, mapping in rr.items():
            ch_id, msg_id = key.split(":")
            for emoji, role_id in mapping.items():
                lines.append(f"{emoji} → <@&{role_id}> | [Сообщение](https://discord.com/channels/{self.guild_id}/{ch_id}/{msg_id})")

        embed = discord.Embed(
            title="🎭 Reaction Roles",
            description="\n".join(lines[:30]),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Всего: {sum(len(v) for v in rr.values())} привязок")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
#   КАНАЛЫ И РОЛИ (доп. настройки)
# ==========================================

class SetupChannelsView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=4)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        def ch(id):
            return f"<#{id}>" if id else "Не задан"

        staff_roles = config.get("staff_roles", [])
        sr_text = ", ".join([interaction.guild.get_role(int(r)).mention if interaction.guild.get_role(int(r)) else str(r) for r in staff_roles[:5]]) if staff_roles else "Не заданы"

        lines = [
            f"### Каналы и Роли",
            f"**Жалобы:** {ch(config.get('report_channel_id'))}",
            f"**Лог повышений:** {ch(config.get('promote_log_channel_id'))}",
            f"**Лог понижений:** {ch(config.get('demote_log_channel_id'))}",
            f"**Роли персонала (promote/demote):** {sr_text}",
            "\n*Команды `/promote` и `/demote` отправляют эмбеды в лог-каналы.*",
        ]
        embed = discord.Embed(title="📢 Каналы — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Канал для жалоб", max_values=1, row=0)
    async def select_report(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "report_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал жалоб: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Канал логов повышений", max_values=1, row=1)
    async def select_promote_log(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "promote_log_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал логов повышений: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Канал логов понижений", max_values=1, row=2)
    async def select_demote_log(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "demote_log_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал логов понижений: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Роли персонала (для promote/demote)", min_values=1, max_values=10, row=3)
    async def select_staff_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await interaction.response.defer()
        await self.db.update_config_field(str(self.guild_id), "staff_roles", [r.id for r in select.values])
        await interaction.followup.send(f"✅ Роли персонала сохранены!", ephemeral=True)


# ==========================================
#   ПРИВАТНЫЕ ГОЛОСОВЫЕ
# ==========================================

class SetupVoiceRoomsView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=4)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        vr = config.get("voice_rooms", {})
        room_type = vr.get("room_type", "personal")
        type_names = {"personal": "👤 Личная", "duo": "👥 Дуэт", "group": "👨‍👩‍👧‍👦 Группа", "team": "🏠 Команда"}
        trigger = vr.get("trigger_channel_id")
        category = vr.get("category_id")
        panel = vr.get("panel_channel_id")

        def ch(id):
            return f"<#{id}>" if id else "Не задан"

        lines = [
            f"### Приватные голосовые",
            f"**Тип комнаты:** {type_names.get(room_type, room_type)}",
            f"**Триггер-канал:** {ch(trigger)}",
            f"**Категория:** {ch(category)}",
            f"**Канал панелей:** {ch(panel)}",
            "\n*Зайдите в триггер-канал, чтобы создать приватную комнату. Владелец может закрывать, переименовывать и управлять доступом.*",
        ]
        embed = discord.Embed(title="🔊 Приватные голосовые — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Тип приватной комнаты",
        min_values=1, max_values=1,
        options=[
            discord.SelectOption(label="Личная комната", value="personal", emoji="👤", description="Личная комната для одного человека"),
            discord.SelectOption(label="Дуэт", value="duo", emoji="👥", description="Комната для двоих на 2 человек"),
            discord.SelectOption(label="Группа", value="group", emoji="👨‍👩‍👧‍👦", description="Групповая комната на 5 человек"),
            discord.SelectOption(label="Команда", value="team", emoji="🏠", description="Командная комната на 10 человек"),
        ],
        row=0
    )
    async def select_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        vr = config.get("voice_rooms", {})
        vr["room_type"] = select.values[0]
        await self.db.update_config_field(str(self.guild_id), "voice_rooms", vr)
        type_names = {"personal": "👤 Личная", "duo": "👥 Дуэт", "group": "👨‍👩‍👧‍👦 Группа", "team": "🏠 Команда"}
        await interaction.followup.send(f"✅ Тип: **{type_names.get(select.values[0], select.values[0])}**", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.voice], placeholder="Триггер-канал (сюда заходить)", max_values=1, row=1)
    async def select_trigger(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        vr = config.get("voice_rooms", {})
        vr["trigger_channel_id"] = select.values[0].id
        await self.db.update_config_field(str(self.guild_id), "voice_rooms", vr)
        await interaction.followup.send(f"✅ Триггер: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.category], placeholder="Категория для приваток", max_values=1, row=2)
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        vr = config.get("voice_rooms", {})
        vr["category_id"] = select.values[0].id
        await self.db.update_config_field(str(self.guild_id), "voice_rooms", vr)
        await interaction.followup.send(f"✅ Категория: **{select.values[0].name}**", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Текстовый канал для панелей (опционально)", max_values=1, row=3)
    async def select_panel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        vr = config.get("voice_rooms", {})
        vr["panel_channel_id"] = select.values[0].id
        await self.db.update_config_field(str(self.guild_id), "voice_rooms", vr)
        await interaction.followup.send(f"✅ Панели будут в: {select.values[0].mention}", ephemeral=True)

    @discord.ui.button(label="Отправить панель", emoji="📤", style=discord.ButtonStyle.blurple, row=4)
    async def btn_send_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(self.guild_id))
        vr = config.get("voice_rooms", {})
        panel_ch_id = vr.get("panel_channel_id")
        if not panel_ch_id:
            return await interaction.followup.send("❌ Сначала выберите текстовый канал для панелей!", ephemeral=True)
        panel_channel = interaction.guild.get_channel(int(panel_ch_id))
        if not panel_channel:
            return await interaction.followup.send("❌ Канал не найден!", ephemeral=True)
        vr_cog = interaction.client.get_cog("VoiceRooms")
        if not vr_cog:
            return await interaction.followup.send("❌ Модуль голосовых не загружен!", ephemeral=True)
        trigger_ch = vr.get('trigger_channel_id', 0)
        room_type = vr.get('room_type', 'personal')
        type_info = {
            "personal": {"emoji": "👤", "name": "Личная", "limit": 1, "desc": "Для уединённого общения"},
            "duo": {"emoji": "👥", "name": "Дуэт", "limit": 2, "desc": "Для тихого разговора вдвоём"},
            "group": {"emoji": "👨‍👩‍👧‍👦", "name": "Группа", "limit": 5, "desc": "Для дружеской компании"},
            "team": {"emoji": "🏠", "name": "Команда", "limit": 10, "desc": "Для командных игр и стримов"}
        }
        current = type_info.get(room_type, type_info["personal"])

        types_text = ""
        for key, info in type_info.items():
            marker = " ◀️" if key == room_type else ""
            limit_word = "участник" if info["limit"] == 1 else "участника" if info["limit"] < 5 else "участников"
            types_text += f"{info['emoji']} **{info['name']}** — до {info['limit']} {limit_word}\n     {info['desc']}{marker}\n"

        description = (
            f"Зайдите в <#{trigger_ch}>, чтобы создать **приватную голосовую комнату**.\n\n"
            f"**Текущий тип:** {current['emoji']} {current['name']}\n"
        )
        fields = [
            ("Доступные типы комнат", types_text),
            ("⚙️ Возможности владельца", (
                "🔒 Закрыть / 🔓 Открыть комнату\n"
                "🔢 Изменить лимит участников\n"
                "✏️ Переименовать комнату\n"
                "👢 Выгнать участника\n"
                "🗑️ Удалить комнату"
            )),
        ]
        embed = discord.Embed(
            title="🔊 Приватные голосовые комнаты",
            description=description,
            color=discord.Color(0x2b2d31),
        )
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text="Ayanami System")

        try:
            await panel_channel.send(embed=embed)
            await interaction.followup.send(f"✅ Панель отправлена в {panel_channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)


# ==========================================
#   БЕЗОПАСНОСТЬ (Anti-Nuke)
# ==========================================

class SetupSecurityView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=3)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        sec = config.get("security", {})
        enabled = "🟢 Вкл" if sec.get("enabled", True) else "🔴 Выкл"
        punishment = sec.get("punishment", "ban")
        p_names = {"ban": "Бан", "kick": "Кик", "strip": "Снятие ролей"}
        warn_limit = sec.get("warn_limit", 3)
        expiry = sec.get("warn_expiry_hours", 24)

        lines = [
            f"### Безопасность (Anti-Nuke)",
            f"**Статус:** {enabled}",
            f"**Наказание:** {p_names.get(punishment, punishment)}",
            f"**Порог варнов:** {warn_limit}",
            f"**Срок варнов:** {expiry}ч",
            "\n*При превышении порога варнов участник автоматически наказывается.*",
        ]
        embed = discord.Embed(title="🚨 Безопасность — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Мера наказания для участника",
        options=[
            discord.SelectOption(label="Бан", value="ban", emoji="🔨", description="Полный бан участника за нарушения"),
            discord.SelectOption(label="Кик", value="kick", emoji="👢", description="Исключение участника с сервера"),
            discord.SelectOption(label="Снятие ролей", value="strip", emoji="🛡️", description="Снятие всех ролей у участника"),
        ],
        row=0
    )
    async def select_punishment(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        sec = config.get("security", {})
        sec["punishment"] = select.values[0]
        await self.db.update_config_field(str(self.guild_id), "security", sec)
        await interaction.followup.send(f"✅ Наказание: **{select.values[0]}**", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Порог срабатывания",
        options=[
            discord.SelectOption(label="Строгий: 2 варна → наказание", value="strict", emoji="🔴", description="Минимальный порог для строгой модерации"),
            discord.SelectOption(label="Норма: 3 варна → наказание", value="normal", emoji="🟡", description="Стандартный порог для обычной модерации"),
            discord.SelectOption(label="Мягкий: 5 варнов → наказание", value="soft", emoji="🟢", description="Максимальный порог для мягкой модерации"),
        ],
        row=1
    )
    async def select_thresholds(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        sec = config.get("security", {})
        val = select.values[0]
        if val == "strict":
            sec["warn_limit"] = 2
            sec["ban_limit"] = 2
            sec["kick_limit"] = 2
            sec["channel_delete_limit"] = 1
        elif val == "soft":
            sec["warn_limit"] = 5
            sec["ban_limit"] = 5
            sec["kick_limit"] = 5
            sec["channel_delete_limit"] = 3
        else:
            sec["warn_limit"] = 3
            sec["ban_limit"] = 3
            sec["kick_limit"] = 3
            sec["channel_delete_limit"] = 2
        await self.db.update_config_field(str(self.guild_id), "security", sec)
        await interaction.followup.send(f"✅ Порог: **{val}**", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Срок действия варнов",
        options=[
            discord.SelectOption(label="1 час", value="1", description="Варны истекают через 1 час"),
            discord.SelectOption(label="6 часов", value="6", description="Варны истекают через 6 часов"),
            discord.SelectOption(label="24 часа", value="24", description="Варны истекают через 24 часа"),
            discord.SelectOption(label="3 дня", value="72", description="Варны истекают через 3 дня"),
            discord.SelectOption(label="7 дней", value="168", description="Варны истекают через 7 дней"),
        ],
        row=2
    )
    async def select_expiry(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        sec = config.get("security", {})
        sec["warn_expiry_hours"] = int(select.values[0])
        await self.db.update_config_field(str(self.guild_id), "security", sec)
        await interaction.followup.send(f"✅ Варны истекают через: **{select.values[0]}ч**", ephemeral=True)

    @discord.ui.button(label="Вкл/Выкл Anti-Nuke", style=discord.ButtonStyle.danger, row=3)
    async def toggle_security(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        sec = config.get("security", {})
        sec["enabled"] = not sec.get("enabled", True)
        await self.db.update_config_field(str(self.guild_id), "security", sec)
        status = "включена ✅" if sec["enabled"] else "выключена ❌"
        await interaction.followup.send(f"Anti-Nuke защита **{status}**", ephemeral=True)


# ==========================================
#   ПРИВАТНЫЕ КОМАНДЫ
# ==========================================

class SetupPrivateCommandsView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.selected_commands = []
        self.add_item(BackButton())

        self.all_cmds = []
        for cmd in cog.bot.tree.walk_commands():
            if isinstance(cmd, app_commands.Command) and cmd.name not in ["setup", "help"]:
                self.all_cmds.append(cmd.qualified_name)
        self.all_cmds.sort()

        self.select_commands.options = [
            discord.SelectOption(label=c, value=c, description=f"Настроить доступ к команде {c}") for c in self.all_cmds[:25]
        ]

    @discord.ui.button(label="Справка", emoji="❓", style=discord.ButtonStyle.grey, row=2)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        private = config.get("private_commands", {})
        hidden_count = len(private)

        lines = [
            f"### Приватные команды — справка",
            f"**Скрыто команд:** {hidden_count}",
            "",
            "**Как использовать:**",
            "1. Выберите команды в верхнем меню",
            "2. Выберите роли, которые МОГУТ видеть эти команды",
            "3. Нажмите **Сделать публичными** чтобы убрать ограничение",
            "",
            "*Участники без указанных ролей не увидят команду в меню.*",
        ]
        embed = discord.Embed(title="🔐 Приватные команды — справка", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Выберите команды (макс. 25)",
        min_values=1, max_values=25,
        options=[],
        row=0
    )
    async def select_commands(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_commands = select.values
        await interaction.response.defer()

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Роли, которые МОГУТ видеть эти команды",
        min_values=1, max_values=5,
        row=1
    )
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        if not self.selected_commands:
            return await interaction.response.send_message("❌ Сначала выберите команды выше!", ephemeral=True)

        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        private = config.get("private_commands", {})

        role_ids = [str(r.id) for r in select.values]
        for cmd in self.selected_commands:
            private[cmd] = role_ids

        await self.db.update_config_field(str(self.guild_id), "private_commands", private)
        await interaction.followup.send(
            f"✅ Команды `{', '.join(self.selected_commands[:5])}` теперь видны только для: {', '.join([r.mention for r in select.values])}",
            ephemeral=True
        )

    @discord.ui.button(label="Сделать публичными", style=discord.ButtonStyle.danger, row=2)
    async def make_public(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_commands:
            return await interaction.response.send_message("❌ Сначала выберите команды выше!", ephemeral=True)

        await interaction.response.defer()
        config = await self.db.get_guild_config(str(self.guild_id))
        private = config.get("private_commands", {})

        for cmd in self.selected_commands:
            private.pop(cmd, None)

        await self.db.update_config_field(str(self.guild_id), "private_commands", private)
        await interaction.followup.send(f"✅ Команды `{', '.join(self.selected_commands[:5])}` снова публичные!", ephemeral=True)


# ==========================================
#   КВЕСТЫ
# ==========================================

class QuestAddModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int, bot=None):
        super().__init__(title="Добавить квест")
        self.db = db
        self.guild_id = guild_id
        self.bot = bot

        self.quest_id_input = discord.ui.TextInput(
            label="ID квеста (уникальный)",
            placeholder="Например: daily_msgs",
            required=True,
            max_length=50
        )
        self.name_input = discord.ui.TextInput(
            label="Название",
            placeholder="Например: Напиши 50 сообщений",
            required=True,
            max_length=100
        )
        self.type_input = discord.ui.TextInput(
            label="Тип (messages/commands/reactions/voice_join)",
            placeholder="Например: messages",
            required=True,
            max_length=20
        )
        self.target_input = discord.ui.TextInput(
            label="Цель (количество)",
            placeholder="Например: 50",
            required=True,
            max_length=10
        )
        self.reward_input = discord.ui.TextInput(
            label="Награда (монетки)",
            placeholder="Например: 200",
            required=True,
            max_length=10
        )

        self.add_item(self.quest_id_input)
        self.add_item(self.name_input)
        self.add_item(self.type_input)
        self.add_item(self.target_input)
        self.add_item(self.reward_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target = int(self.target_input.value)
            reward = int(self.reward_input.value)
        except ValueError:
            return await interaction.followup.send("❌ Цель и награда должны быть числами!", ephemeral=True)

        quest_type = self.type_input.value.strip()
        if quest_type not in ["messages", "commands", "reactions", "voice_join"]:
            return await interaction.followup.send("❌ Тип квеста: messages, commands, reactions, voice_join", ephemeral=True)

        await self.db.create_quest(
            str(self.guild_id), self.quest_id_input.value.strip(),
            self.name_input.value, self.name_input.value,
            quest_type, target, reward
        )
        await interaction.followup.send(f"✅ Квест **{self.name_input.value}** создан!", ephemeral=True)

        if self.bot:
            guild = self.bot.get_guild(self.guild_id)
            if guild:
                config = await self.db.get_guild_config(str(self.guild_id))
                if config.get("quest_notif_enabled", True):
                    sys_ch_id = config.get("quest_notif_channel_id") or config.get("system_channel_id")
                    sys_ch = guild.get_channel(int(sys_ch_id)) if sys_ch_id else None
                    if sys_ch:
                        type_names = {"messages": "Сообщения", "commands": "Команды", "reactions": "Реакции", "voice_join": "Голос"}
                        try:
                            embed = discord.Embed(
                                title="📜 Новый квест!",
                                color=Colors.MAIN
                            )
                            embed.add_field(name="Квест", value=f"**{self.name_input.value}**", inline=False)
                            embed.add_field(name="Тип", value=f"`{type_names.get(quest_type, quest_type)}`", inline=True)
                            embed.add_field(name="Цель", value=f"`{target}`", inline=True)
                            embed.add_field(name="Награда", value=f"`{reward}`", inline=True)
                            embed.set_footer(text="Ayanami System")
                            await sys_ch.send(embed=embed)
                        except discord.Forbidden:
                            pass


class QuestDeleteModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Удалить квест")
        self.db = db
        self.guild_id = guild_id

        self.quest_id_input = discord.ui.TextInput(
            label="ID квеста для удаления",
            placeholder="Например: daily_msgs",
            required=True,
            max_length=50
        )
        self.add_item(self.quest_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.db.delete_quest(str(self.guild_id), self.quest_id_input.value.strip())
        await interaction.followup.send(f"✅ Квест `{self.quest_id_input.value}` удалён!", ephemeral=True)


class RandomQuestAddModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Добавить квест в пул")
        self.db = db
        self.guild_id = guild_id

        self.name_input = discord.ui.TextInput(label="Название", placeholder="Например: Напиши 30 сообщений", required=True, max_length=100)
        self.type_input = discord.ui.TextInput(label="Тип (messages/commands/reactions/voice_join)", placeholder="Например: messages", required=True, max_length=20)
        self.target_input = discord.ui.TextInput(label="Цель (количество)", placeholder="Например: 30", required=True, max_length=10)
        self.reward_input = discord.ui.TextInput(label="Награда (монетки)", placeholder="Например: 150", required=True, max_length=10)
        self.weight_input = discord.ui.TextInput(label="Вес (чем больше, тем чаще)", placeholder="Например: 1", required=False, max_length=5)

        self.add_item(self.name_input)
        self.add_item(self.type_input)
        self.add_item(self.target_input)
        self.add_item(self.reward_input)
        self.add_item(self.weight_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target = int(self.target_input.value)
            reward = int(self.reward_input.value)
            weight = int(self.weight_input.value) if self.weight_input.value else 1
        except ValueError:
            return await interaction.followup.send("❌ Цель, награда и вес должны быть числами!", ephemeral=True)

        quest_type = self.type_input.value.strip()
        if quest_type not in ["messages", "commands", "reactions", "voice_join"]:
            return await interaction.followup.send("❌ Тип: messages, commands, reactions, voice_join", ephemeral=True)

        import random
        pool_id = f"rqp_{random.randint(1000, 9999)}"
        await self.db.add_random_quest(
            str(self.guild_id), pool_id, self.name_input.value,
            f"Рандомный квест: {self.name_input.value}", quest_type, target, reward, weight
        )
        await interaction.followup.send(f"✅ Квест **{self.name_input.value}** добавлен в пул!", ephemeral=True)


class RandomQuestRemoveModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Удалить квест из пула")
        self.db = db
        self.guild_id = guild_id

        self.pool_id_input = discord.ui.TextInput(label="ID квеста в пуле", placeholder="Например: rqp_1234", required=True, max_length=50)
        self.add_item(self.pool_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.db.remove_random_quest(str(self.guild_id), self.pool_id_input.value.strip())
        await interaction.followup.send(f"✅ Квест `{self.pool_id_input.value}` удалён из пула!", ephemeral=True)


class RandomQuestConfigModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Настройки рандомных квестов")
        self.db = db
        self.guild_id = guild_id

        self.count_input = discord.ui.TextInput(label="Сколько квестов выбирать", placeholder="Например: 3", required=False, max_length=5)
        self.interval_input = discord.ui.TextInput(label="Интервал ротации (часы)", placeholder="Например: 6", required=False, max_length=5)
        self.add_item(self.count_input)
        self.add_item(self.interval_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if self.count_input.value:
            try:
                updates['count'] = max(1, min(int(self.count_input.value), 10))
            except ValueError:
                pass
        if self.interval_input.value:
            try:
                updates['interval_hours'] = max(1, min(int(self.interval_input.value), 168))
            except ValueError:
                pass
        if updates:
            await self.db.update_random_quest_config(str(self.guild_id), **updates)
        config = await self.db.get_random_quest_config(str(self.guild_id))
        await interaction.followup.send(
            f"✅ Настройки: количество **{config['count']}**, интервал **{config['interval_hours']}ч**",
            ephemeral=True
        )


class SetupQuestsView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Справка", emoji="❓", style=discord.ButtonStyle.grey, row=3)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        quests = await self.db.get_guild_quests(str(self.guild_id))
        pool = await self.db.get_random_quest_pool(str(self.guild_id))
        config = await self.db.get_random_quest_config(str(self.guild_id))

        lines = [
            f"### Квесты — справка",
            f"**Активных квестов:** {len(quests)}",
            f"**Пул рандомных:** {len(pool)} (выборка {config['count']}, интервал {config['interval_hours']}ч)",
            "",
            "**Как создать квест:**",
            "1. Нажмите **➕ Добавить квест**",
            "2. Заполните поля:",
            "   • **ID** — уникальный идентификатор (например: `daily_msgs`)",
            "   • **Название** — видно участникам (например: `Напиши 300 сообщений`)",
            "   • **Тип** — что считать: `messages` / `commands` / `reactions` / `voice_join`",
            "   • **Цель** — сколько нужно (в сообщениях/командах/реакциях/минутах войса)",
            "   • **Награда** — монетки за выполнение",
            "",
            "**Примеры квестов:**",
            "• `Напиши 300 сообщений` → тип: `messages`, цель: `300`, награда: `500`",
            "• `Посиди 120 мин в войсе` → тип: `voice_join`, цель: `120`, награда: `800`",
            "• `Выполни 10 команд` → тип: `commands`, цель: `10`, награда: `300`",
            "• `Поставь 20 реакций` → тип: `reactions`, цель: `20`, награда: `200`",
            "",
            "**Рандомные квесты:**",
            "1. Добавьте шаблоны через **🎲 Добавить в пул**",
            "2. Настройте выборку и интервал через **⚙️ Настройки пула**",
            "3. Бот будет автоматически выбирать квесты из пула по расписанию",
            "4. Или нажмите **🔄 Ротация** для немедленного обновления",
            "",
            "**Управление:**",
            "➕ Добавить / 🗑️ Удалить / 📋 Список — ручное управление квестами",
            "📊 Доска квестов — участники и выполнение по каждому квесту",
            "🎲 Пул — добавление/удаление шаблонов для рандома",
            "⚙️ Настройки пула — сколько квестов выбирать и как часто",
            "🔔 Уведомления — канал и вкл/выкл уведомлений о квестах (канал ниже)",
            "🧹 Очистить данные — сброс прогресса/активности/уровней/балансов",
            "",
            "`/questdesk` — доска квестов командой, доступна администраторам",
            "",
            "*Уведомления о квестах отправляются в выбранный канал (по умолчанию — системный).*",
        ]
        embed = discord.Embed(title="📜 Квесты — справка", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Добавить квест", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def btn_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuestAddModal(self.db, self.guild_id, bot=self.cog.bot))

    @discord.ui.button(label="Удалить квест", emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuestDeleteModal(self.db, self.guild_id))

    @discord.ui.button(label="Список квестов", emoji="📋", style=discord.ButtonStyle.grey, row=0)
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        quests = await self.db.get_guild_quests(str(self.guild_id))
        if not quests:
            return await interaction.response.send_message("Квестов пока нет.", ephemeral=True)
        desc = ""
        for q in quests:
            status = "✅" if q['enabled'] else "❌"
            desc += f"{status} **{q['name']}** (`{q['quest_id']}`)\n> Тип: `{q['quest_type']}` | Цель: `{q['target']}` | Награда: `{q['reward']}`\n\n"
        embed = discord.Embed(title="Список квестов", description=desc, color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Доска квестов", emoji="📊", style=discord.ButtonStyle.success, row=0)
    async def btn_desk(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        guild_id = str(self.guild_id)
        quests = await self.db.get_guild_quests(guild_id)
        pool = await self.db.get_random_quest_pool(guild_id)
        if not quests:
            return await interaction.followup.send("Квестов пока нет. Создайте их ниже.", ephemeral=True)

        stats = await self.db.get_quest_progress_stats(guild_id)
        type_icons = {"messages": "💬", "commands": "🤖", "reactions": "🎭", "voice_join": "🎧"}

        desc_lines = []
        for q in quests:
            status = "🟢" if q['enabled'] else "🔴"
            st = stats.get(q['quest_id'], {})
            desc_lines.append(
                f"{status} {type_icons.get(q['quest_type'], '❓')} **{q['name']}** — `{q['quest_id']}`\n"
                f"> Тип: `{q['quest_type']}` | Цель: `{q['target']}` | Награда: `{q['reward']}` {AyanamiUI.E_RP}\n"
                f"> Участники: **{st.get('total', 0)}** | Выполнили: **{st.get('done', 0)}**\n"
            )

        desc = "\n".join(desc_lines)
        if pool:
            desc += f"\n**🎲 Пул рандомных ({len(pool)}):** {', '.join(p['name'] for p in pool)}"

        embed = discord.Embed(title="📊 Доска квестов", description=desc, color=Colors.MAIN)
        guild = self.cog.bot.get_guild(self.guild_id)
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Добавить в пул", emoji="🎲", style=discord.ButtonStyle.blurple, row=1)
    async def btn_pool_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RandomQuestAddModal(self.db, self.guild_id))

    @discord.ui.button(label="Удалить из пула", emoji="🎲", style=discord.ButtonStyle.red, row=1)
    async def btn_pool_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RandomQuestRemoveModal(self.db, self.guild_id))

    @discord.ui.button(label="Пул рандомных", emoji="📋", style=discord.ButtonStyle.grey, row=1)
    async def btn_pool_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = await self.db.get_random_quest_pool(str(self.guild_id))
        config = await self.db.get_random_quest_config(str(self.guild_id))
        desc = f"**Настройки:** выборка **{config['count']}** | интервал **{config['interval_hours']}ч**\n\n"
        if not pool:
            desc += "*Пул пуст.*"
        else:
            for item in pool:
                desc += f"> **{item['name']}** (`{item['pool_id']}`)\n> Тип: `{item['quest_type']}` | Цель: `{item['target']}` | Награда: `{item['reward']}` | Вес: `{item['weight']}`\n\n"
        embed = discord.Embed(title="Пул рандомных квестов", description=desc, color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Канал уведомлений о квестах",
        max_values=1, row=2
    )
    async def select_notif_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer(ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "quest_notif_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал уведомлений о квестах: {select.values[0].mention}", ephemeral=True)

    @discord.ui.button(label="Ротация", emoji="🔄", style=discord.ButtonStyle.blurple, row=3)
    async def btn_rotate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        rotated = await self.db.rotate_random_quests(str(self.guild_id))
        if rotated:
            names = ", ".join(rotated)
            await interaction.followup.send(f"✅ Ротация завершена! Новые квесты: **{names}**", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Нет квестов в пуле для ротации.", ephemeral=True)

    @discord.ui.button(label="Настройки пула", emoji="⚙️", style=discord.ButtonStyle.grey, row=3)
    async def btn_pool_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RandomQuestConfigModal(self.db, self.guild_id))

    @discord.ui.button(label="Уведомления: Вкл", emoji="🔔", style=discord.ButtonStyle.success, row=3)
    async def btn_notif_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(self.guild_id))
        currently = config.get("quest_notif_enabled", True)
        await self.db.update_config_field(str(self.guild_id), "quest_notif_enabled", not currently)
        new_state = not currently
        button.label = "Уведомления: Выкл" if not new_state else "Уведомления: Вкл"
        button.style = discord.ButtonStyle.danger if not new_state else discord.ButtonStyle.success
        notif_ch_id = config.get("quest_notif_channel_id") or config.get("system_channel_id")
        channel_text = f"<#{notif_ch_id}>" if notif_ch_id else "❌ не задан (используйте селект выше)"
        embed = discord.Embed(
            description=f"🔔 Уведомления о квестах теперь **{'включены' if new_state else 'выключены'}**. Канал: {channel_text}.",
            color=Colors.MAIN
        )
        embed.set_footer(text="Ayanami System")
        await interaction.edit_original_response(view=self)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Очистить данные", emoji="🧹", style=discord.ButtonStyle.danger, row=3)
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = QuestClearView(self.db, self.guild_id)
        await view.build_select()
        await interaction.response.send_message(
            "🧹 **Очистка данных**\nВыберите, какие данные нужно очистить:",
            view=view, ephemeral=True
        )


class QuestClearView(discord.ui.View):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(timeout=120)
        self.db = db
        self.guild_id = guild_id

    async def build_select(self):
        options = [
            discord.SelectOption(label="Сбросить весь прогресс квестов", value="__all_progress__", description="Обнулить прогресс всех участников по всем квестам"),
            discord.SelectOption(label="Удалить все квесты", value="__all_quests__", description="Удалить все квесты и их прогресс"),
            discord.SelectOption(label="Очистить пул рандомных", value="__clear_pool__", description="Удалить все шаблоны из пула"),
            discord.SelectOption(label="Очистить активность", value="__activity__", description="Удалить статистику активности (сообщения, войс, команды)"),
            discord.SelectOption(label="Сбросить уровни и XP", value="__levels__", description="Обнулить опыт и сбросить уровни всех участников"),
            discord.SelectOption(label="Обнулить балансы", value="__balances__", description="Сбросить монетки у всех участников"),
            discord.SelectOption(label="Сбросить ежедневные награды", value="__daily__", description="Обнулить серии и ежедневные награды"),
        ]
        quests = await self.db.get_guild_quests(str(self.guild_id))
        for q in quests[:18]:
            label = f"Прогресс: {q['name']}"[:80]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=f"quest_{q['quest_id']}",
                    description=f"Сбросить прогресс по квесту {q['quest_id']}",
                )
            )

        select = discord.ui.Select(placeholder="Выберите что очистить...", options=options)
        select.callback = self.clear_callback
        self.add_item(select)

    async def clear_callback(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        guild_id = str(self.guild_id)

        if value == "__all_progress__":
            await self.db.clear_all_quest_progress(guild_id)
            msg = "✅ Весь прогресс квестов сброшен."
        elif value == "__all_quests__":
            await self.db.clear_all_quests(guild_id)
            msg = "✅ Все квесты и их прогресс удалены."
        elif value == "__clear_pool__":
            await self.db.clear_random_pool(guild_id)
            msg = "✅ Пул рандомных квестов очищен."
        elif value == "__activity__":
            await self.db.clear_user_activity(guild_id)
            msg = "✅ Активность очищена."
        elif value == "__levels__":
            await self.db.clear_levels(guild_id)
            msg = "✅ Уровни и XP сброшены."
        elif value == "__balances__":
            await self.db.clear_balances(guild_id)
            msg = "✅ Балансы обнулены."
        elif value == "__daily__":
            await self.db.clear_daily_rewards(guild_id)
            msg = "✅ Ежедневные награды сброшены."
        elif value.startswith("quest_"):
            quest_id = value[len("quest_"):]
            await self.db.clear_quest_progress(guild_id, quest_id)
            msg = f"✅ Прогресс квеста `{quest_id}` сброшен."
        else:
            msg = "❌ Неизвестная операция."

        for item in self.children:
            if isinstance(item, discord.ui.Select):
                item.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(msg, ephemeral=True)


# ==========================================
#   МАГАЗИН
# ==========================================

class ShopItemAddModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Добавить товар")
        self.db = db
        self.guild_id = guild_id

        self.item_id_input = discord.ui.TextInput(label="ID товара", placeholder="Например: vip_role", required=True, max_length=50)
        self.name_input = discord.ui.TextInput(label="Название", placeholder="Например: VIP роль", required=True, max_length=100)
        self.desc_input = discord.ui.TextInput(label="Описание", placeholder="Например: VIP привилегии на 30 дней", required=True, max_length=200)
        self.price_input = discord.ui.TextInput(label="Цена (монетки)", placeholder="Например: 5000", required=True, max_length=10)
        self.type_input = discord.ui.TextInput(label="Тип товара", placeholder="role, temp_role, title, box, color, lootbox, xp_boost, nickname_token", required=True, max_length=30)

        self.add_item(self.item_id_input)
        self.add_item(self.name_input)
        self.add_item(self.desc_input)
        self.add_item(self.type_input)
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            price = int(self.price_input.value)
        except ValueError:
            return await interaction.followup.send("❌ Цена должна быть числом!", ephemeral=True)

        item_type = self.type_input.value.strip()
        valid_types = ["role", "temp_role", "title", "box", "color", "lootbox", "xp_boost", "nickname_token"]
        if item_type not in valid_types:
            return await interaction.followup.send(f"❌ Тип: {', '.join(valid_types)}", ephemeral=True)

        metadata = {}

        await self.db.create_shop_item(
            str(self.guild_id), self.item_id_input.value.strip(),
            self.name_input.value, self.desc_input.value,
            price, item_type, metadata=metadata, stock=-1
        )
        await interaction.followup.send(f"✅ Товар **{self.name_input.value}** добавлен!", ephemeral=True)


class ShopItemRemoveModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Удалить товар")
        self.db = db
        self.guild_id = guild_id

        self.item_id_input = discord.ui.TextInput(label="ID товара для удаления", placeholder="Например: vip_role", required=True, max_length=50)
        self.add_item(self.item_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.db.delete_shop_item(str(self.guild_id), self.item_id_input.value.strip())
        await interaction.followup.send(f"✅ Товар `{self.item_id_input.value}` удалён!", ephemeral=True)


class SetupShopView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Справка", emoji="❓", style=discord.ButtonStyle.grey, row=1)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        items = await self.db.get_shop_items(str(self.guild_id))
        lines = [
            f"### Магазин — справка",
            f"**Товаров:** {len(items)}",
            "",
            "**Как использовать:**",
            "➕ **Добавить товар** — создайте товар (ID, название, описание, цена, тип)",
            "📋 **Список товаров** — посмотреть все товары",
            "",
            "**Типы товаров:**",
            "`role` — вечная роль | `temp_role` — временная роль (минуты в metadata)",
            "`title` — титул | `lootbox` — лутбокс | `xp_boost` — XP-буст",
            "`nickname_token` — токен смены ника | `color` — цвет ника",
            "",
            "*Магазин доступен через `/shop`. Покупки автоматические.*",
        ]
        embed = discord.Embed(title="🛒 Магазин — справка", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Добавить товар", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def btn_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ShopItemAddModal(self.db, self.guild_id))

    @discord.ui.button(label="Удалить товар", emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ShopItemRemoveModal(self.db, self.guild_id))

    @discord.ui.button(label="Список товаров", emoji="📋", style=discord.ButtonStyle.grey, row=1)
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        items = await self.db.get_shop_items(str(self.guild_id))
        if not items:
            return await interaction.response.send_message("Товаров пока нет.", ephemeral=True)
        desc = ""
        for item in items:
            type_emoji = {
                "role": "🎭", "title": "🏷️", "box": "🎁", "color": "🌈",
                "temp_role": "⏳", "lootbox": "🎰", "xp_boost": "⚡", "nickname_token": "✏️",
            }.get(item['item_type'], "📦")
            stock = f"Осталось: `{item['stock']}`" if item['stock'] >= 0 else "∞"
            desc += f"{type_emoji} **{item['name']}** (`{item['item_id']}`)\n> Цена: `{item['price']}` | Сток: {stock}\n\n"
        embed = discord.Embed(title="Список товаров", description=desc, color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
#   ТИТУЛЫ
# ==========================================

class TitleAddModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Выдать титул")
        self.db = db
        self.guild_id = guild_id

        self.member_input = discord.ui.TextInput(label="ID участника", placeholder="Например: 1234567890", required=True, max_length=20)
        self.title_input = discord.ui.TextInput(label="Название титула", placeholder="Например: Легенда", required=True, max_length=100)
        self.emoji_input = discord.ui.TextInput(label="Эмодзи", placeholder="Например: 👑", required=False, max_length=10)

        self.add_item(self.member_input)
        self.add_item(self.title_input)
        self.add_item(self.emoji_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        member_id = self.member_input.value.strip()
        member = interaction.guild.get_member(int(member_id)) if member_id.isdigit() else None
        if not member:
            return await interaction.followup.send("❌ Участник не найден!", ephemeral=True)

        emoji = self.emoji_input.value.strip() if self.emoji_input.value else "🏷️"
        success = await self.db.add_user_title(str(self.guild_id), str(member.id), self.title_input.value, emoji)
        if success:
            await interaction.followup.send(f"✅ Титул {emoji} **{self.title_input.value}** выдан {member.mention}!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Ошибка при выдаче титула.", ephemeral=True)


class TitleEquipModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Надеть/снять титул")
        self.db = db
        self.guild_id = guild_id

        self.member_input = discord.ui.TextInput(label="ID участника", placeholder="Например: 1234567890", required=True, max_length=20)
        self.title_input = discord.ui.TextInput(label="Название титула", placeholder="Например: Легенда", required=True, max_length=100)

        self.add_item(self.member_input)
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        member_id = self.member_input.value.strip()
        member = interaction.guild.get_member(int(member_id)) if member_id.isdigit() else None
        if not member:
            return await interaction.followup.send("❌ Участник не найден!", ephemeral=True)

        titles = await self.db.get_user_titles(str(self.guild_id), str(member.id))
        target_title = next((t for t in titles if t['title'] == self.title_input.value), None)
        if not target_title:
            return await interaction.followup.send("❌ Титул не найден у этого участника!", ephemeral=True)

        if target_title['active']:
            await self.db.conn.execute(
                'UPDATE user_titles SET active = 0 WHERE guild_id = ? AND user_id = ? AND title = ?',
                (str(self.guild_id), str(member.id), self.title_input.value)
            )
            await self.db.conn.commit()
            await interaction.followup.send(f"✅ Титул **{self.title_input.value}** снят с {member.mention}!", ephemeral=True)
        else:
            await self.db.set_active_title(str(self.guild_id), str(member.id), self.title_input.value)
            await interaction.followup.send(f"✅ Титул **{self.title_input.value}** надет на {member.mention}!", ephemeral=True)


class SetupTitlesView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Справка", emoji="❓", style=discord.ButtonStyle.grey, row=1)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        lines = [
            f"### Титулы — справка",
            "",
            "**Как использовать:**",
            "🏷️ **Выдать титул** — введите ID участника и название титула",
            "🔄 **Надеть/снять** — переключите отображение титула у участника",
            "📋 **Список** — посмотреть всех участников с титулами",
            "",
            "*Титулы отображаются в профиле участника. Один титул может быть активным.*",
        ]
        embed = discord.Embed(title="🏷️ Титулы — справка", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Выдать титул", emoji="🏷️", style=discord.ButtonStyle.success, row=0)
    async def btn_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TitleAddModal(self.db, self.guild_id))

    @discord.ui.button(label="Надеть/снять", emoji="🔄", style=discord.ButtonStyle.blurple, row=0)
    async def btn_equip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TitleEquipModal(self.db, self.guild_id))

    @discord.ui.button(label="Список участников с титулами", emoji="📋", style=discord.ButtonStyle.grey, row=1)
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor = await self.db.conn.execute(
            'SELECT DISTINCT user_id, title, emoji, active FROM user_titles WHERE guild_id = ? ORDER BY user_id',
            (str(self.guild_id),)
        )
        rows = await cursor.fetchall()
        if not rows:
            return await interaction.response.send_message("Титулов пока нет.", ephemeral=True)
        desc = ""
        for row in rows:
            member = interaction.guild.get_member(int(row['user_id']))
            name = member.display_name if member else f"ID: {row['user_id']}"
            active = " ✅" if row['active'] else ""
            desc += f"> {row['emoji']} **{row['title']}** — {name}{active}\n"
        embed = discord.Embed(title="Участники с титулами", description=desc, color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
#   УРОВНИ
# ==========================================

class LevelRoleAddModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Добавить роль за уровень")
        self.db = db
        self.guild_id = guild_id

        self.level_input = discord.ui.TextInput(label="Уровень", placeholder="Например: 10", required=True, max_length=5)
        self.role_id_input = discord.ui.TextInput(label="ID роли", placeholder="Например: 1234567890", required=True, max_length=20)
        self.add_item(self.level_input)
        self.add_item(self.role_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            level = int(self.level_input.value)
        except ValueError:
            return await interaction.followup.send("❌ Уровень должен быть числом!", ephemeral=True)
        role_id = self.role_id_input.value.strip()
        if not role_id.isdigit():
            return await interaction.followup.send("❌ ID роли должен быть числом!", ephemeral=True)
        await self.db.set_level_role(str(self.guild_id), level, role_id)
        await interaction.followup.send(f"✅ За уровень **{level}** будет выдаваться роль <@&{role_id}>", ephemeral=True)


class LevelConfigModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Настройки XP")
        self.db = db
        self.guild_id = guild_id

        self.xp_per_msg = discord.ui.TextInput(label="XP за сообщение", placeholder="Например: 15", required=False, max_length=5)
        self.xp_cooldown = discord.ui.TextInput(label="Кулдаун XP (секунды)", placeholder="Например: 60", required=False, max_length=5)
        self.xp_voice = discord.ui.TextInput(label="XP за минуту голоса", placeholder="Например: 10", required=False, max_length=5)
        self.add_item(self.xp_per_msg)
        self.add_item(self.xp_cooldown)
        self.add_item(self.xp_voice)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if self.xp_per_msg.value:
            try:
                updates['xp_per_message'] = max(1, min(int(self.xp_per_msg.value), 100))
            except ValueError:
                pass
        if self.xp_cooldown.value:
            try:
                updates['xp_cooldown_seconds'] = max(5, min(int(self.xp_cooldown.value), 300))
            except ValueError:
                pass
        if self.xp_voice.value:
            try:
                updates['xp_voice_per_minute'] = max(1, min(int(self.xp_voice.value), 50))
            except ValueError:
                pass
        if updates:
            await self.db.update_guild_config(str(self.guild_id), **updates)
        config = await self.db.get_guild_config(str(self.guild_id))
        await interaction.followup.send(
            f"✅ XP за сообщение: **{config.get('xp_per_message', 15)}** | "
            f"Кулдаун: **{config.get('xp_cooldown_seconds', 60)}с** | "
            f"XP за голос: **{config.get('xp_voice_per_minute', 10)}/мин**",
            ephemeral=True
        )


class LevelUpMsgModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Текст повышения уровня")
        self.db = db
        self.guild_id = guild_id

        self.msg_input = discord.ui.TextInput(
            label="Текст повышения",
            style=discord.TextStyle.paragraph,
            placeholder="{user}, {level}, {server}, {username}",
            required=True,
            max_length=500
        )
        self.add_item(self.msg_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.db.update_guild_config(str(self.guild_id), level_up_message=self.msg_input.value)
        await interaction.followup.send("✅ Текст повышения уровня сохранён!", ephemeral=True)


class SetupLevelsView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=4)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        def ch(id):
            return f"<#{id}>" if id else "Не задан"

        xp_enabled = "🟢" if config.get("xp_enabled", True) else "🔴"
        notif_enabled = "🟢" if config.get("level_up_enabled", True) else "🔴"
        roles_enabled = "🟢" if config.get("role_rewards_enabled", True) else "🔴"
        xp_per_msg = config.get("xp_per_message", 15)
        cooldown = config.get("xp_cooldown_seconds", 60)
        boost = int(config.get("booster_xp_boost", 0) * 100)

        roles = await self.db.get_level_roles(str(self.guild_id))
        roles_text = ""
        for lr in roles[:5]:
            r = interaction.guild.get_role(int(lr['role_id']))
            role_name = r.mention if r else f"`{lr['role_id']}`"
            roles_text += f"  Ур. `{lr['level']}` → {role_name}\n"
        if len(roles) > 5:
            roles_text += f"  ...и ещё {len(roles)-5}\n"

        lines = [
            f"### Уровни",
            f"{xp_enabled} **XP:** {xp_per_msg}/сообщение, кулдаун {cooldown}с",
            f"{notif_enabled} **Уведомления:** {ch(config.get('level_up_channel_id'))}",
            f"{roles_enabled} **Роли за уровни:**",
        ]
        if roles_text:
            lines.append(roles_text)
        else:
            lines.append("  Не заданы")
        lines.append("\n*Используйте кнопки ниже для настройки XP и ролей.*")

        embed = discord.Embed(title="📊 Уровни — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Канал для повышения уровней",
        max_values=1, row=0
    )
    async def select_level_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer(ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "level_up_channel_id", select.values[0].id)
        await interaction.followup.send(f"✅ Канал повышения: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Включить/выключить",
        min_values=0, max_values=4,
        options=[
            discord.SelectOption(label="Начисление XP", value="xp_enabled", emoji="⚡", description="Начислять XP за сообщения"),
            discord.SelectOption(label="Уведомления", value="level_up_enabled", emoji="🔔", description="Писать в канал при повышении"),
            discord.SelectOption(label="Роли за уровни", value="role_rewards_enabled", emoji="🎭", description="Выдавать роли за достижение уровня"),
            discord.SelectOption(label="Бустер XP-бонус", value="booster_boost", emoji="⚡", description="+65% XP для бустеров"),
        ],
        row=1
    )
    async def select_level_toggles(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if 'xp_enabled' in select.values:
            updates['xp_enabled'] = True
        if 'level_up_enabled' in select.values:
            updates['level_up_enabled'] = True
        if 'role_rewards_enabled' in select.values:
            updates['role_rewards_enabled'] = True
        if 'booster_boost' in select.values:
            config = await self.db.get_guild_config(str(self.guild_id))
            updates['booster_xp_boost'] = config.get('booster_xp_boost', 0.65)

        if not updates:
            updates = {'xp_enabled': False, 'level_up_enabled': False, 'role_rewards_enabled': False}

        await self.db.update_guild_config(str(self.guild_id), **updates)
        enabled = select.values
        await interaction.followup.send(f"✅ Включено: {', '.join(enabled) if enabled else 'ничего'}", ephemeral=True)

    @discord.ui.button(label="Настройки XP", emoji="⚙️", style=discord.ButtonStyle.blurple, row=2)
    async def btn_xp_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelConfigModal(self.db, self.guild_id))

    @discord.ui.button(label="Текст повышения", emoji="💬", style=discord.ButtonStyle.green, row=2)
    async def btn_level_up_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelUpMsgModal(self.db, self.guild_id))

    @discord.ui.button(label="Добавить роль за уровень", emoji="🎭", style=discord.ButtonStyle.blurple, row=3)
    async def btn_add_level_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelRoleAddModal(self.db, self.guild_id))

    @discord.ui.button(label="Список ролей за уровни", emoji="📋", style=discord.ButtonStyle.grey, row=3)
    async def btn_list_level_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles = await self.db.get_level_roles(str(self.guild_id))
        if not roles:
            return await interaction.response.send_message("Ролей за уровни пока нет.", ephemeral=True)
        desc = ""
        for lr in roles:
            role = interaction.guild.get_role(int(lr['role_id']))
            role_name = role.mention if role else f"ID: {lr['role_id']}"
            desc += f"> Уровень `{lr['level']}` → {role_name}\n"
        embed = discord.Embed(title="Роли за уровни", description=desc, color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Топ-10", emoji="🏆", style=discord.ButtonStyle.grey, row=3)
    async def btn_top(self, interaction: discord.Interaction, button: discord.ui.Button):
        top = await self.db.get_top_users_by_level(str(self.guild_id), 10)
        if not top:
            return await interaction.response.send_message("Пока нет данных.", ephemeral=True)
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        desc = ""
        for i, entry in enumerate(top):
            member = interaction.guild.get_member(int(entry['user_id']))
            name = member.display_name if member else f"ID: {entry['user_id']}"
            medal = medals.get(i + 1, f"**{i + 1}.**")
            desc += f"{medal} **{name}** — Ур. `{entry['level']}` (`{entry['exp']}` XP)\n"
        embed = discord.Embed(title="🏆 Топ-10 по уровню", description=desc, color=discord.Color(0xf1c40f))
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
#   АВТО-МОДЕРАЦИЯ
# ==========================================

class AutomodConfigModal(discord.ui.Modal):
    def __init__(self, db: Database, guild_id: int):
        super().__init__(title="Настройки авто-модерации")
        self.db = db
        self.guild_id = guild_id

        self.spam_limit = discord.ui.TextInput(label="Лимит сообщений за 5 сек (спам)", placeholder="Например: 5", required=False, max_length=3)
        self.caps_limit = discord.ui.TextInput(label="Процент капса (0-100)", placeholder="Например: 70", required=False, max_length=3)
        self.max_length = discord.ui.TextInput(label="Макс. длина сообщения", placeholder="Например: 2000", required=False, max_length=5)
        self.add_item(self.spam_limit)
        self.add_item(self.caps_limit)
        self.add_item(self.max_length)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(self.guild_id))
        automod = config.get("automod", {})
        if self.spam_limit.value:
            try:
                automod['spam_limit'] = max(2, min(int(self.spam_limit.value), 20))
            except ValueError:
                pass
        if self.caps_limit.value:
            try:
                automod['caps_limit'] = max(30, min(int(self.caps_limit.value), 100))
            except ValueError:
                pass
        if self.max_length.value:
            try:
                automod['max_message_length'] = max(100, min(int(self.max_length.value), 4000))
            except ValueError:
                pass
        config['automod'] = automod
        await self.db.update_config_field(str(self.guild_id), "automod", automod)
        await interaction.followup.send("✅ Настройки авто-модерации сохранены!", ephemeral=True)


class SetupAutomodView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="Текущие настройки", emoji="📋", style=discord.ButtonStyle.grey, row=3)
    async def btn_settings_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_guild_config(str(self.guild_id))
        automod = config.get("automod", {})
        action = automod.get("action", "warn")
        a_names = {"warn": "Предупреждение", "delete": "Удаление", "mute": "Мут", "kick": "Кик"}
        filters = {"anti_spam": "Анти-спам", "anti_caps": "Анти-капс", "anti_links": "Ссылки",
                   "anti_files": "Файлы", "anti_invites": "Инвайты", "max_length": "Макс. длина"}
        enabled = [name for key, name in filters.items() if automod.get(key)]

        lines = [
            f"### Авто-модерация",
            f"**Действие:** {a_names.get(action, action)}",
            f"**Фильтры:** {', '.join(enabled) if enabled else 'никакие'}",
            f"**Спам:** {automod.get('spam_limit', 5)} сообщений/5сек",
            f"**Капс:** {automod.get('caps_limit', 70)}%",
            f"**Макс. длина:** {automod.get('max_message_length', 2000)} символов",
            "\n*Включите фильтры в меню ниже. Нарушители получат выбранное действие.*",
        ]
        embed = discord.Embed(title="🤖 Автомод — настройки", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Включить фильтры",
        min_values=0, max_values=6,
        options=[
            discord.SelectOption(label="Анти-спам", value="anti_spam", emoji="🚫", description="Блокировка спама сообщений"),
            discord.SelectOption(label="Анти-капс", value="anti_caps", emoji="🔠", description="Блокировка капса"),
            discord.SelectOption(label="Блокировка ссылок", value="anti_links", emoji="🔗", description="Блокировка внешних ссылок"),
            discord.SelectOption(label="Блокировка файлов", value="anti_files", emoji="📎", description="Блокировка файлов"),
            discord.SelectOption(label="Анти-маски", value="anti_invites", emoji="📨", description="Блокировка инвайт-кодов Discord"),
            discord.SelectOption(label="Макс. длина", value="max_length", emoji="📏", description="Ограничение длины сообщения"),
        ],
        row=0
    )
    async def select_automod_filters(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(self.guild_id))
        automod = config.get("automod", {})
        all_filters = ["anti_spam", "anti_caps", "anti_links", "anti_files", "anti_invites", "max_length"]
        for f in all_filters:
            automod[f] = f in select.values
        await self.db.update_config_field(str(self.guild_id), "automod", automod)
        enabled = [f for f in select.values]
        disabled = [f for f in all_filters if f not in enabled]
        text = f"✅ Включены: {', '.join(enabled) if enabled else 'ничего'}"
        if disabled:
            text += f"\n❌ Выключены: {', '.join(disabled)}"
        await interaction.followup.send(text, ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Действие за нарушение",
        options=[
            discord.SelectOption(label="Предупреждение", value="warn", emoji="⚠️"),
            discord.SelectOption(label="Удаление сообщения", value="delete", emoji="🗑️"),
            discord.SelectOption(label="Мут (5 мин)", value="mute", emoji="🔇"),
            discord.SelectOption(label="Кик", value="kick", emoji="👢"),
        ],
        row=1
    )
    async def select_automod_action(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(self.guild_id))
        automod = config.get("automod", {})
        automod['action'] = select.values[0]
        await self.db.update_config_field(str(self.guild_id), "automod", automod)
        actions = {'warn': 'Предупреждение', 'delete': 'Удаление', 'mute': 'Мут (5 мин)', 'kick': 'Кик'}
        await interaction.followup.send(f"✅ Действие: **{actions.get(select.values[0], select.values[0])}**", ephemeral=True)

    @discord.ui.button(label="Настройки порогов", emoji="⚙️", style=discord.ButtonStyle.blurple, row=2)
    async def btn_automod_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AutomodConfigModal(self.db, self.guild_id))

    @discord.ui.button(label="Белый список ролей", emoji="🛡️", style=discord.ButtonStyle.grey, row=2)
    async def btn_automod_whitelist(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(self.guild_id))
        automod = config.get("automod", {})
        whitelisted = automod.get('whitelisted_roles', [])
        if not whitelisted:
            desc = "*Белый список пуст. Все роли подчиняются фильтрам.*"
        else:
            desc = ""
            for role_id in whitelisted:
                role = interaction.guild.get_role(int(role_id))
                desc += f"> {role.mention if role else f'ID: {role_id}'}\n"
        embed = discord.Embed(title="Белый список авто-модерации", description=desc, color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Статистика", emoji="📊", style=discord.ButtonStyle.grey, row=3)
    async def btn_automod_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(self.guild_id))
        automod = config.get("automod", {})
        filters_on = [k for k, v in automod.items() if v is True and k.startswith("anti_")]
        desc = (
            f"**Фильтры:** {', '.join(filters_on) if filters_on else 'никакие'}\n"
            f"**Действие:** {automod.get('action', 'warn')}\n"
            f"**Спам-лимит:** {automod.get('spam_limit', 5)} сообщений/5сек\n"
            f"**Капс-лимит:** {automod.get('caps_limit', 70)}%\n"
            f"**Макс. длина:** {automod.get('max_message_length', 2000)} символов"
        )
        embed = discord.Embed(title="📊 Статистика авто-модерации", description=desc, color=Colors.MAIN)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ==========================================
#   ГЛАВНЫЙ КОГ
# ==========================================

class Dashboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Настройка бота")
    @app_commands.default_permissions(administrator=True)
    async def setup_slash(self, interaction: discord.Interaction):
        db = Database()
        config = await db.get_guild_config(str(interaction.guild.id))
        quests = await db.get_guild_quests(str(interaction.guild.id))
        shop_items = await db.get_shop_items(str(interaction.guild.id))
        dashboard_view = DashboardView(self, interaction.guild.id, config, len(quests), len(shop_items))
        await interaction.response.send_message(view=dashboard_view, ephemeral=True)

    @commands.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.setup_slash.callback(self, InteractionAdapter(ctx))


async def setup(bot):
    await bot.add_cog(Dashboard(bot))
