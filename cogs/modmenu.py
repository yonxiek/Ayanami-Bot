import re

import discord
from discord import app_commands
from discord.ext import commands

from prefix_adapter import find_member


COLORS = {
    "Санкции": 0xe74c3c,
    "Каналы": 0x3498db,
    "Чёрный список": 0x95a5a6,
    "Журнал": 0xf1c40f,
    "Ники": 0x1abc9c,
    "Голос": 0x9b59b6,
    "Роли": 0xe67e22,
}


def _extract_id(text: str | None) -> int | None:
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


class ModActionModal(discord.ui.Modal):
    def __init__(self, title: str, fields, handler):
        super().__init__(title=title)
        self._inputs = []
        for label, placeholder, required, max_length in fields:
            ti = discord.ui.TextInput(
                label=label, placeholder=placeholder,
                required=required, max_length=max_length,
            )
            self._inputs.append(ti)
            self.add_item(ti)
        self._handler = handler

    async def on_submit(self, interaction: discord.Interaction):
        values = [i.value for i in self._inputs]
        await self._handler(interaction, values)


class ModMenuView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.cog._can_mod(interaction.user):
            await interaction.response.send_message(
                "⛔ Это меню доступно только модераторам.", ephemeral=True
            )
            return False
        return True

    @discord.ui.select(
        placeholder="Выберите раздел модерации...",
        options=[
            discord.SelectOption(label="Санкции", description="Варны, муты, кики, баны", emoji="🎯"),
            discord.SelectOption(label="Каналы", description="Очистка, слоумод, лок и анлок", emoji="🧰"),
            discord.SelectOption(label="Ники", description="Смена и сброс ника", emoji="🔤"),
            discord.SelectOption(label="Голос", description="Войс-кик, заглушение", emoji="🎙️"),
            discord.SelectOption(label="Роли", description="Выдача и снятие ролей", emoji="🎭"),
            discord.SelectOption(label="Чёрный список", description="В ЧС и снятие ЧС", emoji="🚫"),
            discord.SelectOption(label="Журнал", description="Заметки и история", emoji="📝"),
        ],
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"🛡️ {select.values[0]}",
                description="Выберите действие ниже.",
                color=COLORS[select.values[0]],
            ).set_footer(text="Ayanami System"),
            view=ModCategoryView(self.cog, select.values[0]),
        )


class ModCategoryView(discord.ui.View):
    def __init__(self, cog, category: str):
        super().__init__(timeout=180)
        self.cog = cog

        actions = {
            "Санкции": [
                ("warn", "Варн", "⚠️"),
                ("unwarn", "Снять варн", "🗑️"),
                ("mute", "Мут", "🔇"),
                ("unmute", "Анмут", "🔊"),
                ("kick", "Кик", "👢"),
                ("ban", "Бан", "🔨"),
                ("unban", "Разбан", "🕊️"),
            ],
            "Каналы": [
                ("clear", "Очистить", "🧹"),
                ("slowmode", "Слоумод", "🐢"),
                ("lock", "Лок", "🔒"),
                ("unlock", "Анлок", "🔓"),
            ],
            "Ники": [
                ("nick", "Сменить ник", "🔤"),
                ("reset_nick", "Сбросить ник", "♻️"),
            ],
            "Голос": [
                ("disconnect", "Войс-кик", "📤"),
                ("deafen", "Заглушить", "🔕"),
                ("undeafen", "Разглушить", "🔔"),
            ],
            "Роли": [
                ("giverole", "Выдать роль", "➕"),
                ("removerole", "Снять роль", "➖"),
            ],
            "Чёрный список": [
                ("blacklist", "В ЧС", "🚫"),
                ("unblacklist", "Из ЧС", "✅"),
            ],
            "Журнал": [
                ("modnote", "Заметка", "📝"),
                ("history", "История", "📜"),
            ],
        }[category]

        for i, (key, label, emoji) in enumerate(actions):
            btn = discord.ui.Button(label=label, emoji=emoji, row=i // 3)
            btn.callback = self._make_callback(key)
            self.add_item(btn)

        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.grey, row=3)
        back.callback = self._back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.cog._can_mod(interaction.user):
            await interaction.response.send_message(
                "⛔ Это меню доступно только модераторам.", ephemeral=True
            )
            return False
        return True

    def _make_callback(self, action: str):
        async def callback(interaction: discord.Interaction):
            await self.cog.run_action(interaction, action)
        return callback

    async def _back(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ Меню модерации",
            description="Выберите раздел ниже. Отображаются только те, кто имеет права модератора.",
            color=0x2B2D31,
        )
        embed.set_footer(text="Ayanami System")
        await interaction.response.edit_message(embed=embed, view=ModMenuView(self.cog))


