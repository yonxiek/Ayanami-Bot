import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
from typing import Optional, Literal
from datetime import datetime, timezone, timedelta
from db import Database

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.items = [] # Кэш товаров

    async def cog_load(self):
        self.bot.loop.create_task(self.load_items())
        self.bot.loop.create_task(self.check_expired_privileges_loop())

    async def load_items(self):
        cursor = await self.db.conn.execute('SELECT id, data FROM shop_items')
        rows = await cursor.fetchall()
        self.items = []
        for row in rows:
            try:
                self.items.append(json.loads(row['data']))
            except Exception:
                pass

    # Функция сохранения с учетом guild_id
    async def save_item(self, db_id: str, item: dict):
        await self.db.conn.execute('INSERT OR REPLACE INTO shop_items (id, data) VALUES (?, ?)', (db_id, json.dumps(item, ensure_ascii=False)))
        await self.db.conn.commit()
        
        # Обновляем кэш
        for i, it in enumerate(self.items):
            if it.get('id') == item['id'] and it.get('guild_id') == item['guild_id']:
                self.items[i] = item
                break
        else: 
            self.items.append(item)

    # Удаление с учетом guild_id
    async def delete_item(self, db_id: str, item_id: str, guild_id: str):
        await self.db.conn.execute('DELETE FROM shop_items WHERE id = ?', (db_id,))
        await self.db.conn.commit()
        self.items = [it for it in self.items if not (it.get('id') == item_id and it.get('guild_id') == guild_id)]

    # Получение товара конкретного сервера
    def get_item(self, item_id: str, guild_id: str) -> Optional[dict]:
        for item in self.items:
            if item.get('id') == item_id and item.get('guild_id') == guild_id: 
                return item.copy()
        return None

    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        choices = []
        guild_id = str(interaction.guild.id)
        for item in self.items:
            # Игнорируем товары других серверов
            if not item.get('enabled', True) or item.get('guild_id') != guild_id: 
                continue
            if current.lower() in item['name'].lower() or current.lower() in item['id'].lower():
                choices.append(app_commands.Choice(name=f"{item['name']} ({item['price']} монет)", value=item['id']))
        return choices[:25]

    @app_commands.command(name="shop", description="Посмотреть магазин (меню с кнопками)")
    async def shop_slash(self, interaction: discord.Interaction):
        await self._logic_shop_menu(interaction)

    @app_commands.command(name="buy", description="Купить товар по ID")
    @app_commands.autocomplete(item_id=item_autocomplete)
    async def buy_slash(self, interaction: discord.Interaction, item_id: str):
        await self._logic_buy(interaction, item_id)

   # @app_commands.command(name="shopadd", description="Добавить новый товар в магазин (Админ)")
    @app_commands.default_permissions(administrator=True)
    async def shopadd_slash(self, interaction: discord.Interaction, item_id: str, name: str, description: str, price: int, item_type: Literal["role", "custom_role"], role: Optional[discord.Role] = None, enabled: bool = True):
        guild_id = str(interaction.guild.id)
        if self.get_item(item_id, guild_id): 
            return await interaction.response.send_message(f"Товар `{item_id}` уже существует.", ephemeral=True)
        if item_type == "role" and not role: 
            return await interaction.response.send_message("Для этого типа нужна роль.", ephemeral=True)

        db_id = f"{guild_id}_{item_id}"
        new_item = {
            "id": item_id, "guild_id": guild_id, "name": name, "description": description, 
            "price": price, "item_type": item_type, "enabled": enabled
        }
        if role: new_item["role_id"] = role.id

        await self.save_item(db_id, new_item)
        await interaction.response.send_message(f"Товар `{name}` добавлен.", ephemeral=True)

  #  @app_commands.command(name="shopremove", description="Удалить товар из магазина (Админ)")
    @app_commands.autocomplete(item_id=item_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def shopremove_slash(self, interaction: discord.Interaction, item_id: str):
        guild_id = str(interaction.guild.id)
        if not self.get_item(item_id, guild_id): 
            return await interaction.response.send_message(f"Товар `{item_id}` не найден.", ephemeral=True)
        
        db_id = f"{guild_id}_{item_id}"
        await self.delete_item(db_id, item_id, guild_id)
        await interaction.response.send_message(f"Товар `{item_id}` удален.", ephemeral=True)

    async def _send_msg(self, context, text=None, embed=None, view=None, ephemeral=True):
        if isinstance(context, discord.Interaction):
            if not context.response.is_done():
                await context.response.send_message(content=text, embed=embed, view=view, ephemeral=ephemeral)
            else:
                await context.followup.send(content=text, embed=embed, view=view, ephemeral=ephemeral)

    async def _logic_shop_menu(self, context):
        user_id = context.user.id if isinstance(context, discord.Interaction) else context.author.id
        guild_id = str(context.guild.id)
        
        # Берем товары ТОЛЬКО этого сервера
        enabled_items = [item for item in self.items if item.get('enabled', True) and item.get('guild_id') == guild_id]
        
        if not enabled_items: 
            return await self._send_msg(context, "В магазине пока нет товаров.")

        view = PaginatedShopView(self, user_id, enabled_items)
        embed = discord.Embed(title="Магазин сервера", description="Выберите товар для покупки:", color=discord.Color.blurple())
        await self._send_msg(context, embed=embed, view=view)

    async def _logic_buy(self, context, item_id):
        guild_id = str(context.guild.id)
        item = self.get_item(item_id, guild_id)
        
        if not item: 
            return await self._send_msg(context, "Товар с таким ID не найден на этом сервере.")

        class DummyInteraction:
            def __init__(self, user, guild):
                self.user = user
                self.guild = guild
        dummy = DummyInteraction(context.user, context.guild)

        ok, msg = await self.check_prerequisites(dummy, item)
        if not ok: return await self._send_msg(context, msg)

        if item['item_type'] == 'custom_role':
            if isinstance(context, discord.Interaction):
                await context.response.send_modal(CustomRoleModal(self, item))
            else:
                await self._send_msg(context, "Кастомные роли можно покупать только через слэш-команду `/buy`.")
        else:
            if isinstance(context, discord.Interaction): await context.response.defer(ephemeral=True)
            success = await self.execute_purchase(dummy, item)
            if success: await self._send_msg(context, f"🎉 Вы успешно купили **{item['name']}**!")

    async def check_prerequisites(self, interaction, item: dict) -> tuple[bool, str]:
        if not item.get('enabled', True): return False, "Этот товар временно недоступен."
        
        economy = self.bot.get_cog('Economy')
        if not economy: return False, "Экономическая система временно отключена."
        
        user_data = await economy.get_user_data(str(interaction.guild.id), str(interaction.user.id))
        balance = user_data.get("balance", 0)
        price = item['price']
        
        if balance < price: return False, f"Недостаточно монет. Нужно {price}, у вас {balance}."
        return True, "OK"

    async def execute_purchase(self, interaction, item: dict, **kwargs):
        guild_id, user_id = str(interaction.guild.id), str(interaction.user.id)
        price = item['price']

        try:
            await self.db.conn.execute('''
                UPDATE users SET balance = balance - ?, total_spent = total_spent + ?
                WHERE guild_id = ? AND user_id = ?
            ''', (price, price, guild_id, user_id))

            cursor = await self.db.conn.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
            row = await cursor.fetchone()
            if row and row[0] < 0:
                await self.db.conn.rollback()
                return False

            await self.db.conn.execute('''
                INSERT OR REPLACE INTO purchases (guild_id, user_id, item_id, purchase_date)
                VALUES (?, ?, ?, ?)
            ''', (guild_id, user_id, item['id'], datetime.now(timezone.utc).isoformat()))
            await self.db.conn.commit()
        except Exception:
            await self.db.conn.execute("ROLLBACK")
            return False

        item_type = item['item_type']
        try:
            if item_type == 'role':
                role = interaction.guild.get_role(item.get('role_id'))
                if role: await interaction.user.add_roles(role, reason=f"Покупка: {item['name']}")
                return True
            elif item_type == 'custom_role':
                name = kwargs.get('name')
                color_hex = kwargs.get('color', '#99AAB5')
                color = discord.Color(int(color_hex[1:], 16)) if color_hex.startswith('#') else discord.Color.default()
                try:
                    color = discord.Color(int(color_hex[1:], 16)) if color_hex.startswith('#') else discord.Color.default()
                except ValueError:
                    color = discord.Color.default()
                new_role = await interaction.guild.create_role(name=name[:100], color=color, reason="Покупка кастомной роли")
                await interaction.user.add_roles(new_role)
                return True
        except Exception:
            return False

    async def check_expired_privileges_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.now(timezone.utc)
            privileges = await self.db.get_all_active_privileges()
            for priv in privileges:
                if datetime.fromisoformat(priv['expires']) <= now:
                    guild = self.bot.get_guild(int(priv['guild_id']))
                    if guild:
                        member = guild.get_member(int(priv['user_id']))
                        role = guild.get_role(int(priv['role_id']))
                        if member and role:
                            try: await member.remove_roles(role, reason="Истек срок привилегии")
                            except: pass
                    await self.db.remove_active_privilege(priv['guild_id'], priv['user_id'], priv['item_id'])
            await asyncio.sleep(60)

class PaginatedShopView(discord.ui.View):
    def __init__(self, cog, user_id, items, page=0):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.items = items
        self.page = page
        self.per_page = 20
        self.max_page = max(0, (len(items) - 1) // self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        page_items = self.items[self.page * self.per_page : (self.page + 1) * self.per_page]

        for item in page_items: self.add_item(ShopItemButton(self.cog, item, self.user_id))

        if self.max_page > 0:
            if self.page > 0: self.add_item(PageButton("Пред.", self.page - 1, self.cog, self.user_id, self.items))
            if self.page < self.max_page: self.add_item(PageButton("След.", self.page + 1, self.cog, self.user_id, self.items))

class ShopItemButton(discord.ui.Button):
    def __init__(self, cog, item, user_id):
        self.cog, self.item, self.user_id = cog, item, user_id
        super().__init__(label=f"{item['name']} - {item['price']} монет", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
        ok, msg = await self.cog.check_prerequisites(interaction, self.item)
        if not ok: return await interaction.response.send_message(msg, ephemeral=True)
        
        if self.item['item_type'] == 'custom_role': await interaction.response.send_modal(CustomRoleModal(self.cog, self.item))
        else:
            await interaction.response.defer(ephemeral=True)
            if await self.cog.execute_purchase(interaction, self.item):
                await interaction.followup.send(f"Вы успешно купили **{self.item['name']}**!", ephemeral=True)

class PageButton(discord.ui.Button):
    def __init__(self, label, target_page, cog, user_id, items):
        super().__init__(label=label, style=discord.ButtonStyle.gray)
        self.target_page, self.cog, self.user_id, self.items = target_page, cog, user_id, items

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        view = PaginatedShopView(self.cog, self.user_id, self.items, self.target_page)
        await interaction.response.edit_message(view=view)

class CustomRoleModal(discord.ui.Modal, title="Создание кастомной роли"):
    name = discord.ui.TextInput(label="Название роли", max_length=100)
    color = discord.ui.TextInput(label="Цвет (HEX, например #FF0000)", required=False, max_length=7)

    def __init__(self, cog, item):
        super().__init__()
        self.cog, self.item = cog, item

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ok, msg = await self.cog.check_prerequisites(interaction, self.item)
        if not ok: return await interaction.followup.send(msg, ephemeral=True)
        if await self.cog.execute_purchase(interaction, self.item, name=str(self.name), color=str(self.color)):
            await interaction.followup.send(f"Кастомная роль **{self.name}** создана!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Shop(bot))
