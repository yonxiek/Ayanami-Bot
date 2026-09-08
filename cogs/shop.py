import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
from db import Database
from ui_components import Icons, Colors, AyanamiUI



class ShopView(discord.ui.View):
    def __init__(self, cog, guild_id, user_id, page=0):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.page = page
        self.per_page = 5

    def update_buttons(self, items):
        self.clear_items()
        start = self.page * self.per_page
        end = start + self.per_page
        page_items = items[start:end]

        for item in page_items:
            btn = discord.ui.Button(
                label=f"{item['name']} — {item['price']} {AyanamiUI.E_RP}",
                style=discord.ButtonStyle.primary,
                custom_id=f"shop_buy_{item['item_id']}"
            )
            btn.callback = self.create_buy_callback(item)
            self.add_item(btn)

        if self.page > 0:
            btn = discord.ui.Button(label="◀️ Назад", style=discord.ButtonStyle.gray, custom_id="shop_prev")
            btn.callback = self.prev_page
            self.add_item(btn)

        if end < len(items):
            btn = discord.ui.Button(label="Вперед ▶️", style=discord.ButtonStyle.gray, custom_id="shop_next")
            btn.callback = self.next_page
            self.add_item(btn)

    def create_buy_callback(self, item):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
            await self.cog.execute_buy(interaction, item)
        return callback

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
        self.page -= 1
        items = await self.cog.db.get_shop_items(self.guild_id)
        self.update_buttons(items)
        embed = self.cog.build_shop_embed(items, self.page, self.per_page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
        self.page += 1
        items = await self.cog.db.get_shop_items(self.guild_id)
        self.update_buttons(items)
        embed = self.cog.build_shop_embed(items, self.page, self.per_page)
        await interaction.response.edit_message(embed=embed, view=self)


class Shop(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    def build_shop_embed(self, items, page=0, per_page=5):
        start = page * per_page
        end = start + per_page
        page_items = items[start:end]
        total_pages = max(1, (len(items) + per_page - 1) // per_page)

        desc = ""
        for item in page_items:
            stock_text = f"Осталось: `{item['stock']}`" if item['stock'] >= 0 else "Без ограничений"
            type_emoji = {
                "role": "🎭",
                "custom_role": "🎨",
                "title": "🏷️",
                "box": "🎁",
                "color": "🌈",
                "temp_role": "⏳",
                "lootbox": "🎰",
                "xp_boost": "⚡",
                "nickname_token": "✏️",
            }.get(item['item_type'], "📦")
            desc += (
                f"### {type_emoji} {item['name']}\n"
                f"> {item['description']}\n"
                f"> **Цена:** {item['price']} {AyanamiUI.E_RP} | {stock_text}\n\n"
            )

        if not desc:
            desc = "*Магазин пуст*"

        embed = discord.Embed(
            title=f"Магазин — Страница {page + 1}/{total_pages}",
            description=desc,
            color=discord.Color(0x2b2d31)
        )
        embed.set_footer(text=f"Всего товаров: {len(items)} | Страница {page + 1}/{total_pages}")
        return embed

    @app_commands.command(name="shop", description="Открыть магазин")
    async def shop(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        items = await self.db.get_shop_items(guild_id)

        if not items:
            embed = discord.Embed(
                title="Магазин",
                description="Магазин пуст. Администраторы могут добавить товары через `/setup`.",
                color=Colors.MAIN,
            )
            return await interaction.followup.send(embed=embed)

        view = ShopView(self, guild_id, interaction.user.id)
        view.update_buttons(items)
        embed = self.build_shop_embed(items)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="buy", description="Купить товар по ID")
    @app_commands.describe(item_id="ID товара")
    async def buy(self, interaction: discord.Interaction, item_id: str):
        if not interaction.guild:
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        item = await self.db.get_shop_item(guild_id, item_id)
        if not item:
            return await interaction.followup.send("❌ Товар не найден.", ephemeral=True)

        await self.execute_buy(interaction, item)

    async def execute_buy(self, interaction: discord.Interaction, item: dict):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        user = await self.db.get_or_create_user(guild_id, user_id)
        balance = user.get('balance', 0)

        if balance < item['price']:
            embed = discord.Embed(
                title="Недостаточно средств",
                description=f"Нужно **{item['price']}** {AyanamiUI.E_RP}, у вас **{balance}** {AyanamiUI.E_RP}",
                color=Colors.ERROR,
            )
            embed.set_footer(text="Ayanami System")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if item['stock'] == 0:
            return await interaction.followup.send("❌ Товар закончился.", ephemeral=True)

        success = await self.db.buy_shop_item(guild_id, user_id, item['item_id'])
        if not success:
            return await interaction.followup.send("❌ Ошибка при покупке.", ephemeral=True)

        if item['item_type'] == 'role' and item.get('role_id'):
            role = interaction.guild.get_role(int(item['role_id']))
            if role:
                try:
                    await interaction.user.add_roles(role, reason=f"Покупка: {item['name']}")
                except discord.Forbidden:
                    pass

        elif item['item_type'] == 'temp_role' and item.get('role_id'):
            import json
            from datetime import datetime, timezone, timedelta
            meta = json.loads(item.get('metadata', '{}'))
            hours = meta.get('hours', 24)
            role = interaction.guild.get_role(int(item['role_id']))
            if role:
                expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
                try:
                    await interaction.user.add_roles(role, reason=f"Покупка: {item['name']} ({hours}ч)")
                    await self.db.add_temporary_role(guild_id, user_id, item['role_id'], expires)
                except discord.Forbidden:
                    pass

        elif item['item_type'] == 'title':
            import json
            meta = json.loads(item.get('metadata', '{}'))
            title_text = meta.get('title', item['name'])
            emoji = meta.get('emoji', '🏷️')
            from datetime import datetime, timezone
            await self.db.conn.execute(
                'INSERT OR REPLACE INTO user_titles (guild_id, user_id, title, emoji, active) VALUES (?, ?, ?, ?, 0)',
                (guild_id, user_id, title_text, emoji)
            )
            await self.db.conn.commit()

        elif item['item_type'] == 'lootbox':
            import random, json
            meta = json.loads(item.get('metadata', '{}'))
            min_reward = meta.get('min_reward', 50)
            max_reward = meta.get('max_reward', 500)
            reward = random.randint(min_reward, max_reward)
            await self.db.update_user_balance(guild_id, user_id, reward)
            embed = discord.Embed(
                title="Открыт лутбокс!",
                description=f"Вы получили **{reward}** {AyanamiUI.E_RP} из **{item['name']}**!",
                color=Colors.SUCCESS,
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Ayanami System")
            return await interaction.followup.send(embed=embed)

        elif item['item_type'] == 'xp_boost':
            import json
            from datetime import datetime, timezone, timedelta
            meta = json.loads(item.get('metadata', '{}'))
            multiplier = meta.get('multiplier', 1.5)
            hours = meta.get('hours', 24)
            expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
            await self.db.add_xp_boost(guild_id, user_id, multiplier, expires)

        elif item['item_type'] == 'nickname_token':
            pass

        embed = discord.Embed(
            title="Покупка успешна",
            description=f"Вы купили **{item['name']}** за **{item['price']}** {AyanamiUI.E_RP}!",
            color=Colors.SUCCESS,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="inventory", description="Ваш инвентарь")
    async def inventory(self, interaction: discord.Interaction, member: discord.Member = None):
        if not interaction.guild:
            return
        await interaction.response.defer()

        target = member or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(target.id)

        items = await self.db.get_user_inventory(guild_id, user_id)
        if not items:
            embed = discord.Embed(
                title="Инвентарь",
                description="Ваш инвентарь пуст.",
                color=Colors.MAIN,
            )
            return await interaction.followup.send(embed=embed)

        desc = ""
        for item in items:
            type_emoji = {
                "role": "🎭",
                "title": "🏷️",
                "box": "🎁",
                "color": "🌈",
                "temp_role": "⏳",
                "lootbox": "🎰",
                "xp_boost": "⚡",
                "nickname_token": "✏️",
            }.get(item.get('item_type'), "📦")
            desc += f"> {type_emoji} **{item['name']}** x{item['quantity']}\n"

        embed = discord.Embed(
            title=f"Инвентарь — {target.display_name}",
            description=desc,
            color=Colors.MAIN,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Shop(bot))
