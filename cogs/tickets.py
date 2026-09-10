import discord
from datetime import datetime, timezone
from discord.ext import commands
from db import Database
from ui_components import Colors
from cogs.achievements import award_achievement


class TicketCloseView(discord.ui.View):
    def __init__(self, ticket_id: int):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

    @discord.ui.button(label="Закрыть тикет", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("❌ Модуль тикетов недоступен.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await cog._close_ticket(interaction, self.ticket_id)


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, categories: list[dict]):
        options = []
        for cat in categories:
            desc = cat.get("description", "Нет описания")[:100]
            options.append(discord.SelectOption(
                label=cat["name"],
                value=str(cat["category_id"]),
                description=desc,
                emoji=cat.get("emoji", "📩"),
            ))
        if not options:
            options.append(discord.SelectOption(label="Нет категорий", value="none"))
        super().__init__(placeholder="Выберите категорию...", options=options)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Tickets")
        if not cog:
            return
        if self.values[0] == "none":
            return await interaction.response.send_message("❌ Категории не настроены.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await cog._create_ticket(interaction, int(self.values[0]))


class TicketPanelView(discord.ui.View):
    def __init__(self, categories: list[dict]):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect(categories))


class Tickets(commands.Cog):
    """Система тикетов (обращений в поддержку)."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    # ==========================================================
    #                    ЛОГИКА РАССЫЛКИ ПАНЕЛИ
    # ==========================================================

    async def _handle_category(self, interaction: discord.Interaction, action: str, name: str = None,
                              emoji: str = "📩", description: str = "", category_id: int = None):
        config = await self.db.get_guild_config(str(interaction.guild.id))
        categories = config.get("ticket_categories", [])

        if action == "remove":
            if not name:
                return await interaction.response.send_message("❌ Укажите название для удаления.", ephemeral=True)
            before = len(categories)
            categories = [c for c in categories if c["name"].lower() != name.lower()]
            if len(categories) == before:
                return await interaction.response.send_message("❌ Категория не найдена.", ephemeral=True)
            await self.db.update_config_field(str(interaction.guild.id), "ticket_categories", categories)
            return await interaction.response.send_message(f"✅ Категория **{name}** удалена.", ephemeral=True)

        if not name:
            return await interaction.response.send_message("❌ Укажите название.", ephemeral=True)
        cat = {"name": name, "emoji": emoji, "description": description, "category_id": category_id or 0}
        categories.append(cat)
        await self.db.update_config_field(str(interaction.guild.id), "ticket_categories", categories)
        await interaction.response.send_message(
            f"✅ Категория **{name}** добавлена. ID Discord-категории: {category_id or 0}.",
            ephemeral=True
        )

    async def _send_panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        config = await self.db.get_guild_config(str(interaction.guild.id))
        categories = config.get("ticket_categories", [])
        if not categories:
            return await interaction.followup.send(
                "❌ Сначала добавьте категории на панели «Тикеты» в `/setup`.", ephemeral=True
            )

        embed = discord.Embed(
            title="📩 Поддержка сервера",
            description="Нажмите на выпадающее меню ниже, чтобы создать обращение.\nВыберите подходящую категорию для вашего вопроса.",
            color=Colors.MAIN,
        )
        embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        view = TicketPanelView(categories)
        await target.send(embed=embed, view=view)
        await interaction.followup.send(f"✅ Панель отправлена в {target.mention}", ephemeral=True)

    # ==========================================================
    #                ЛОГИКА ТИКЕТОВ
    # ==========================================================

    async def _create_ticket(self, interaction: discord.Interaction, category_id: int):
        guild = interaction.guild
        user = interaction.user
        config = await self.db.get_guild_config(str(guild.id))

        cursor = await self.db.conn.execute(
            "SELECT ticket_id FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
            (str(guild.id), str(user.id))
        )
        existing = await cursor.fetchone()
        if existing:
            return await interaction.followup.send(
                f"❌ У вас уже есть открытый тикет <#{existing[0]}>. Закройте его перед созданием нового.",
                ephemeral=True
            )

        ticket_categories = config.get("ticket_categories", [])
        cat_info = next((c for c in ticket_categories if c.get("category_id") == category_id), None)
        cat_name = cat_info["name"] if cat_info else "Обращение"
        cat_emoji = cat_info.get("emoji", "📩") if cat_info else "📩"

        ticket_number = await self._next_ticket_number(str(guild.id))
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }

        # Добавляем роль поддержки, если настроена
        support_role_id = config.get("ticket_support_role_id")
        if support_role_id:
            support_role = guild.get_role(int(support_role_id))
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, attach_files=True
                )

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{ticket_number}",
            category=discord.Object(id=category_id) if category_id else None,
            overwrites=overwrites,
            topic=f"Тикет #{ticket_number} — {user.name} ({user.id})",
        )

        await self.db.conn.execute(
            "INSERT INTO tickets (guild_id, user_id, channel_id, ticket_number, category_name, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (str(guild.id), str(user.id), str(ticket_channel.id), ticket_number, cat_name,
             datetime.now(timezone.utc).isoformat())
        )
        await self.db.conn.commit()

        embed = discord.Embed(
            title=f"{cat_emoji} Тикет #{ticket_number}",
            description=(
                f"Здравствуйте, {user.mention}! Опишите вашу проблему или вопрос.\n\n"
                f"**Категория:** {cat_name}\n"
                f"**Статус:** Открыт\n\n"
                "Нажмите кнопку ниже, чтобы закрыть тикет."
            ),
            color=Colors.SUCCESS,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Тикет #{ticket_number} • {guild.name}")

        view = TicketCloseView(ticket_number)
        await ticket_channel.send(content=user.mention, embed=embed, view=view)
        await interaction.followup.send(f"✅ Тикет создан: {ticket_channel.mention}", ephemeral=True)

        await self._log_ticket("created", guild, user, ticket_number, cat_name)

        await award_achievement(self.db, str(guild.id), str(user.id), "first_ticket", user)
        if await self.db.count_tickets(str(guild.id), str(user.id)) >= 5:
            await award_achievement(self.db, str(guild.id), str(user.id), "tickets_5", user)

    async def _close_ticket(self, interaction: discord.Interaction, ticket_number: int):
        guild = interaction.guild
        config = await self.db.get_guild_config(str(guild.id))

        cursor = await self.db.conn.execute(
            "SELECT channel_id, user_id, category_name FROM tickets "
            "WHERE guild_id = ? AND ticket_number = ? AND status = 'open'",
            (str(guild.id), ticket_number)
        )
        row = await cursor.fetchone()
        if not row:
            return await interaction.followup.send("❌ Тикет не найден или уже закрыт.", ephemeral=True)

        channel_id, user_id, cat_name = row["channel_id"], row["user_id"], row["category_name"]

        await self.db.conn.execute(
            "UPDATE tickets SET status = 'closed', closed_at = ? WHERE guild_id = ? AND ticket_number = ?",
            (datetime.now(timezone.utc).isoformat(), str(guild.id), ticket_number)
        )
        await self.db.conn.commit()

        # Собрать историю
        channel = guild.get_channel(int(channel_id))
        messages_text = ""
        if channel:
            try:
                async for msg in channel.history(limit=200, oldest_first=True):
                    if msg.author.bot:
                        continue
                    time_str = msg.created_at.strftime("%d.%m %H:%M")
                    messages_text += f"[{time_str}] {msg.author.name}: {msg.content[:200]}\n"
            except Exception:
                pass

        embed = discord.Embed(
            title=f"🔒 Тикет #{ticket_number} закрыт",
            description=f"**Категория:** {cat_name}\n**Закрыт:** <@{interaction.user.id}>",
            color=Colors.WARNING,
            timestamp=datetime.now(timezone.utc),
        )
        if messages_text:
            embed.add_field(name="История сообщений", value=messages_text[:1024] or "Пусто", inline=False)

        # Лог
        log_channel_id = config.get("ticket_log_channel_id")
        if log_channel_id:
            log_channel = guild.get_channel(int(log_channel_id))
            if log_channel:
                await log_channel.send(embed=embed)

        # Уведомление создателю
        member = guild.get_member(int(user_id))
        if member:
            try:
                await member.send(f"🔒 Ваш тикет **#{ticket_number}** на сервере **{guild.name}** был закрыт.")
            except Exception:
                pass

        if channel:
            await channel.delete(reason=f"Тикет #{ticket_number} закрыт")

        await interaction.followup.send(f"✅ Тикет #{ticket_number} закрыт.", ephemeral=True)
        await self._log_ticket("closed", guild, interaction.user, ticket_number, cat_name)

    async def _next_ticket_number(self, guild_id: str) -> int:
        cursor = await self.db.conn.execute(
            "SELECT MAX(ticket_number) FROM tickets WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        return (row[0] or 0) + 1 if row else 1

    async def _log_ticket(self, action: str, guild, user, ticket_number: int, category: str):
        config = await self.db.get_guild_config(str(guild.id))
        log_channel_id = config.get("ticket_log_channel_id")
        if not log_channel_id:
            return
        log_channel = guild.get_channel(int(log_channel_id))
        if not log_channel:
            return

        color = Colors.SUCCESS if action == "created" else Colors.WARNING
        emoji = "📩" if action == "created" else "🔒"
        text = "Создан" if action == "created" else "Закрыт"

        embed = discord.Embed(
            title=f"{emoji} Тикет #{ticket_number} {text}",
            description=f"**Пользователь:** {user.mention}\n**Категория:** {category}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        try:
            await log_channel.send(embed=embed)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Tickets(bot))
