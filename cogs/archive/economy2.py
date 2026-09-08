import discord
from discord.ext import commands
from discord import app_commands
import random
from typing import Optional, Literal
from db import Database
from ui_components import RavenUI

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    # --- КАРТОЧКА ПРОФИЛЯ ---
    @app_commands.command(name="profile", description="Посмотреть профиль пользователя")
    async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        data = await self.db.get_or_create_user(str(interaction.guild.id), str(target.id))
        
        bal = data.get('balance', 0)
        rep = data.get('reputation', 0)
        lvl = data.get('level', 1)
        xp = data.get('exp', 0)
        msgs = data.get('total_messages', 0)

        next_xp = lvl * 500
        progress = min(int((xp / next_xp) * 10), 10)
        bar = "▰" * progress + "▱" * (10 - progress)

        description = (
            f"**Финансы**\n"
            f"{RavenUI.E_REPLY} Баланс: `{bal}` {RavenUI.E_MONEY}\n"
            f"{RavenUI.E_REPLY} Репутация: `{rep}` ❤️\n\n"
            f"**Активность**\n"
            f"{RavenUI.E_REPLY} Уровень: `{lvl}` (`{xp}/{next_xp}` XP)\n"
            f"{RavenUI.E_REPLY} `{bar}`\n"
            f"{RavenUI.E_REPLY} Сообщений: `{msgs}`"
        )

        embed = RavenUI.create_embed(
            title=f"Карточка — {target.display_name}",
            description=description,
            user=interaction.user,
            thumbnail=target.display_avatar.url
        )
        await interaction.response.send_message(embed=embed)

    # --- ЕЖЕДНЕВНЫЙ БОНУС ---
    @app_commands.command(name="daily", description="Получить ежедневную награду")
    @app_commands.checks.cooldown(1, 86400, key=lambda i: (i.guild_id, i.user.id))
    async def daily(self, interaction: discord.Interaction):
        amount = random.randint(100, 300)
        await self.db.update_user_balance(str(interaction.guild.id), str(interaction.user.id), amount)
        
        embed = RavenUI.create_embed(
            description=f"🎉 **{interaction.user.name}**, вы получили `{amount}` {RavenUI.E_MONEY}!",
            color=RavenUI.SUCCESS,
            user=interaction.user,
            thumbnail=interaction.user.display_avatar.url
        )
        await interaction.response.send_message(embed=embed)

    # --- РЕПУТАЦИЯ ---
    @app_commands.command(name="rep", description="Выдать очко репутации пользователю")
    @app_commands.checks.cooldown(1, 43200, key=lambda i: (i.guild_id, i.user.id))
    async def rep(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == interaction.user.id or member.bot:
            interaction.command.reset_cooldown(interaction)
            return await interaction.response.send_message("❌ Нельзя выдать репутацию самому себе или боту!", ephemeral=True)

        await self.db.create_user(str(interaction.guild.id), str(member.id)) 
        await self.db.conn.execute('UPDATE users SET reputation = reputation + 1 WHERE guild_id = ? AND user_id = ?', (str(interaction.guild.id), str(member.id)))
        await self.db.conn.commit()

        embed = RavenUI.create_embed(
            description=f"❤️ **{interaction.user.name}** повысил репутацию пользователю **{member.mention}**!",
            color=0xff69b4, # Розовый для репутации
            user=interaction.user,
            thumbnail=member.display_avatar.url
        )
        await interaction.response.send_message(embed=embed)

    # --- КОИНФЛИП (ОРЕЛ/РЕШКА) ---
    @app_commands.command(name="coinflip", description="Сыграть в орла или решку")
    async def coinflip(self, interaction: discord.Interaction, amount: int, choice: Literal["орел", "решка"]):
        data = await self.db.get_or_create_user(str(interaction.guild.id), str(interaction.user.id))
        if amount <= 0 or data.get('balance', 0) < amount:
            return await interaction.response.send_message("❌ Недостаточно средств для ставки!", ephemeral=True)

        result = random.choice(["орел", "решка"])
        win = (choice == result)
        
        await self.db.update_user_balance(str(interaction.guild.id), str(interaction.user.id), amount if win else -amount)

        color = RavenUI.SUCCESS if win else RavenUI.ERROR
        res_text = f"**Вы выиграли!**" if win else f"**Вы проиграли!**"
        
        embed = RavenUI.create_embed(
            title="🪙 Монетка",
            description=f"Выпало: **{result.upper()}**\n{RavenUI.E_REPLY} {res_text} `{amount}` {RavenUI.E_MONEY}",
            color=color,
            user=interaction.user,
            thumbnail=interaction.user.display_avatar.url
        )
        await interaction.response.send_message(embed=embed)

    # --- СЛОТЫ ---
    @app_commands.command(name="slots", description="Игровой автомат")
    async def slots(self, interaction: discord.Interaction, amount: int):
        data = await self.db.get_or_create_user(str(interaction.guild.id), str(interaction.user.id))
        if amount <= 0 or data.get('balance', 0) < amount:
            return await interaction.response.send_message("❌ Недостаточно средств!", ephemeral=True)

        emojis = ["🍒", "💎", "🔔", "🍇", "🍎"]
        s = [random.choice(emojis) for _ in range(3)]
        win = (s[0] == s[1] == s[2])
        
        await self.db.update_user_balance(str(interaction.guild.id), str(interaction.user.id), (amount * 5) if win else -amount)

        res_msg = f"🎉 ДЖЕКПОТ! +`{amount * 5}`" if win else f"😢 Проигрыш -`{amount}`"
        embed = RavenUI.create_embed(
            title="🎰 Слоты",
            description=f"**[ {s[0]} | {s[1]} | {s[2]} ]**\n\n{RavenUI.E_REPLY} {res_msg} {RavenUI.E_MONEY}",
            color=RavenUI.SUCCESS if win else RavenUI.MAIN,
            user=interaction.user,
            thumbnail=interaction.user.display_avatar.url
        )
        await interaction.response.send_message(embed=embed)


        # --- РАБОТА ---
    @app_commands.command(name="work", description="Поработать и получить немного монет")
    @app_commands.checks.cooldown(1, 3600, key=lambda i: (i.guild_id, i.user.id))
    async def work(self, interaction: discord.Interaction):
        amount = random.randint(50, 200)
        
        # Список фраз для атмосферы
        jobs = [
            "Вы подметали улицы", 
            "Вы работали курьером в доставке", 
            "Вы написали сложный скрипт на Python", 
            "Вы помогали админу чинить сервер",
            "Вы подрабатывали в местном кафе"
        ]
        job_done = random.choice(jobs)

        await self.db.update_user_balance(str(interaction.guild.id), str(interaction.user.id), amount)
        
        embed = RavenUI.create_embed(
            description=f"💼 {job_done} и заработали `{amount}` {RavenUI.E_MONEY}!",
            color=RavenUI.SUCCESS,
            user=interaction.user,
            thumbnail=interaction.user.display_avatar.url
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Economy(bot))
