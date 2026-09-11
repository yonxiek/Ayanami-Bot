import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from prefix_adapter import InteractionAdapter


COLORS = {
    "Голосования": 0x3498db,
    "События": 0x2ecc71,
    "Карточки": 0x9b59b6,
    "Кланы": 0xe74c3c,
    "GitHub": 0x5865f2,
    "Напоминания": 0xf1c40f,
}


def _bool_from_text(text: str | None) -> bool:
    return (text or "").strip().lower() in ("да", "yes", "y", "true", "1", "+", "д")


def _extract_id(text: str) -> int | None:
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


async def _polls_summary(interaction: discord.Interaction) -> str:
    db = Database()
    try:
        cursor = await db.conn.execute(
            "SELECT question, message_id, ends_at FROM polls "
            "WHERE guild_id = ? AND status = 'active' ORDER BY id DESC LIMIT 5",
            (str(interaction.guild.id),)
        )
        rows = await cursor.fetchall()
    except Exception:
        return ""
    if not rows:
        return "Активных голосований нет.\n\nНажмите **➕ Создать**, чтобы запустить первый опрос!"

    lines = []
    for r in rows[:3]:
        time_txt = ""
        if r["ends_at"]:
            try:
                time_txt = f" • до <t:{int(datetime.fromisoformat(r['ends_at']).timestamp())}:R>"
            except Exception:
                pass
        mid = f" [`#{r['message_id']}`]" if r["message_id"] else ""
        lines.append(f"❓ **{r['question']}**{mid}{time_txt}")
    lines.append("")
    lines.append("*Результаты — через 📊, завершение — через 🏁*")
    return "\n".join(lines)


