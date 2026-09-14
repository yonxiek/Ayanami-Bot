
import random

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from cogs.lottery import _format_ends as _lottery_ends
from ui_components import AyanamiUI, Colors


class ShopView(discord.ui.View):
    def __init__(self, cog, guild_id, user_id, page=0):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.page = page
        self.per_page = 5

    def update_buttons(self, items, cases, lottery=None):
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

        if cases:
            sel = discord.ui.Select(
                placeholder="🎁 Открыть кейс...",
                min_values=1,
                max_values=1,
                row=2,
                options=[
                    discord.SelectOption(
                        label=f"{c['emoji']} {c['name']} — {c['price']} {AyanamiUI.E_RP}",
                        value=str(c['id']),
                    )
                    for c in cases[:25]
                ],
            )
            sel.callback = self.case_callback
            self.add_item(sel)

        if lottery is not None:
            lot_options = [
                discord.SelectOption(label="Статус лотереи", value="lottery_status", emoji="📊"),
            ]
            if lottery.get("status") == "active":
                lot_options.append(discord.SelectOption(label="Купить билет", value="lottery_buy", emoji="🎟"))
            lot_sel = discord.ui.Select(
                placeholder="🎟 Лотерея...",
                min_values=1,
                max_values=1,
                row=3,
                options=lot_options,
            )
            lot_sel.callback = self.lottery_callback
            self.add_item(lot_sel)

        if self.page > 0:
            btn = discord.ui.Button(label="◀️ Назад", style=discord.ButtonStyle.gray, custom_id="shop_prev", row=1)
            btn.callback = self.prev_page
            self.add_item(btn)

        if end < len(items):
            btn = discord.ui.Button(label="Вперед ▶️", style=discord.ButtonStyle.gray, custom_id="shop_next", row=1)
            btn.callback = self.next_page
            self.add_item(btn)

    def create_buy_callback(self, item):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
            await self.cog.execute_buy(interaction, item)
        return callback

    async def case_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        case_id = int(interaction.data["values"][0])
        await self.cog.execute_open_case(interaction, case_id)

    async def lottery_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
        val = interaction.data["values"][0]
        cog = interaction.client.get_cog("Lottery")
        if not cog:
            return await interaction.response.send_message("❌ Модуль «Лотерея» выключен.", ephemeral=True)
        if val == "lottery_buy":
            return await interaction.response.send_modal(LotteryBuyModal())
        await interaction.response.defer(ephemeral=True)
        await cog.lottery_status(interaction)

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
        self.page -= 1
        items = await self.cog.db.get_shop_items(self.guild_id)
        cases = await self.cog._get_cases(self.guild_id)
        lottery = await self.cog._get_lottery(self.guild_id)
        self.update_buttons(items, cases, lottery)
        embed = self.cog.build_shop_embed(items, cases, self.page, self.per_page, lottery)
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Не ваше меню.", ephemeral=True)
        self.page += 1
        items = await self.cog.db.get_shop_items(self.guild_id)
        cases = await self.cog._get_cases(self.guild_id)
        lottery = await self.cog._get_lottery(self.guild_id)
        self.update_buttons(items, cases, lottery)
        embed = self.cog.build_shop_embed(items, cases, self.page, self.per_page, lottery)
        await interaction.response.edit_message(embed=embed, view=self)


