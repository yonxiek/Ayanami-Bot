import discord
import random
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors
from cogs.achievements import award_achievement


RARITY_CONFIG = {
    "common": {"color": 0x95a5a6, "label": "Обычная", "emoji": "⚪"},
    "rare": {"color": 0x3498db, "label": "Редкая", "emoji": "🔵"},
    "epic": {"color": 0x9b59b6, "label": "Эпическая", "emoji": "🟣"},
    "legendary": {"color": 0xf39c12, "label": "Легендарная", "emoji": "🟡"},
}


class Collectibles(commands.Cog):
    """Система коллекционных карточек."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def _add_card(self, interaction: discord.Interaction, card_id: str, name: str,
                        rarity: str, emoji: str = "🃏",
                        description: str = "", drop_rate: float = 0.1):
        drop_rate = max(0.01, min(1.0, drop_rate))
        rarity = rarity if rarity in RARITY_CONFIG else "common"
        await self.db.conn.execute(
            "INSERT OR REPLACE INTO collectible_cards (guild_id, card_id, name, description, rarity, emoji, drop_rate, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (str(interaction.guild.id), card_id, name, description, rarity, emoji, drop_rate)
        )
        await self.db.conn.commit()
        r_info = RARITY_CONFIG[rarity]
        return f"{r_info['emoji']} Карточка **{name}** [{r_info['label']}] добавлена! (шанс: {drop_rate:.0%})"

    @app_commands.command(name="card_drop", description="Выбросить случайную карточку")
    @app_commands.checks.cooldown(1, 300, key=lambda i: (i.guild_id, i.user.id))
    async def card_drop(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild.id)

        cursor = await self.db.conn.execute(
            "SELECT card_id, name, description, rarity, emoji, drop_rate FROM collectible_cards "
            "WHERE guild_id = ? AND enabled = 1", (guild_id,)
        )
        cards = await cursor.fetchall()
        if not cards:
            return await interaction.followup.send("📭 Карточек в пуле нет. Админы, добавьте их на панели «Карточки» в `/setup`.", ephemeral=True)

        # Взвешенный рандом
        total_rate = sum(c["drop_rate"] for c in cards)
        roll = random.uniform(0, total_rate)
        cumulative = 0
        selected = cards[-1]
        for card in cards:
            cumulative += card["drop_rate"]
            if roll <= cumulative:
                selected = card
                break

        r_info = RARITY_CONFIG[selected["rarity"]]
        user_id = str(interaction.user.id)

        # Запись в инвентарь
        await self.db.conn.execute(
            "INSERT INTO user_cards (guild_id, user_id, card_id, quantity, obtained_at) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(guild_id, user_id, card_id) DO UPDATE SET quantity = quantity + 1",
            (guild_id, user_id, selected["card_id"], datetime.now(timezone.utc).isoformat())
        )
        await self.db.conn.commit()

        embed = discord.Embed(
            title=f"{selected['emoji']} {selected['name']}",
            description=(
                f"**Редкость:** {r_info['emoji']} {r_info['label']}\n"
                f"**Описание:** {selected['description'] or 'Нет описания'}\n"
                f"**ID:** `{selected['card_id']}`"
            ),
            color=r_info["color"],
        )
        embed.set_footer(text=f"Выпало {interaction.user.name}!")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed)

        await award_achievement(self.db, guild_id, user_id, "first_card", interaction.user)
        if selected["rarity"] == "legendary":
            await award_achievement(self.db, guild_id, user_id, "legendary_card", interaction.user)
        if await self.db.count_unique_cards(guild_id, user_id) >= 10:
            await award_achievement(self.db, guild_id, user_id, "cards_10", interaction.user)

    @app_commands.command(name="card_inventory", description="Моя коллекция карточек")
    async def card_inventory(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        guild_id = str(interaction.guild.id)

        cursor = await self.db.conn.execute(
            "SELECT uc.card_id, uc.quantity, cc.name, cc.rarity, cc.emoji "
            "FROM user_cards uc JOIN collectible_cards cc ON uc.card_id = cc.card_id "
            "WHERE uc.guild_id = ? AND uc.user_id = ? ORDER BY cc.rarity DESC, uc.quantity DESC",
            (guild_id, str(target.id))
        )
        rows = await cursor.fetchall()
        if not rows:
            return await interaction.response.send_message(f"📭 У {target.name} нет карточек.", ephemeral=True)

        lines = []
        total = 0
        for r in rows:
            r_info = RARITY_CONFIG.get(r["rarity"], {})
            lines.append(f"{r['emoji']} **{r['name']}** {r_info.get('emoji', '')} x{r['quantity']}")
            total += r["quantity"]

        embed = discord.Embed(
            title=f"🃏 Коллекция {target.name}",
            description="\n".join(lines[:25]),
            color=Colors.MAIN,
        )
        embed.set_footer(text=f"Всего: {total} карточек")
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="card_give", description="Передать карточку другому игроку")
    @app_commands.describe(member="Получатель", card_id="ID карточки", amount="Количество")
    async def card_give(self, interaction: discord.Interaction, member: discord.Member, card_id: str, amount: int = 1):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("❌ Нельзя передать себе.", ephemeral=True)
        if amount < 1:
            return await interaction.response.send_message("❌ Количество должно быть >= 1.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        cursor = await self.db.conn.execute(
            "SELECT quantity FROM user_cards WHERE guild_id = ? AND user_id = ? AND card_id = ?",
            (guild_id, user_id, card_id)
        )
        row = await cursor.fetchone()
        if not row or row["quantity"] < amount:
            return await interaction.response.send_message("❌ У вас недостаточно этих карточек.", ephemeral=True)

        # Списание
        await self.db.conn.execute(
            "UPDATE user_cards SET quantity = quantity - ? WHERE guild_id = ? AND user_id = ? AND card_id = ?",
            (amount, guild_id, user_id, card_id)
        )
        # Выдача
        await self.db.conn.execute(
            "INSERT INTO user_cards (guild_id, user_id, card_id, quantity, obtained_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, card_id) DO UPDATE SET quantity = quantity + ?",
            (guild_id, str(member.id), card_id, amount, datetime.now(timezone.utc).isoformat(), amount)
        )
        await self.db.conn.commit()
        await interaction.response.send_message(f"✅ Передано **{amount}** карточек `{card_id}` -> {member.mention}")

    # ==========================================================
    #                ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================================

    @commands.command(name="card_drop")
    async def card_drop_prefix(self, ctx):
        await self.card_drop.callback(self, InteractionAdapter(ctx))

    @commands.command(name="card_inventory")
    async def card_inventory_prefix(self, ctx, member: discord.Member = None):
        await self.card_inventory.callback(self, InteractionAdapter(ctx), member)

    @commands.command(name="card_give")
    async def card_give_prefix(self, ctx, member: discord.Member, card_id: str, amount: int = 1):
        await self.card_give.callback(self, InteractionAdapter(ctx), member, card_id, amount)


async def setup(bot):
    await bot.add_cog(Collectibles(bot))
