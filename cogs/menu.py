import discord
from discord import app_commands
from discord.ext import commands

from prefix_adapter import InteractionAdapter


class PollCreateModal(discord.ui.Modal, title="📊 Создать опрос"):
    question = discord.ui.TextInput(
        label="Вопрос", placeholder="Что вы думаете о...?", max_length=200
    )
    options = discord.ui.TextInput(
        label="Варианты (через ;)", placeholder="Да;Нет;Может быть", max_length=500
    )
    duration = discord.ui.TextInput(
        label="Длительность (необяз.)",
        placeholder="1ч, 30м, 1д",
        required=False,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Polls")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        await cog.poll.callback(
            cog,
            interaction,
            self.question.value,
            self.options.value,
            duration=self.duration.value or None,
        )


class EventCreateModal(discord.ui.Modal, title="🎉 Создать событие"):
    name = discord.ui.TextInput(
        label="Название", placeholder="Название события", max_length=100
    )
    description = discord.ui.TextInput(
        label="Описание", placeholder="Описание...", max_length=500, required=False
    )
    time = discord.ui.TextInput(
        label="Время начала",
        placeholder="15.06 19:00, завтра 18:00, через 2ч",
        required=False,
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ServerEvents")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        await cog.event_create.callback(
            cog,
            interaction,
            self.name.value,
            self.description.value or "",
            self.time.value or None,
        )


class PollIdModal(discord.ui.Modal, title="📊 ID сообщения"):
    message_id = discord.ui.TextInput(
        label="ID сообщения с голосованием", placeholder="1234567890", max_length=20
    )

    def __init__(self, action: str):
        super().__init__()
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Polls")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        if self.action == "results":
            await cog.poll_results.callback(cog, interaction, self.message_id.value)
        elif self.action == "end":
            await cog.poll_end.callback(cog, interaction, self.message_id.value)


