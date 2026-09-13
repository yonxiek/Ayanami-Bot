"""Дни рождения: /setbday, авто-поздравление и роль в назначенный день."""

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
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

    @app_commands.command(name="setbday", description="Сохранить свою дату рождения (ДД ММ)")
    async def setbday_cmd(self, interaction: discord.Interaction, день: int, месяц: int):
        if not (1 <= день <= 31 and 1 <= месяц <= 12):
            return await interaction.response.send_message(
                "❌ Укажи корректные числа: день 1–31, месяц 1–12.", ephemeral=True
            )
        await self.db.set_birthday(str(interaction.guild.id), str(interaction.user.id), день, месяц)
        await interaction.response.send_message(
            f"✅ Дата рождения сохранена: **{день:02d}.{месяц:02d}**", ephemeral=True
        )

    @app_commands.command(name="removebday", description="Удалить свою дату рождения")
    async def removebday_cmd(self, interaction: discord.Interaction):
        await self.db.remove_birthday(str(interaction.guild.id), str(interaction.user.id))
        await interaction.response.send_message("✅ Дата рождения удалена.", ephemeral=True)

    @app_commands.command(name="bdaychannel", description="Канал для поздравлений (роль модератора)")
    @app_commands.default_permissions(manage_channels=True)
    async def bdaychannel_cmd(self, interaction: discord.Interaction, канал: discord.TextChannel):
        config = await self.db.get_guild_config(str(interaction.guild.id))
        config["birthdays_channel_id"] = str(канал.id)
        await self.db.update_guild_config(str(interaction.guild.id), **config)
        await interaction.response.send_message(
            f"✅ Канал поздравлений: {канал.mention}", ephemeral=True
        )

    @app_commands.command(name="bdayrole", description="Роль на день рождения (роль модератора)")
    @app_commands.default_permissions(manage_channels=True)
    async def bdayrole_cmd(self, interaction: discord.Interaction, роль: discord.Role):
        config = await self.db.get_guild_config(str(interaction.guild.id))
        config["birthdays_role_id"] = str(роль.id)
        await self.db.update_guild_config(str(interaction.guild.id), **config)
        await interaction.response.send_message(
            f"✅ Роль на день рождения: {роль.mention}", ephemeral=True
        )

    @commands.command(name="setbday")
    async def setbday_prefix(self, ctx, день: int, месяц: int):
        from prefix_adapter import InteractionAdapter
        await self.setbday_cmd.callback(self, InteractionAdapter(ctx), день, месяц)


async def setup(bot):
    await bot.add_cog(Birthdays(bot))