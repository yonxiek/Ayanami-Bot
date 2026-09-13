"""Дни рождения: дата задаётся в /menu, поздравление и роль в назначенный день; настройка — в /setup."""

import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import Database
from ui_components import Colors


def _date_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def cog_load(self):
        try:
            self.bg_task = self.bot.loop.create_task(self._birthday_loop())
        except (RuntimeError, AttributeError):
            pass

    async def cog_unload(self):
        if hasattr(self, "bg_task"):
            self.bg_task.cancel()

    async def _birthday_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._check_birthdays()
            except Exception as e:
                print(f"Ошибка дней рождения: {e}")
            await asyncio.sleep(60)

    async def _check_birthdays(self):
        now = datetime.now(timezone.utc)
        date_key = _date_key(now)
        month, day = now.month, now.day

        for guild in self.bot.guilds:
            cfg = await self.db.get_guild_config(str(guild.id))
            channel_id = cfg.get("birthdays_channel_id")
            role_id = cfg.get("birthdays_role_id")
            if not channel_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if not channel:
                continue
            role = guild.get_role(int(role_id)) if role_id else None

            bday_today = await self.db.get_birthdays_for(str(guild.id), month, day)
            today_ids = {row["user_id"] for row in bday_today}

            for row in bday_today:
                member = guild.get_member(int(row["user_id"]))
                if not member:
                    continue
                if row.get("last_announced") == date_key and (not role or role in member.roles):
                    continue
                await self.db.mark_birthday_announced(str(guild.id), row["user_id"], date_key)
                embed = discord.Embed(
                    title="🎂 День рождения!",
                    description=f"🎉 Сегодня празднует {member.mention}!",
                    color=Colors.SUCCESS,
                )
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden:
                        pass

            # Убираем роль у тех, у кого день рождения не сегодня
            if role:
                for member in guild.members:
                    if role in member.roles and str(member.id) not in today_ids:
                        try:
                            await member.remove_roles(role)
                        except discord.Forbidden:
                            pass

    async def set_bday(self, interaction: discord.Interaction, день: int, месяц: int):
        if not (1 <= день <= 31 and 1 <= месяц <= 12):
            return await interaction.response.send_message(
                "❌ Укажи корректные числа: день 1–31, месяц 1–12.", ephemeral=True
            )
        await self.db.set_birthday(str(interaction.guild.id), str(interaction.user.id), день, месяц)
        await interaction.response.send_message(
            f"✅ Дата рождения сохранена: **{день:02d}.{месяц:02d}**", ephemeral=True
        )

    async def remove_bday(self, interaction: discord.Interaction):
        await self.db.remove_birthday(str(interaction.guild.id), str(interaction.user.id))
        await interaction.response.send_message("✅ Дата рождения удалена.", ephemeral=True)

    async def bday_info(self, interaction: discord.Interaction):
        bday = await self.db.get_birthday(str(interaction.guild.id), str(interaction.user.id))
        if not bday:
            return await interaction.response.send_message(
                "🎂 Дата рождения не задана. Нажми **Установить**, чтобы добавить.", ephemeral=True
            )
        await interaction.response.send_message(
            f"🎂 Твоя дата рождения: **{bday['day']:02d}.{bday['month']:02d}**", ephemeral=True
        )

    async def set_bday_channel(self, interaction: discord.Interaction, channel_id: str):
        channel = interaction.guild.get_channel(int(channel_id)) if channel_id.strip().isdigit() else None
        if not channel:
            return await interaction.response.send_message(
                "❌ Канал не найден (нужен ID текстового канала).", ephemeral=True
            )
        config = await self.db.get_guild_config(str(interaction.guild.id))
        config["birthdays_channel_id"] = str(channel.id)
        await self.db.update_guild_config(str(interaction.guild.id), **config)
        await interaction.response.send_message(
            f"✅ Канал поздравлений: {channel.mention}", ephemeral=True
        )

    async def set_bday_role(self, interaction: discord.Interaction, role_id: str):
        role = interaction.guild.get_role(int(role_id)) if role_id.strip().isdigit() else None
        if not role:
            return await interaction.response.send_message(
                "❌ Роль не найдена (нужен ID роли).", ephemeral=True
            )
        config = await self.db.get_guild_config(str(interaction.guild.id))
        config["birthdays_role_id"] = str(role.id)
        await self.db.update_guild_config(str(interaction.guild.id), **config)
        await interaction.response.send_message(
            f"✅ Роль на день рождения: {role.mention}", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Birthdays(bot))