class EventIdModal(discord.ui.Modal, title="🎉 ID события"):
    event_id = discord.ui.TextInput(
        label="ID события", placeholder="1", max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ServerEvents")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        await cog.event_cancel.callback(cog, interaction, int(self.event_id.value))


class ClanJoinModal(discord.ui.Modal, title="🤝 Вступить в клан"):
    clan_name = discord.ui.TextInput(
        label="Название клана", placeholder="Название", max_length=30
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        await cog.clan_join.callback(cog, interaction, self.clan_name.value)


class ClanInfoModal(discord.ui.Modal, title="ℹ️ Клан"):
    clan_name = discord.ui.TextInput(
        label="Название (пусто = свой)", required=False, max_length=30
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        await cog.clan_info.callback(cog, interaction, self.clan_name.value or None)


class MenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        placeholder="Выберите категорию...",
        options=[
            discord.SelectOption(
                label="Голосования",
                description="Опросы с голосованием кнопками",
                emoji="📊",
            ),
            discord.SelectOption(
                label="События", description="Мероприятия сервера", emoji="🎉"
            ),
            discord.SelectOption(
                label="Карточки",
                description="Коллекционные карточки",
                emoji="🃏",
            ),
            discord.SelectOption(
                label="Кланы", description="Клановая система", emoji="⚔️"
            ),
        ],
    )
    async def select_callback(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        category = select.values[0]
        meta = {
            "Голосования": (
                0x3498db,
                "Создавайте опросы, просматривайте результаты и завершайте голосования.",
            ),
            "События": (
                0x2ecc71,
                "Создавайте мероприятия, просматривайте список и отменяйте.",
            ),
            "Карточки": (
                0x9b59b6,
                "Выбрасывайте карточки, просматривайте коллекцию.",
            ),
            "Кланы": (
                0xe74c3c,
                "Создавайте кланы, вступайте, смотрите топ.",
            ),
        }
        color, desc = meta[category]
        embed = discord.Embed(title=category, description=desc, color=color)
        embed.set_footer(text="Выберите действие ниже")
        await interaction.response.edit_message(embed=embed, view=CategoryView(category))


class CategoryView(discord.ui.View):
    def __init__(self, category: str):
        super().__init__(timeout=120)

        if category == "Голосования":
            self._add_btn(
                "Создать опрос", "➕", discord.ButtonStyle.success, self._poll_create
            )
            self._add_btn(
                "Результаты", "📊", discord.ButtonStyle.secondary, self._poll_results
            )
            self._add_btn(
                "Завершить", "🏁", discord.ButtonStyle.danger, self._poll_end
            )
        elif category == "События":
            self._add_btn(
                "Создать", "➕", discord.ButtonStyle.success, self._event_create
            )
            self._add_btn(
                "Список", "📋", discord.ButtonStyle.secondary, self._event_list
            )
            self._add_btn(
                "Отменить", "❌", discord.ButtonStyle.danger, self._event_cancel
            )
        elif category == "Карточки":
            self._add_btn(
                "Выбросить", "🃏", discord.ButtonStyle.primary, self._card_drop
            )
            self._add_btn(
                "Коллекция", "📦", discord.ButtonStyle.secondary, self._card_inventory
            )
        elif category == "Кланы":
            self._add_btn(
                "Создать", "➕", discord.ButtonStyle.success, self._clan_create
            )
            self._add_btn(
                "Мой клан", "ℹ️", discord.ButtonStyle.secondary, self._clan_info
            )
            self._add_btn(
                "Топ", "🏆", discord.ButtonStyle.primary, self._clan_top
            )
            self._add_btn(
                "Вступить", "🤝", discord.ButtonStyle.success, self._clan_join
            )

        back = discord.ui.Button(
            label="Назад", emoji="◀️", style=discord.ButtonStyle.grey, row=4
        )
        back.callback = self._back
        self.add_item(back)

    def _add_btn(self, label, emoji, style, callback):
        btn = discord.ui.Button(label=label, emoji=emoji, style=style)
        btn.callback = callback
        self.add_item(btn)

    async def _back(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 Меню функций",
            description=(
                "Добро пожаловать в центр управления!\n"
                "Выберите категорию из списка ниже."
            ),
            color=0x2B2D31,
        )
        embed.set_footer(text="Ayanami System")
        await interaction.response.edit_message(embed=embed, view=MenuView())

    # ── Polls ──
    async def _poll_create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PollCreateModal())

    async def _poll_results(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PollIdModal("results"))

    async def _poll_end(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PollIdModal("end"))

    # ── Events ──
    async def _event_create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EventCreateModal())

    async def _event_list(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ServerEvents")
        if cog:
            await cog.event_list.callback(cog, interaction)

    async def _event_cancel(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EventIdModal())

    # ── Cards ──
    async def _card_drop(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Collectibles")
        if cog:
            await cog.card_drop.callback(cog, interaction)

    async def _card_inventory(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Collectibles")
        if cog:
            await cog.card_inventory.callback(cog, interaction)

    # ── Clans ──
    async def _clan_create(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if cog:
            await cog.clan_create.callback(cog, interaction)

    async def _clan_info(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ClanInfoModal())

    async def _clan_top(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if cog:
            await cog.clan_top.callback(cog, interaction)

    async def _clan_join(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ClanJoinModal())


class Menu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="menu",
        description="Меню функций — голосования, события, карточки, кланы",
    )
    async def menu(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 Меню функций",
            description=(
                "Добро пожаловать в центр управления!\n"
                "Выберите категорию из списка ниже."
            ),
            color=0x2B2D31,
        )
        embed.set_footer(text="Ayanami System")
        await interaction.response.send_message(embed=embed, view=MenuView())

    @commands.command(name="menu")
    async def menu_prefix(self, ctx):
        await self.menu.callback(self, InteractionAdapter(ctx))


async def setup(bot):
    await bot.add_cog(Menu(bot))