class ModMenu(commands.Cog):
    """Меню модерации для персонала сервера."""

    FIELDS = {
        "warn": (("Участник", "@Имя", True, 40), ("Причина", "Не указана", False, 1024)),
        "unwarn": (("Участник", "@Имя", True, 40), ("ID варна", "1", True, 10)),
        "mute": (("Участник", "@Имя", True, 40), ("Время", "10s / 5m / 2h / 1d", True, 15), ("Причина", "Не указана", False, 1024)),
        "unmute": (("Участник", "@Имя", True, 40),),
        "kick": (("Участник", "@Имя", True, 40), ("Причина", "Не указана", False, 1024)),
        "ban": (("Участник или ID", "@Имя или ID", True, 40), ("Причина", "Не указана", False, 1024)),
        "unban": (("ID пользователя", "123456789", True, 40),),
        "blacklist": (("Участник или ID", "@Имя или ID", True, 40), ("Причина", "Нарушение правил", False, 1024)),
        "unblacklist": (("Участник или ID", "@Имя или ID", True, 40),),
        "modnote": (("Участник", "@Имя", True, 40), ("Текст заметки", "Что было замечено", True, 1024)),
        "history": (("Участник", "@Имя", True, 40),),
        "clear": (("Количество сообщений", "50", True, 5),),
        "slowmode": (("Секунды", "0 = выключить (макс. 21600)", True, 6),),
        "nick": (("Участник", "@Имя", True, 40), ("Новый ник", "пусто = сбросить", False, 40)),
        "reset_nick": (("Участник", "@Имя", True, 40),),
        "disconnect": (("Участник", "@Имя", True, 40),),
        "deafen": (("Участник", "@Имя", True, 40),),
        "undeafen": (("Участник", "@Имя", True, 40),),
        "giverole": (("Участник", "@Имя", True, 40), ("Роль", "ID или название", True, 40)),
        "removerole": (("Участник", "@Имя", True, 40), ("Роль", "ID или название", True, 40)),
    }

    PERMS = {
        "warn": ("moderate_members",), "unwarn": ("moderate_members",),
        "mute": ("moderate_members",), "unmute": ("moderate_members",),
        "kick": ("kick_members",), "ban": ("ban_members",), "unban": ("ban_members",),
        "blacklist": ("manage_roles",), "unblacklist": ("manage_roles",),
        "modnote": ("moderate_members",), "history": ("moderate_members",),
        "clear": ("manage_messages",), "lock": ("manage_channels",), "unlock": ("manage_channels",),
        "slowmode": ("manage_channels",),
        "nick": ("manage_nicknames",), "reset_nick": ("manage_nicknames",),
        "disconnect": ("move_members",), "deafen": ("deafen_members",), "undeafen": ("deafen_members",),
        "giverole": ("manage_roles",), "removerole": ("manage_roles",),
    }

    TITLES = {
        "warn": "Варн", "unwarn": "Снять варн", "mute": "Мут", "unmute": "Анмут",
        "kick": "Кик", "ban": "Бан", "unban": "Разбан", "blacklist": "Внести в ЧС",
        "unblacklist": "Снять с ЧС", "modnote": "Заметка модератора",
        "history": "История участника", "clear": "Очистить канал",
        "lock": "Закрыть канал", "unlock": "Открыть канал",
        "slowmode": "Слоумод", "nick": "Сменить ник", "reset_nick": "Сбросить ник",
        "disconnect": "Войс-кик", "deafen": "Заглушить (deafen)", "undeafen": "Разглушить",
        "giverole": "Выдать роль", "removerole": "Снять роль",
    }

    def __init__(self, bot):
        self.bot = bot

    def _perm(self, user, perms: tuple) -> bool:
        gp = user.guild_permissions
        if gp.administrator:
            return True
        return any(getattr(gp, p, False) for p in perms)

    def _can_mod(self, user) -> bool:
        return self._perm(user, ("manage_messages", "moderate_members", "kick_members", "ban_members", "manage_roles", "manage_channels"))

    async def _resolve(self, interaction, text: str):
        cid = _extract_id(text)
        if not cid:
            return None, "❌ Не удалось распознать участника. Укажите упоминание или ID."
        member = interaction.guild.get_member(cid)
        if member:
            return member, None
        try:
            return await interaction.client.fetch_user(cid), None
        except discord.NotFound:
            return None, "❌ Пользователь не найден."

    @app_commands.command(name="modmenu", description="Меню модерации: варны, муты, баны, ЧС и др.")
    async def modmenu(self, interaction: discord.Interaction):
        if not self._can_mod(interaction.user):
            return await interaction.response.send_message(
                "⛔ Это меню доступно только модераторам.", ephemeral=True
            )
        embed = discord.Embed(
            title="🛡️ Меню модерации",
            description="Выберите раздел ниже.",
            color=0x2B2D31,
        )
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, view=ModMenuView(self), ephemeral=True)

    @commands.command(name="modmenu")
    async def modmenu_prefix(self, ctx):
        if not self._can_mod(ctx.author):
            return await ctx.send("⛔ Это меню доступно только модераторам.", delete_after=5)
        from prefix_adapter import InteractionAdapter
        await self.modmenu.callback(self, InteractionAdapter(ctx))

    async def run_action(self, interaction: discord.Interaction, action: str):
        if not self._perm(interaction.user, self.PERMS[action]):
            return await interaction.response.send_message(
                "⛔ У вас нет прав для этого действия.", ephemeral=True
            )

        if action in ("lock", "unlock"):
            cog = interaction.client.get_cog("Moderation")
            if not cog:
                return await interaction.response.send_message("❌ Модуль модерации недоступен.", ephemeral=True)
            if action == "lock":
                await cog.lock.callback(cog, interaction)
            else:
                await cog.unlock.callback(cog, interaction)
            return

        fields = self.FIELDS[action]
        await interaction.response.send_modal(
            ModActionModal(self.TITLES[action], fields, self._make_handler(action))
        )

    def _make_handler(self, action: str):
        async def handler(interaction: discord.Interaction, values: list[str]):
            await self._dispatch(interaction, action, values)
        return handler

    async def _dispatch(self, interaction: discord.Interaction, action: str, values: list[str]):
        cog = interaction.client.get_cog("Moderation")
        if not cog:
            return await interaction.response.send_message("❌ Модуль модерации недоступен.", ephemeral=True)

        if action == "slowmode":
            try:
                seconds = int(values[0])
            except ValueError:
                return await interaction.response.send_message("❌ Укажите число секунд.", ephemeral=True)
            return await cog.set_slowmode(interaction, seconds)

        if action == "clear":
            try:
                amount = int(values[0])
            except ValueError:
                return await interaction.response.send_message("❌ Укажите число.", ephemeral=True)
            return await cog.clear.callback(cog, interaction, amount)

        if action in ("blacklist", "unblacklist", "ban", "unban"):
            user = self._resolve_member(interaction.guild, values[0])
            cid = _extract_id(values[0])
            if not user and cid:
                user = await self._fetch_user(interaction, cid)
            if not user:
                return await interaction.response.send_message("❌ Пользователь не найден.", ephemeral=True)
            if action == "blacklist":
                return await cog.blacklist.callback(cog, interaction, user, values[1] or "Нарушение правил")
            if action == "unblacklist":
                return await cog.unblacklist.callback(cog, interaction, user)
            if action == "ban":
                return await cog.ban.callback(cog, interaction, user, values[1] or "Не указана")
            return await cog.unban.callback(cog, interaction, user)

        member = self._resolve_member(interaction.guild, values[0])
        if not member:
            return await interaction.response.send_message("❌ Участник не найден на сервере.", ephemeral=True)

        if action == "warn":
            return await cog.warn.callback(cog, interaction, member, values[1] or "Не указана")
        if action == "unwarn":
            try:
                warn_id = int(values[1])
            except ValueError:
                return await interaction.response.send_message("❌ Укажите ID варна числом.", ephemeral=True)
            return await cog.remove_warn(interaction, member, warn_id)
        if action == "mute":
            return await cog.mute.callback(cog, interaction, member, values[1], values[2] or "Не указана")
        if action == "unmute":
            return await cog.unmute.callback(cog, interaction, member)
        if action == "kick":
            return await cog.kick.callback(cog, interaction, member, values[1] or "Не указана")
        if action == "modnote":
            return await cog.modnote.callback(cog, interaction, member, values[1])
        if action == "history":
            return await cog.history.callback(cog, interaction, member)
        if action == "nick":
            return await cog.change_nickname(interaction, member, values[1].strip() if len(values) > 1 else "")
        if action == "reset_nick":
            return await cog.change_nickname(interaction, member, "")
        if action == "disconnect":
            return await cog.voice_kick(interaction, member)
        if action == "deafen":
            return await cog.set_deafen(interaction, member, True)
        if action == "undeafen":
            return await cog.set_deafen(interaction, member, False)
        if action in ("giverole", "removerole"):
            role = self._resolve_role(interaction.guild, values[1])
            if not role:
                return await interaction.response.send_message("❌ Роль не найдена.", ephemeral=True)
            return await cog.set_role(interaction, member, role, action == "removerole")

        return await interaction.response.send_message("❌ Неизвестное действие.", ephemeral=True)

    def _resolve_member(self, guild: discord.Guild, text: str) -> discord.Member | None:
        return find_member(guild, text)

    def _resolve_role(self, guild: discord.Guild, text: str) -> discord.Role | None:
        text = text.strip()
        digits = re.sub(r"\D", "", text)
        if digits:
            role = guild.get_role(int(digits))
            if role:
                return role
        return discord.utils.get(guild.roles, name=text)

    async def _fetch_user(self, interaction, user_id: int):
        try:
            return await interaction.client.fetch_user(user_id)
        except discord.NotFound:
            return None


async def setup(bot):
    await bot.add_cog(ModMenu(bot))