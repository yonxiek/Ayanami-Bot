import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

from cogs.achievements import award_achievement
from db import Database
from ui_components import Colors


class ClanCreateModal(discord.ui.Modal, title="Создать клан"):
    name = discord.ui.TextInput(label="Название клана", placeholder="Например: Пламя", max_length=30, required=True)
    tag = discord.ui.TextInput(label="Тег (сокращение)", placeholder="Например: ПЛМ", max_length=5, required=True)
    description = discord.ui.TextInput(label="Описание", placeholder="Кратко о клане...", max_length=200, required=False)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        # Проверка: уже в клане?
        cursor = await self.cog.db.conn.execute(
            "SELECT clan_id FROM clan_members WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        if await cursor.fetchone():
            return await interaction.followup.send("❌ Вы уже состоите в клане.")

        name = self.name.value.strip()
        tag = self.tag.value.strip().upper()

        # Проверка уникальности
        cursor = await self.cog.db.conn.execute(
            "SELECT id FROM clans WHERE guild_id = ? AND (name = ? OR tag = ?)", (guild_id, name, tag)
        )
        if await cursor.fetchone():
            return await interaction.followup.send("❌ Клан с таким названием или тегом уже существует.")

        await self.cog.db.conn.execute(
            "INSERT INTO clans (guild_id, name, tag, leader_id, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, name, tag, user_id, self.description.value or "", datetime.now(timezone.utc).isoformat())
        )
        await self.cog.db.conn.commit()

        cursor = await self.cog.db.conn.execute(
            "SELECT id FROM clans WHERE guild_id = ? AND leader_id = ?", (guild_id, user_id)
        )
        row = await cursor.fetchone()
        clan_id = row["id"]

        await self.cog.db.conn.execute(
            "INSERT INTO clan_members (guild_id, user_id, clan_id, role, joined_at) VALUES (?, ?, ?, 'leader', ?)",
            (guild_id, user_id, clan_id, datetime.now(timezone.utc).isoformat())
        )
        await self.cog.db.conn.commit()

        embed = discord.Embed(
            title=f"⚔️ Клан «{name}» [{tag}] создан!",
            description=f"**Лидер:** {interaction.user.mention}\n**Описание:** {self.description.value or 'Нет описания'}",
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed)
        await award_achievement(self.cog.db, guild_id, user_id, "clan_create", interaction.user)
        await self._apply_clan_tag(interaction.user, tag)


class Clans(commands.Cog):
    """Система кланов с лидерами, участниками, уровнем и балансом."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def _apply_clan_tag(self, member: discord.Member, tag: str):
        """Добавляет тег клана перед ником: [ТЕГ] Ник."""
        tag_clean = (tag or "").strip().upper()
        if not tag_clean:
            return
        try:
            current = member.nick or member.name
            cleaned = re.sub(rf"^\[{re.escape(tag_clean)}\]\s*", "", current)
            new_nick = f"[{tag_clean}] {cleaned}"
            if current != new_nick:
                await member.edit(nick=new_nick)
        except discord.HTTPException:
            pass

    async def _clear_clan_tag(self, member: discord.Member, tag: str):
        """Снимает тег клана с ника при выходе из клана."""
        tag_clean = (tag or "").strip().upper()
        if not tag_clean:
            return
        try:
            current = member.nick or member.name
            cleaned = re.sub(rf"^\[{re.escape(tag_clean)}\]\s*", "", current)
            if cleaned != current:
                if cleaned == member.name:
                    await member.edit(nick=None)
                else:
                    await member.edit(nick=cleaned)
        except discord.HTTPException:
            pass

    async def clan_create(self, interaction: discord.Interaction):
        user = await self.db.get_or_create_user(str(interaction.guild.id), str(interaction.user.id))
        if user.get("balance", 0) < 500:
            return await interaction.response.send_message("❌ Нужно 500 монет для создания клана.", ephemeral=True)
        await self.db.update_user_balance(str(interaction.guild.id), str(interaction.user.id), -500)
        await interaction.response.send_modal(ClanCreateModal(self))

    async def clan_info(self, interaction: discord.Interaction, clan_name: str = None):
        guild_id = str(interaction.guild.id)
        if clan_name:
            cursor = await self.db.conn.execute(
                "SELECT * FROM clans WHERE guild_id = ? AND name = ?", (guild_id, clan_name)
            )
        else:
            cursor = await self.db.conn.execute(
                "SELECT c.* FROM clans c JOIN clan_members cm ON c.id = cm.clan_id "
                "WHERE c.guild_id = ? AND cm.user_id = ?", (guild_id, str(interaction.user.id))
            )
        row = await cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Клан не найден.", ephemeral=True)

        clan = dict(row)
        level = clan["level"]
        exp = clan["exp"]
        next_level_xp = level * 1000
        progress = min(exp / next_level_xp * 100, 100) if next_level_xp else 0

        cursor = await self.db.conn.execute(
            "SELECT user_id, role FROM clan_members WHERE guild_id = ? AND clan_id = ?",
            (guild_id, clan["id"])
        )
        members = await cursor.fetchall()

        member_lines = []
        for m in members:
            if not interaction.guild.get_member(int(m["user_id"])):
                continue
            role_emoji = "👑" if m["role"] == "leader" else "⚔️"
            member_lines.append(f"{role_emoji} <@{m['user_id']}>")

        embed = discord.Embed(
            title=f"⚔️ Клан «{clan['name']}» [{clan['tag']}]",
            description=clan.get("description", "Нет описания"),
            color=Colors.MAIN,
        )
        embed.add_field(name="Уровень", value=f"{level} ({exp}/{next_level_xp} XP)", inline=True)
        embed.add_field(name="Баланс", value=f"{clan['balance']} монет", inline=True)
        embed.add_field(name=f"Участники ({len(members)})", value="\n".join(member_lines) or "Нет", inline=False)

        bar_len = round(progress / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        embed.add_field(name="Прогресс", value=f"`{bar}` {progress:.0f}%", inline=False)

        await interaction.response.send_message(embed=embed)

    async def clan_join(self, interaction: discord.Interaction, clan_name: str):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        cursor = await self.db.conn.execute(
            "SELECT clan_id FROM clan_members WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        if await cursor.fetchone():
            return await interaction.response.send_message("❌ Вы уже в клане. Покиньте его через **/menu → Кланы**.", ephemeral=True)

        cursor = await self.db.conn.execute(
            "SELECT id, tag FROM clans WHERE guild_id = ? AND name = ?", (guild_id, clan_name)
        )
        row = await cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Клан не найден.", ephemeral=True)

        await self.db.conn.execute(
            "INSERT INTO clan_members (guild_id, user_id, clan_id, role, joined_at) VALUES (?, ?, ?, 'member', ?)",
            (guild_id, user_id, row["id"], datetime.now(timezone.utc).isoformat())
        )
        await self.db.conn.commit()
        await interaction.response.send_message(f"✅ Вы вступили в клан **{clan_name}**!")
        await award_achievement(self.db, guild_id, user_id, "clan_join", interaction.user)
        await self._apply_clan_tag(interaction.user, row["tag"])

    async def clan_leave(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        cursor = await self.db.conn.execute(
            "SELECT cm.clan_id, cm.role, c.name, c.tag FROM clan_members cm "
            "JOIN clans c ON cm.clan_id = c.id WHERE cm.guild_id = ? AND cm.user_id = ?",
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Вы не в клане.", ephemeral=True)
        if row["role"] == "leader":
            return await interaction.response.send_message("❌ Лидер не может покинуть клан. Передайте лидерство.", ephemeral=True)

        await self.db.conn.execute(
            "DELETE FROM clan_members WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        await self.db.conn.commit()
        await self._clear_clan_tag(interaction.user, row["tag"])
        await interaction.response.send_message(f"✅ Вы покинули клан **{row['name']}**.")

    async def clan_top(self, interaction: discord.Interaction):
        cursor = await self.db.conn.execute(
            "SELECT c.name, c.tag, c.level, c.balance, "
            "(SELECT COUNT(*) FROM clan_members WHERE clan_id = c.id) as member_count "
            "FROM clans c WHERE c.guild_id = ? ORDER BY c.level DESC, c.balance DESC LIMIT 10",
            (str(interaction.guild.id),)
        )
        rows = await cursor.fetchall()
        if not rows:
            return await interaction.response.send_message("📭 Кланов пока нет.", ephemeral=True)

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else f"**{i+1}.**"
            lines.append(f"{medal} **{r['name']}** [{r['tag']}] — Ур. {r['level']} | {r['balance']} монет | {r['member_count']} уч.")

        embed = discord.Embed(title="⚔️ Топ кланов", description="\n".join(lines), color=Colors.MAIN)
        await interaction.response.send_message(embed=embed)

    async def clan_pay(self, interaction: discord.Interaction, amount: int = 100):
        if amount <= 0:
            return await interaction.response.send_message("❌ Сумма должна быть положительной.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        cursor = await self.db.conn.execute(
            "SELECT cm.clan_id, c.name FROM clan_members cm "
            "JOIN clans c ON cm.clan_id = c.id WHERE cm.guild_id = ? AND cm.user_id = ?",
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Вы не в клане.", ephemeral=True)

        user = await self.db.get_or_create_user(guild_id, user_id)
        if user.get("balance", 0) < amount:
            return await interaction.response.send_message("❌ Недостаточно монет.", ephemeral=True)

        await self.db.update_user_balance(guild_id, user_id, -amount)
        await self.db.conn.execute(
            "UPDATE clans SET balance = balance + ? WHERE id = ?", (amount, row["clan_id"])
        )
        await self.db.conn.commit()
        await interaction.response.send_message(f"✅ Вы пополнили баланс клана **{row['name']}** на **{amount}** монет.")

    async def clan_role(self, interaction: discord.Interaction, member: discord.Member, role: str):
        """Назначить роль в клане (лидер). role: officer | member."""
        if role not in ("officer", "member"):
            return await interaction.response.send_message("❌ Роль: `officer` или `member`.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        cursor = await self.db.conn.execute(
            "SELECT clan_id FROM clan_members WHERE guild_id = ? AND user_id = ? AND role = 'leader'",
            (guild_id, user_id)
        )
        if not await cursor.fetchone():
            return await interaction.response.send_message("❌ Только лидер клана может назначать роли.", ephemeral=True)

        cursor = await self.db.conn.execute(
            "SELECT clan_id FROM clan_members WHERE guild_id = ? AND user_id = ? AND clan_id = ("
            "SELECT clan_id FROM clan_members WHERE guild_id = ? AND user_id = ?)",
            (guild_id, str(member.id), guild_id, user_id)
        )
        if not await cursor.fetchone():
            return await interaction.response.send_message("❌ Этот участник не в вашем клане.", ephemeral=True)

        await self.db.conn.execute(
            "UPDATE clan_members SET role = ? WHERE guild_id = ? AND user_id = ?",
            (role, guild_id, str(member.id))
        )
        await self.db.conn.commit()
        role_name = "Офицер" if role == "officer" else "Участник"
        await interaction.response.send_message(f"✅ Роль **{role_name}** назначена {member.mention}.")


async def setup(bot):
    await bot.add_cog(Clans(bot))