async def _events_summary(interaction: discord.Interaction) -> str:
    db = Database()
    now = datetime.now(timezone.utc)
    try:
        cursor = await db.conn.execute(
            "SELECT id, name, starts_at, status FROM server_events "
            "WHERE guild_id = ? ORDER BY starts_at DESC LIMIT 15",
            (str(interaction.guild.id),)
        )
        rows = await cursor.fetchall()
    except Exception:
        return ""

    upcoming, past = [], []
    for r in rows:
        if not r["starts_at"]:
            continue
        try:
            starts = datetime.fromisoformat(r["starts_at"])
        except Exception:
            continue
        if starts >= now and r["status"] == "active":
            upcoming.append((r, starts))
        elif starts < now:
            past.append((r, starts))
    upcoming.sort(key=lambda x: x[1])
    past.sort(key=lambda x: x[1], reverse=True)

    if not upcoming and not past:
        return "Событий ещё нет.\n\nНажмите **➕ Создать**, чтобы запланировать первое!"

    lines = []
    if upcoming:
        lines.append("📅 **Ближайшие:**")
        for r, s in upcoming[:3]:
            lines.append(f"• **{r['name']}** — <t:{int(s.timestamp())}:R> [`#{r['id']}`]")
    if past:
        lines.append("\n🕰️ **Последние прошедшие:**")
        for r, s in past[:3]:
            lines.append(f"• {discord.utils.format_dt(s, style='d')} **{r['name']}** [`#{r['id']}`]")
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  Модалки
# ─────────────────────────────────────────────

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
    multi_select = discord.ui.TextInput(
        label="Множественный выбор (да/нет)",
        placeholder="нет",
        required=False,
        max_length=5,
    )
    anonymous = discord.ui.TextInput(
        label="Анонимное голосование (да/нет)",
        placeholder="нет",
        required=False,
        max_length=5,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Polls")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        await cog.poll(
            interaction,
            self.question.value,
            self.options.value,
            multi_select=_bool_from_text(self.multi_select.value),
            anonymous=_bool_from_text(self.anonymous.value),
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
    channel_id = discord.ui.TextInput(
        label="Канал (ID, необяз.)",
        placeholder="Оставьте пустым — текущий канал",
        required=False,
        max_length=30,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ServerEvents")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        channel = None
        if self.channel_id.value.strip():
            cid = _extract_id(self.channel_id.value)
            channel = interaction.guild.get_channel(cid) if cid else None
            if not isinstance(channel, discord.TextChannel):
                return await interaction.response.send_message(
                    "❌ Канал не найден (нужен ID текстового канала).", ephemeral=True
                )
        await cog.event_create(
            interaction,
            self.name.value,
            self.description.value or "",
            self.time.value or None,
            channel,
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
            await cog.poll_results(interaction, self.message_id.value)
        elif self.action == "end":
            await cog.poll_end(interaction, self.message_id.value)


class EventIdModal(discord.ui.Modal, title="🎉 ID события"):
    event_id = discord.ui.TextInput(label="ID события", placeholder="1", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ServerEvents")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        await cog.event_cancel(interaction, int(self.event_id.value))


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
        await cog.clan_join(interaction, self.clan_name.value)


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
        await cog.clan_info(interaction, self.clan_name.value or None)


class ClanPayModal(discord.ui.Modal, title="💰 Пополнить казну клана"):
    amount = discord.ui.TextInput(
        label="Сумма (монеты)", placeholder="100", max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        try:
            amount = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("❌ Укажите число.", ephemeral=True)
        await cog.clan_pay(interaction, amount)


class ClanRoleModal(discord.ui.Modal, title="🎖️ Роль в клане"):
    member_id = discord.ui.TextInput(
        label="Участник (упоминание или ID)", placeholder="@Имя", max_length=30
    )
    role = discord.ui.TextInput(
        label="Роль", placeholder="офицер / участник", max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        cid = _extract_id(self.member_id.value)
        member = interaction.guild.get_member(cid) if cid else None
        if not member:
            return await interaction.response.send_message("❌ Участник не найден.", ephemeral=True)
        role_value = {"офицер": "officer", "участник": "member"}.get(
            self.role.value.strip().lower(), self.role.value.strip().lower()
        )
        await cog.clan_role(interaction, member, role_value)


class CardGiveModal(discord.ui.Modal, title="✉️ Передать карточку"):
    member_id = discord.ui.TextInput(
        label="Получатель (упоминание или ID)", placeholder="@Имя", max_length=30
    )
    card_id = discord.ui.TextInput(
        label="ID карточки", placeholder="например: dragon", max_length=30
    )
    amount = discord.ui.TextInput(
        label="Количество (необяз.)", placeholder="1", max_length=5
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Collectibles")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        cid = _extract_id(self.member_id.value)
        member = interaction.guild.get_member(cid) if cid else None
        if not member:
            return await interaction.response.send_message("❌ Получатель не найден.", ephemeral=True)
        try:
            amount = int(self.amount.value or "1")
        except ValueError:
            amount = 1
        await cog.card_give(interaction, member, self.card_id.value, amount)


class GitHubRepoModal(discord.ui.Modal, title="🐙 Репозиторий"):
    repo = discord.ui.TextInput(
        label="Репозиторий (owner/name)", placeholder="user/repo", max_length=100
    )

    def __init__(self, action: str):
        super().__init__()
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("GitHubIntegration")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        if self.action == "commits":
            await cog.github_commits(interaction, self.repo.value, 5)
        elif self.action == "pr":
            await cog.github_pr(interaction, self.repo.value)
        elif self.action == "issues":
            await cog.github_issues(interaction, self.repo.value)


class RemindCreateModal(discord.ui.Modal, title="⏰ Создать напоминание"):
    время = discord.ui.TextInput(
        label="Через сколько (30с / 10м / 2ч / 1д)", placeholder="10м", max_length=10
    )
    текст = discord.ui.TextInput(
        label="Что напомнить", placeholder="Выпить воды", max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Reminders")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        await cog.remind(interaction, self.время.value, self.текст.value)


class RemindRemoveModal(discord.ui.Modal, title="❌ Удалить напоминание"):
    remind_id = discord.ui.TextInput(
        label="ID напоминания (из «Список»)", placeholder="1", max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Reminders")
        if not cog:
            return await interaction.response.send_message(
                "❌ Модуль недоступен.", ephemeral=True
            )
        try:
            remind_id = int(self.remind_id.value)
        except ValueError:
            return await interaction.response.send_message("❌ Укажите число.", ephemeral=True)
        await cog.remind_remove(interaction, remind_id)


# ─────────────────────────────────────────────
#  View-ы
# ─────────────────────────────────────────────

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
            discord.SelectOption(
                label="GitHub", description="Коммиты, PR, Issues", emoji="🐙"
            ),
            discord.SelectOption(
                label="Напоминания", description="Личные напоминания", emoji="⏰"
            ),
        ],
    )
    async def select_callback(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        category = select.values[0]
        desc = {
            "Голосования": await _polls_summary(interaction),
            "События": await _events_summary(interaction),
            "Карточки": "Выбрасывайте карточки, смотрите коллекцию и передавайте их другим.",
            "Кланы": "Создавайте кланы, вступайте, пополняйте казну, следите за топом.",
            "GitHub": "Смотрите последние коммиты, Pull Requests и Issues репозитория.",
            "Напоминания": "Создавайте личные напоминания и управляйте ими.",
        }[category]
        embed = discord.Embed(title=category, description=desc, color=COLORS[category])
        embed.set_footer(text="Выберите действие ниже")
        await interaction.response.edit_message(embed=embed, view=CategoryView(category))


class CategoryView(discord.ui.View):
    def __init__(self, category: str):
        super().__init__(timeout=120)

        if category == "Голосования":
            self._add_btn("Создать опрос", "➕", discord.ButtonStyle.success, self._poll_create)
            self._add_btn("Результаты", "📊", discord.ButtonStyle.secondary, self._poll_results)
            self._add_btn("Завершить", "🏁", discord.ButtonStyle.danger, self._poll_end)
        elif category == "События":
            self._add_btn("Создать", "➕", discord.ButtonStyle.success, self._event_create)
            self._add_btn("Список", "📋", discord.ButtonStyle.secondary, self._event_list)
            self._add_btn("Отменить", "❌", discord.ButtonStyle.danger, self._event_cancel)
        elif category == "Карточки":
            self._add_btn("Выбросить", "🃏", discord.ButtonStyle.primary, self._card_drop)
            self._add_btn("Коллекция", "📦", discord.ButtonStyle.secondary, self._card_inventory)
            self._add_btn("Передать", "✉️", discord.ButtonStyle.success, self._card_give)
        elif category == "Кланы":
            self._add_btn("Создать", "➕", discord.ButtonStyle.success, self._clan_create)
            self._add_btn("Мой клан", "ℹ️", discord.ButtonStyle.secondary, self._clan_info)
            self._add_btn("Топ", "🏆", discord.ButtonStyle.primary, self._clan_top)
            self._add_btn("Вступить", "🤝", discord.ButtonStyle.success, self._clan_join)
            self._add_btn("Покинуть", "🚪", discord.ButtonStyle.danger, self._clan_leave)
            self._add_btn("Казну", "💰", discord.ButtonStyle.secondary, self._clan_pay)
            self._add_btn("Роли", "🎖️", discord.ButtonStyle.secondary, self._clan_role)
        elif category == "GitHub":
            self._add_btn("Коммиты", "📝", discord.ButtonStyle.primary, self._gh_commits)
            self._add_btn("Pull Requests", "🔀", discord.ButtonStyle.secondary, self._gh_pr)
            self._add_btn("Issues", "🐛", discord.ButtonStyle.secondary, self._gh_issues)
        elif category == "Напоминания":
            self._add_btn("Создать", "⏰", discord.ButtonStyle.success, self._remind_create)
            self._add_btn("Список", "📋", discord.ButtonStyle.secondary, self._remind_list)
            self._add_btn("Удалить", "❌", discord.ButtonStyle.danger, self._remind_remove)

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

    async def _not_found(self, interaction, module):
        await interaction.response.send_message(f"❌ Модуль `{module}` недоступен.", ephemeral=True)

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
        db = Database()
        now = datetime.now(timezone.utc)
        try:
            cursor = await db.conn.execute(
                "SELECT id, name, starts_at, creator_id, status FROM server_events "
                "WHERE guild_id = ? ORDER BY starts_at DESC LIMIT 25",
                (str(interaction.guild.id),)
            )
            rows = await cursor.fetchall()
        except Exception:
            return await interaction.response.send_message("❌ Ошибка чтения базы.", ephemeral=True)
        if not rows:
            return await interaction.response.send_message("📭 Событий ещё нет. Создайте первое через **➕ Создать**!", ephemeral=True)
        upcoming, past = [], []
        for r in rows:
            if not r["starts_at"]:
                continue
            try:
                starts = datetime.fromisoformat(r["starts_at"])
            except Exception:
                continue
            if starts >= now and r["status"] == "active":
                upcoming.append((r, starts))
            elif starts < now:
                past.append((r, starts))
        upcoming.sort(key=lambda x: x[1])
        past.sort(key=lambda x: x[1], reverse=True)
        lines = []
        if upcoming:
            lines.append("### 📅 Предстоящие")
            for r, s in upcoming[:5]:
                lines.append(f"• **{r['name']}** — <t:{int(s.timestamp())}:R> [`#{r['id']}`]")
        if past:
            lines.append("\n### 🕰️ Прошедшие")
            for r, s in past[:5]:
                lines.append(f"• {discord.utils.format_dt(s, style='d')} **{r['name']}** [`#{r['id']}`]")
        if not lines:
            lines.append("Нет событий для показа.")
        embed = discord.Embed(title="🎉 События сервера", description="\n".join(lines), color=COLORS["События"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _event_cancel(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EventIdModal())

    # ── Cards ──
    async def _card_drop(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Collectibles")
        if cog:
            await cog.card_drop(interaction)
        else:
            await self._not_found(interaction, "Collectibles")

    async def _card_inventory(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Collectibles")
        if cog:
            await cog.card_inventory(interaction)
        else:
            await self._not_found(interaction, "Collectibles")

    async def _card_give(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CardGiveModal())

    # ── Clans ──
    async def _clan_create(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if cog:
            await cog.clan_create(interaction)
        else:
            await self._not_found(interaction, "Clans")

    async def _clan_info(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ClanInfoModal())

    async def _clan_top(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if cog:
            await cog.clan_top(interaction)
        else:
            await self._not_found(interaction, "Clans")

    async def _clan_join(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ClanJoinModal())

    async def _clan_leave(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Clans")
        if cog:
            await cog.clan_leave(interaction)
        else:
            await self._not_found(interaction, "Clans")

    async def _clan_pay(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ClanPayModal())

    async def _clan_role(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ClanRoleModal())

    # ── GitHub ──
    async def _gh_commits(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GitHubRepoModal("commits"))

    async def _gh_pr(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GitHubRepoModal("pr"))

    async def _gh_issues(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GitHubRepoModal("issues"))

    # ── Reminders ──
    async def _remind_create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RemindCreateModal())

    async def _remind_list(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Reminders")
        if cog:
            await cog.reminders(interaction)
        else:
            await self._not_found(interaction, "Reminders")

    async def _remind_remove(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RemindRemoveModal())


class Menu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(
        name="menu",
        description="Меню функций — голосования, события, карточки, кланы, GitHub, напоминания",
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