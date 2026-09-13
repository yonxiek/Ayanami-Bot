"""Личные задачи: создание, список, завершение через /menu."""

import discord
from discord.ext import commands

from db import Database
from ui_components import Colors


class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def task_create(self, interaction: discord.Interaction, title: str):
        title = title.strip()
        if not title:
            return await interaction.response.send_message("❌ Задача не может быть пустой.", ephemeral=True)
        if len(title) > 120:
            return await interaction.response.send_message(
                "❌ Название задачи слишком длинное (до 120 символов).", ephemeral=True
            )
        task_id = await self.db.add_user_task(str(interaction.guild.id), str(interaction.user.id), title)
        await interaction.response.send_message(f"✅ Задача `#{task_id}` создана: **{title}**", ephemeral=True)

    async def task_list(self, interaction: discord.Interaction):
        tasks = await self.db.get_user_tasks(str(interaction.guild.id), str(interaction.user.id))
        if not tasks:
            return await interaction.response.send_message(
                "📋 Задач пока нет. Создайте первую через **➕ Новая**!", ephemeral=True
            )
        open_count = sum(1 for t in tasks if t["status"] == "open")
        lines = []
        for t in tasks:
            mark = "🟢" if t["status"] == "open" else "✅"
            lines.append(f"{mark} `#{t['task_id']}` **{t['title']}**")
        embed = discord.Embed(
            title=f"📋 Задачи — {interaction.user.display_name}",
            description="\n".join(lines),
            color=Colors.MAIN,
        )
        embed.set_footer(text=f"Всего: {len(tasks)} • открыто: {open_count}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def task_complete(self, interaction: discord.Interaction, task_id: int):
        ok = await self.db.complete_user_task(str(interaction.guild.id), str(interaction.user.id), task_id)
        if not ok:
            return await interaction.response.send_message(
                "❌ Задача не найдена или уже завершена.", ephemeral=True
            )
        await interaction.response.send_message(f"✅ Задача `#{task_id}` завершена! 🎉", ephemeral=True)

    async def task_delete(self, interaction: discord.Interaction, task_id: int):
        ok = await self.db.delete_user_task(str(interaction.guild.id), str(interaction.user.id), task_id)
        if not ok:
            return await interaction.response.send_message("❌ Задача не найдена.", ephemeral=True)
        await interaction.response.send_message(f"🗑️ Задача `#{task_id}` удалена.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Tasks(bot))