class LotteryBuyModal(discord.ui.Modal, title="🎟 Купить билеты"):
    count = discord.ui.TextInput(
        label="Количество билетов", placeholder="1", max_length=4, default="1"
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Lottery")
        if not cog:
            return await interaction.response.send_message("❌ Модуль «Лотерея» выключен.", ephemeral=True)
        try:
            count = int(self.count.value)
        except ValueError:
            count = 1
        await interaction.response.defer(ephemeral=True)
        await cog.lottery_buy(interaction, count)


class Shop(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    def build_shop_embed(self, items, cases=None, page=0, per_page=5, lottery=None):
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
                "guild_xp_boost": "🏛️",
                "nickname_token": "✏️",
                "card": "🃏",
            }.get(item['item_type'], "📦")
            desc += (
                f"### {type_emoji} {item['name']}\n"
                f"> {item['description']}\n"
                f"> **Цена:** {item['price']} {AyanamiUI.E_RP} | {stock_text}\n\n"
            )

        if cases:
            case_lines = [f"> {c['emoji']} **{c['name']}** — {c['price']} {AyanamiUI.E_RP}" for c in cases]
            desc += "### 🎁 Кейсы\n" + "\n".join(case_lines) + "\n\n*Открыть можно через меню ниже*"

        if lottery is not None and lottery.get("status") == "active":
            desc += (
                f"\n### 🎟 Лотерея\n"
                f"> 💸 Билет: **{lottery['ticket_price']}** {AyanamiUI.E_RP} • 💰 Фонд: **{lottery['prize_pool']}**\n"
                f"> ⏳ Розыгрыш: {_lottery_ends(lottery['ends_at'])}\n"
                f"*Билеты — через меню ниже*"
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

    async def _get_cases(self, guild_id: str) -> list:
        cursor = await self.db.conn.execute(
            'SELECT id, name, emoji, price, enabled FROM cases WHERE guild_id = ? AND enabled = 1 ORDER BY id',
            (guild_id,))
        return [dict(row) for row in await cursor.fetchall()]

    async def _get_lottery(self, guild_id: str) -> dict | None:
        return await self.db.get_lottery(guild_id)

    async def _get_case(self, guild_id: str, case_id: int) -> dict | None:
        cursor = await self.db.conn.execute(
            'SELECT * FROM cases WHERE guild_id = ? AND id = ?', (guild_id, case_id))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _get_case_items(self, guild_id: str, case_id: int) -> list:
        cursor = await self.db.conn.execute(
            'SELECT * FROM case_items WHERE guild_id = ? AND case_id = ?', (guild_id, case_id))
        return [dict(row) for row in await cursor.fetchall()]

    async def _roll_case_item(self, guild_id: str, case_id: int) -> dict | None:
        items = await self._get_case_items(guild_id, case_id)
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

    async def execute_open_case(self, interaction: discord.Interaction, case_id: int):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        case = await self._get_case(guild_id, case_id)
        if not case or not case['enabled']:
            return await interaction.followup.send(
                embed=discord.Embed(color=Colors.ERROR, description="❌ Кейс не найден."), ephemeral=True)

        user = await self.db.get_or_create_user(guild_id, user_id)
        if user.get('balance', 0) < case['price']:
            return await interaction.followup.send(
                embed=discord.Embed(color=Colors.ERROR,
                                    description=f"❌ Недостаточно монеток. Нужно **{case['price']}**, у вас **{user.get('balance', 0)}**."),
                ephemeral=True)

        item = await self._roll_case_item(guild_id, case_id)
        await self.db.update_user_balance(guild_id, user_id, -case['price'])
        await self.db.conn.execute(
            "UPDATE users SET cases_opened = COALESCE(cases_opened, 0) + 1 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id))
        await self.db.conn.commit()

        cursor = await self.db.conn.execute(
            "SELECT COALESCE(cases_opened, 0) AS opened FROM users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id))
        opened_row = await cursor.fetchone()
        opened = opened_row["opened"] if opened_row else 0
        try:
            from cogs.achievements import award_achievement
            await award_achievement(self.db, guild_id, user_id, "case_open_1", interaction.user)
            if opened >= 10:
                await award_achievement(self.db, guild_id, user_id, "case_open_10", interaction.user)
        except Exception:
            pass

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
                from datetime import datetime, timezone
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

    @app_commands.command(name="shop", description="Открыть магазин")
    async def shop(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        items = await self.db.get_shop_items(guild_id)
        cases = await self._get_cases(guild_id)
        lottery = await self._get_lottery(guild_id)

        if not items and not cases and not (lottery and lottery["status"] == "active"):
            embed = discord.Embed(
                title="Магазин",
                description="Магазин пуст. Администраторы могут добавить товары и кейсы через `/setup`.",
                color=Colors.MAIN,
            )
            return await interaction.followup.send(embed=embed)

        view = ShopView(self, guild_id, interaction.user.id)
        view.update_buttons(items, cases, lottery)
        embed = self.build_shop_embed(items, cases, lottery=lottery)
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

        try:
            from cogs.achievements import award_achievement
            await award_achievement(self.db, guild_id, user_id, "first_buy", interaction.user)
        except Exception:
            pass

        if item['item_type'] == 'role' and item.get('role_id'):
            role = interaction.guild.get_role(int(item['role_id']))
            if role:
                try:
                    await interaction.user.add_roles(role, reason=f"Покупка: {item['name']}")
                except discord.Forbidden:
                    pass

        elif item['item_type'] == 'temp_role' and item.get('role_id'):
            import json
            from datetime import datetime, timedelta, timezone
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
            import json
            import random
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
            from datetime import datetime, timedelta, timezone
            meta = json.loads(item.get('metadata', '{}'))
            multiplier = meta.get('multiplier', 1.5)
            hours = meta.get('hours', 24)
            expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
            await self.db.add_xp_boost(guild_id, user_id, multiplier, expires)

        elif item['item_type'] == 'nickname_token':
            pass

        elif item['item_type'] == 'guild_xp_boost':
            import json
            from datetime import datetime, timedelta, timezone
            meta = json.loads(item.get('metadata', '{}'))
            multiplier = meta.get('multiplier', 1.5)
            hours = meta.get('hours', 2)
            expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
            config = await self.db.get_guild_config(guild_id)
            config['guild_xp_boost'] = {'multiplier': multiplier, 'expires_at': expires}
            await self.db.update_guild_config(guild_id, **config)
            embed = discord.Embed(
                title="🏛️ Гильдейский буст XP!",
                description=(
                    f"**{item['name']}** активирован на весь сервер!\n"
                    f"Множитель XP: **x{multiplier}** на **{hours} ч** для всех участников."
                ),
                color=Colors.SUCCESS,
            )
            embed.set_thumbnail(
                url=interaction.guild.icon.url if interaction.guild.icon else interaction.user.display_avatar.url
            )
            embed.set_footer(text="Ayanami System")
            return await interaction.followup.send(embed=embed)

        elif item['item_type'] == 'card':
            meta = item.get('metadata', {})
            card_id = meta.get('card_id')
            if card_id:
                bought = await self.db.buy_card(guild_id, user_id, card_id, item['price'])
                if not bought:
                    return await interaction.followup.send("❌ Карточка недоступна.", ephemeral=True)
                card = await self.db.get_card(guild_id, card_id)
                r_info = {
                    "common": {"label": "Обычная", "emoji": "⚪"},
                    "rare": {"label": "Редкая", "emoji": "🔵"},
                    "epic": {"label": "Эпическая", "emoji": "🟣"},
                    "legendary": {"label": "Легендарная", "emoji": "🟡"},
                }.get(card['rarity'] if card else 'common', {"label": "", "emoji": "🃏"})
                embed = discord.Embed(
                    title="Покупка успешна",
                    description=f"Вы купили карточку **{card['name'] if card else item['name']}** {r_info['emoji']} за **{item['price']}** {AyanamiUI.E_RP}!",
                    color=Colors.SUCCESS,
                )
                embed.set_footer(text="Ayanami System")
                return await interaction.followup.send(embed=embed)

        embed = discord.Embed(
            title="Покупка успешна",
            description=f"Вы купили **{item['name']}** за **{item['price']}** {AyanamiUI.E_RP}!",
            color=Colors.SUCCESS,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="inventory", description="Ваш инвентарь: баланс, карточки, товары и титулы")
    @app_commands.describe(member="Участник, чей инвентарь показать")
    async def inventory(self, interaction: discord.Interaction, member: discord.Member = None):
        if not interaction.guild:
            return
        await interaction.response.defer()

        target = member or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(target.id)

        user = await self.db.get_or_create_user(guild_id, user_id)
        balance = user.get("balance", 0)
        opened_cases = user.get("cases_opened", 0)

        lines = [f"🪙 **Баланс:** {balance} {AyanamiUI.E_RP}"]

        cursor = await self.db.conn.execute(
            "SELECT cc.card_id, cc.name, cc.emoji, cc.rarity, uc.quantity "
            "FROM user_cards uc JOIN collectible_cards cc ON uc.card_id = cc.card_id "
            "AND uc.guild_id = cc.guild_id "
            "WHERE uc.guild_id = ? AND uc.user_id = ? ORDER BY uc.obtained_at",
            (guild_id, user_id))
        cards = await cursor.fetchall()
        if cards:
            cards_lines = []
            for c in cards:
                cards_lines.append(f"{c['emoji']} **{c['name']}** x{c['quantity']}`{c['rarity']}`")
            lines.append(f"\n🃏 **Карточки ({len(cards)}):**\n> " + "\n> ".join(cards_lines[:20]))
            if len(cards) > 20:
                lines.append(f"> …и ещё {len(cards) - 20}")

        items = await self.db.get_user_inventory(guild_id, user_id)
        if items:
            type_emoji = {
                "role": "🎭", "title": "🏷️", "box": "🎁", "color": "🌈",
                "temp_role": "⏳", "lootbox": "🎰", "xp_boost": "⚡",
                "nickname_token": "✏️",
            }
            item_lines = []
            for item in items:
                item_lines.append(f"{type_emoji.get(item.get('item_type'), '📦')} **{item['name']}** x{item['quantity']}")
            lines.append("\n🎒 **Товары:**\n> " + "\n> ".join(item_lines[:15]))
            if len(item_lines) > 15:
                lines.append(f"> …и ещё {len(item_lines) - 15}")

        titles = await self.db.get_user_titles(guild_id, user_id)
        if titles:
            title_lines = []
            for t in titles:
                active = " ✅" if t.get("active") else ""
                title_lines.append(f"{t.get('emoji', '🏷️')} {t['title']}{active}")
            lines.append("\n🏷️ **Титулы:**\n> " + "\n> ".join(title_lines[:20]))

        if opened_cases:
            lines.append(f"\n🎁 **Открыто кейсов:** {opened_cases}")

        embed = discord.Embed(
            title="Инвентарь",
            description=(f"{target.mention}\n" + "\n".join(lines)) if items or cards or titles else f"{lines[0]}\n\nПусто, но это исправимо!",
            color=Colors.MAIN,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Ayanami System")
        await interaction.followup.send(
            embed=embed, allowed_mentions=discord.AllowedMentions(users=False, everyone=False, roles=False)
        )


    @commands.command(name="shop")
    async def shop_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.shop.callback(self, InteractionAdapter(ctx))

    @commands.command(name="buy")
    async def buy_prefix(self, ctx, item_id: str):
        from prefix_adapter import InteractionAdapter
        await self.buy.callback(self, InteractionAdapter(ctx), item_id)

    @commands.command(name="inventory")
    async def inventory_prefix(self, ctx, member: discord.Member = None):
        from prefix_adapter import InteractionAdapter
        await self.inventory.callback(self, InteractionAdapter(ctx), member)

async def setup(bot):
    await bot.add_cog(Shop(bot))
