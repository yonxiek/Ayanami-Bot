import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from ui_components import Colors

ITEM_TYPES = {
    "role": "Роль",
    "card": "Карточка",
    "coins": "Монетки",
}


class Cases(commands.Cog):
    """Кейс-система: открытие кейсов за монетки с дропом ролей, карточек и монет."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def _get_case(self, guild_id: str, case_id: int) -> dict | None:
        cursor = await self.db.conn.execute(
            'SELECT * FROM cases WHERE guild_id = ? AND id = ?', (guild_id, case_id))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _get_items(self, guild_id: str, case_id: int) -> list:
        cursor = await self.db.conn.execute(
            'SELECT * FROM case_items WHERE guild_id = ? AND case_id = ?', (guild_id, case_id))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _roll_item(self, guild_id: str, case_id: int) -> dict | None:
        items = await self._get_items(guild_id, case_id)
        if not items:
            return None
        total = sum(max(0.0, i['drop_rate']) for i in items)
        if total <= 0:
            return random.choice(items)
        roll = random.uniform(0, total)
        cumulative = 0
        for item in items:
            cumulative += max(0.0, item['drop_rate'])
            if roll <= cumulative:
                return item
        return items[-1]

    @app_commands.command(name="casecreate", description="Создать кейс (цена, emoji)")
    @app_commands.describe(name="Название кейса", price="Цена открытия в монетках", emoji="Emoji кейса")
    @app_commands.default_permissions(administrator=True)
    async def casecreate(self, interaction: discord.Interaction, name: str, price: int = 100, emoji: str = "🎁"):
        if price < 0:
            return await interaction.response.send_message(embed=discord.Embed(color=Colors.ERROR, description="❌ Цена не может быть отрицательной."), ephemeral=True)
        cursor = await self.db.conn.execute(
            'INSERT INTO cases (guild_id, name, emoji, price, enabled) VALUES (?, ?, ?, ?, 1)',
            (str(interaction.guild.id), name, emoji, price))
        await self.db.conn.commit()
        embed = discord.Embed(
            color=Colors.SUCCESS,
            description=f"✅ Кейс **{emoji} {name}** создан! ID: `{cursor.lastrowid}`, цена: **{price}** монеток.\n"
                        f"Добавьте предметы через `/caseitem {cursor.lastrowid}`.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="caseremove", description="Удалить кейс вместе с предметами")
    @app_commands.describe(case_id="ID кейса")
    @app_commands.default_permissions(administrator=True)
    async def caseremove(self, interaction: discord.Interaction, case_id: int):
        guild_id = str(interaction.guild.id)
        case = await self._get_case(guild_id, case_id)
        if not case:
            return await interaction.response.send_message(embed=discord.Embed(color=Colors.ERROR, description="❌ Кейс не найден."), ephemeral=True)
        await self.db.conn.execute('DELETE FROM cases WHERE guild_id = ? AND id = ?', (guild_id, case_id))
        await self.db.conn.execute('DELETE FROM case_items WHERE guild_id = ? AND case_id = ?', (guild_id, case_id))
        await self.db.conn.commit()
        await interaction.response.send_message(embed=discord.Embed(color=Colors.SUCCESS, description=f"🗑️ Кейс **{case['emoji']} {case['name']}** удалён."))

    @app_commands.command(name="caseitem", description="Добавить предмет в кейс")
    @app_commands.describe(
        case_id="ID кейса",
        item_type="Тип предмета",
        value="Значение: ID роли / ID карточки / количество монет",
        drop_rate="Шанс выпадения (0.01 - 1.0)",
    )
    @app_commands.choices(item_type=[
        app_commands.Choice(name="Роль", value="role"),
        app_commands.Choice(name="Карточка", value="card"),
        app_commands.Choice(name="Монетки", value="coins"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def caseitem(self, interaction: discord.Interaction, case_id: int, item_type: app_commands.Choice[str], value: str, drop_rate: float = 0.1):
        guild_id = str(interaction.guild.id)
        case = await self._get_case(guild_id, case_id)
        if not case:
            return await interaction.response.send_message(embed=discord.Embed(color=Colors.ERROR, description="❌ Кейс не найден."), ephemeral=True)
        value = value.strip()
        if item_type.value == "role":
            role = discord.utils.get(interaction.guild.roles, id=int(value)) if value.isdigit() else discord.utils.get(interaction.guild.roles, mention=value) or discord.utils.get(interaction.guild.roles, name=value)
            if not role:
                return await interaction.response.send_message(embed=discord.Embed(color=Colors.ERROR, description="❌ Роль не найдена."), ephemeral=True)
            value = str(role.id)
        elif item_type.value == "coins":
            try:
                int(value)
            except ValueError:
                return await interaction.response.send_message(embed=discord.Embed(color=Colors.ERROR, description="❌ Для монет укажите число."), ephemeral=True)
        elif item_type.value == "card":
            card = await self.db.get_card(guild_id, value)
            if not card:
                return await interaction.response.send_message(embed=discord.Embed(color=Colors.ERROR, description="❌ Карточка с таким ID не найдена."), ephemeral=True)
            value = card['card_id']

        drop_rate = max(0.0, min(1.0, drop_rate))
        await self.db.conn.execute(
            'INSERT INTO case_items (guild_id, case_id, item_type, item_value, drop_rate) VALUES (?, ?, ?, ?, ?)',
            (guild_id, case_id, item_type.value, value, drop_rate))
        await self.db.conn.commit()

        label = ITEM_TYPES[item_type.value]
        embed = discord.Embed(color=Colors.SUCCESS, description=f"✅ В кейс `{case_id}` добавлен предмет **{label}** `{value}` (шанс {drop_rate:.0%}).")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="caseitems", description="Список предметов кейса")
    @app_commands.describe(case_id="ID кейса")
    async def caseitems(self, interaction: discord.Interaction, case_id: int):
        guild_id = str(interaction.guild.id)
        case = await self._get_case(guild_id, case_id)
        if not case:
            return await interaction.response.send_message(embed=discord.Embed(color=Colors.ERROR, description="❌ Кейс не найден."), ephemeral=True)
        items = await self._get_items(guild_id, case_id)
        lines = []
        for i, item in enumerate(items, 1):
            label = ITEM_TYPES.get(item['item_type'], item['item_type'])
            value = item['item_value'] if item['item_type'] != "role" else (f"<@&{item['item_value']}>" if (interaction.guild.get_role(int(item['item_value']))) else item['item_value'])
            lines.append(f"`{i}.` {label} — **{value}** — шанс {item['drop_rate']:.0%}")
        embed = discord.Embed(
            title=f"{case['emoji']} {case['name']} — предметы",
            description="\n".join(lines) if lines else "Предметов пока нет.",
            color=Colors.MAIN)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="caselist", description="Список кейсов на сервере")
    async def caselist(self, interaction: discord.Interaction):
        cursor = await self.db.conn.execute(
            'SELECT id, name, emoji, price FROM cases WHERE guild_id = ? AND enabled = 1',
            (str(interaction.guild.id),))
        cases = await cursor.fetchall()
        if not cases:
            return await interaction.response.send_message(embed=discord.Embed(color=Colors.MAIN, description="📭 Кейсов пока нет."), ephemeral=True)
        lines = []
        for c in cases:
            items = await self._get_items(str(interaction.guild.id), c['id'])
            lines.append(f"`{c['id']}.` {c['emoji']} **{c['name']}** — {c['price']} монеток, {len(items)} предметов")
        embed = discord.Embed(title="🎁 Кейсы сервера", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Открыть: /caseopen <ID>")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="caseopen", description="Открыть кейс и получить приз")
    @app_commands.describe(case_id="ID кейса")
    async def caseopen(self, interaction: discord.Interaction, case_id: int):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        case = await self._get_case(guild_id, case_id)
        if not case or not case['enabled']:
            return await interaction.response.send_message(embed=discord.Embed(color=Colors.ERROR, description="❌ Кейс не найден."), ephemeral=True)

        await interaction.response.defer()
        user = await self.db.get_or_create_user(guild_id, user_id)
        if user.get('balance', 0) < case['price']:
            return await interaction.followup.send(embed=discord.Embed(color=Colors.ERROR, description=f"❌ Недостаточно монеток. Нужно **{case['price']}**, у вас **{user.get('balance', 0)}**."), ephemeral=True)

        item = await self._roll_item(guild_id, case_id)
        await self.db.update_user_balance(guild_id, user_id, -case['price'])

        if not item:
            await self.db.update_user_balance(guild_id, user_id, case['price'] // 2)
            embed = discord.Embed(
                title=f"{case['emoji']} {case['name']}",
                description=f"🫙 В кейсе пока пусто. Вернули **{case['price'] // 2}** монеток.",
                color=Colors.MAIN,
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        reward_desc = ""
        embed_color = Colors.MAIN
        embed_thumb = interaction.user.display_avatar.url

        if item['item_type'] == "coins":
            amount = int(item['item_value'])
            await self.db.update_user_balance(guild_id, user_id, amount)
            reward_desc = f"🪙 **{amount}** монеток зачислено на баланс!"
        elif item['item_type'] == "role":
            role = interaction.guild.get_role(int(item['item_value']))
            if not role or role >= interaction.guild.me.top_role:
                await self.db.update_user_balance(guild_id, user_id, case['price'] // 2)
                reward_desc = f"⚠️ Роль недоступна. Возврат **{case['price'] // 2}** монеток."
            else:
                await interaction.user.add_roles(role, reason=f"Кейс {case['name']}")
                reward_desc = f"🎭 Выдана роль {role.mention}!"
        elif item['item_type'] == "card":
            card = await self.db.get_card(guild_id, item['item_value'])
            if not card:
                await self.db.update_user_balance(guild_id, user_id, case['price'] // 2)
                reward_desc = f"⚠️ Карточка недоступна. Возврат **{case['price'] // 2}** монеток."
            else:
                await self.db.conn.execute(
                    "INSERT INTO user_cards (guild_id, user_id, card_id, quantity, obtained_at) "
                    "VALUES (?, ?, ?, 1, ?) "
                    "ON CONFLICT(guild_id, user_id, card_id) DO UPDATE SET quantity = quantity + 1",
                    (guild_id, user_id, card['card_id'], datetime.now(timezone.utc).isoformat()))
                await self.db.conn.commit()
                reward_desc = f"🃏 Карточка **{card['name']}** ({card['emoji']}) добавлена в коллекцию!"
                embed_color = 0x2b2d31

        embed = discord.Embed(
            title=f"{case['emoji']} {case['name']}",
            description=f"С вас списано **{case['price']}** монеток.\n{reward_desc}",
            color=embed_color,
        )
        embed.set_thumbnail(url=embed_thumb)
        embed.set_footer(text=f"Открыл {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Cases(bot))