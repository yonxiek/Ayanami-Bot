import discord
from discord.ext import commands
from discord import app_commands
from ui_components import Colors
from db import Database


class HelpDropdown(discord.ui.Select):
    def __init__(self, sections: list[tuple[str, str, str]]):
        options = [discord.SelectOption(label="Все команды", value="__all__", description="Общий список по всем разделам", emoji="📚")]
        for key, label, _ in sections:
            options.append(discord.SelectOption(label=label, value=key, emoji=label.split()[0] if label.split() else None))
        super().__init__(placeholder="Выберите раздел команд…", min_values=1, max_values=1, options=options)
        self.sections = sections

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = self.view.build_embed(self.values[0])
        await interaction.edit_original_response(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, embeds: dict, sections: list[tuple[str, str, str]]):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.sections = sections
        self.add_item(HelpDropdown(sections))

    def build_embed(self, key: str) -> discord.Embed:
        return self.embeds[key]


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    COG_RU = {
        "Moderation": ("🛡️ Модерация", "Управление сервером"),
        "Economy": ("💰 Экономика", "Профили и баллы"),
        "Utils": ("🛠️ Утилиты", "Полезные команды"),
        "Dashboard": ("⚙️ Настройки", "Управление ботом"),
        "Permissions": ("🔒 Права", "Управление доступом"),
        "Logging": ("📋 Логирование", "Журнал событий"),
        "Greetings": ("👋 Приветствия", "Привет/Прощание/Буст"),
        "VoiceRooms": ("🔊 Приватки", "Голосовые комнаты"),
        "Security": ("🚨 Безопасность", "Anti-Nuke защита"),
        "MiniGames": ("🎮 Мини-игры", "Факты, угадай число, КНБ"),
        "Reactions": ("🎭 Реакции", "Реакции на сообщения"),
        "Shop": ("🛒 Магазин", "Покупка товаров"),
        "Levels": ("📊 Уровни", "Опыт и роли"),
        "Quests": ("📜 Квесты", "Задания и награды"),
    }

    def _gather_commands(self, config, private_cmds, user_role_ids, is_admin) -> list[tuple[str, str]]:
        """Возвращает список [(раздел, текст_команд)] для видимых пользователю когов."""
        sections = []
        for cog_name, cog in self.bot.cogs.items():
            if cog_name in ["HelpCog", "ErrorHandler", "SlashSync", "Security", "StatusCog", "Voice"]:
                continue
            slash_cmds = [cmd for cmd in cog.walk_app_commands() if isinstance(cmd, app_commands.Command)]
            if not slash_cmds:
                continue
            cmd_text = ""
            shown = 0
            for cmd in slash_cmds:
                if cmd.qualified_name in private_cmds:
                    if is_admin:
                        badge = "🔐"
                    else:
                        allowed_roles = private_cmds[cmd.qualified_name]
                        if any(rid in allowed_roles for rid in user_role_ids):
                            badge = "🔐"
                        else:
                            continue
                else:
                    perms = cmd.default_permissions
                    is_mod = perms is not None and perms.value != 0
                    badge = "🛡️" if is_mod else "👤"
                cmd_text += f"{badge} `/{cmd.name}` — *{cmd.description or 'Нет описания'}*\n"
                shown += 1
            if shown > 0:
                cat_info = self.COG_RU.get(cog_name, (f"📁 {cog_name}", ""))
                sections.append((cat_info[0], cmd_text))
        return sections

    @app_commands.command(name="help", description="Список всех команд бота")
    async def help_slash(self, interaction: discord.Interaction):
        config = await self.db.get_guild_config(str(interaction.guild.id)) if interaction.guild else {}
        private_cmds = config.get("private_commands", {})
        user_role_ids = [str(r.id) for r in interaction.user.roles] if interaction.guild else []
        is_admin = interaction.guild and (interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator)

        sections = self._gather_commands(config, private_cmds, user_role_ids, is_admin)

        intro = (
            "Справочник команд бота. Выберите раздел в меню ниже, "
            "чтобы посмотреть команды конкретного модуля.\n\n"
            "👤 `[Участник]` — доступно всем.\n"
            "🛡️ `[Модерация]` — требуются права.\n"
            "🔐 `[Приватная]` — только для определённых ролей."
        )

        def base_embed():
            e = discord.Embed(title="Справочник команд", color=Colors.MAIN)
            e.set_thumbnail(url=self.bot.user.display_avatar.url)
            e.set_footer(text=f"Запросил: {interaction.user.name}")
            return e

        # Embed «все разделы»
        all_embed = base_embed()
        all_embed.description = intro
        for name, value in sections:
            all_embed.add_field(name=name, value=value, inline=False)

        # По одному embed на раздел
        embeds = {"__all__": all_embed}
        section_items = []
        for name, value in sections:
            key = name
            e = base_embed()
            e.description = intro
            e.add_field(name=name, value=value, inline=False)
            embeds[key] = e
            section_items.append((key, name, value))

        view = HelpView(embeds, section_items)
        await interaction.response.send_message(embed=all_embed, view=view)


    @commands.command(name="help")
    async def help_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.help_slash.callback(self, InteractionAdapter(ctx))

async def setup(bot):
    bot.remove_command('help')
    await bot.add_cog(HelpCog(bot))
