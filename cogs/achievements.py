import discord
from discord.ext import commands
from discord import app_commands
from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors

ACHIEVEMENTS = {
    "first_message": ("📨", "Первое сообщение", "Напишите первое сообщение"),
    "messages_100": ("💬", "Болтун", "Напишите 100 сообщений"),
    "messages_1000": ("📢", "Оратор", "Напишите 1000 сообщений"),
    "voice_60": ("🎙️", "Говорун", "Проведите 60 минут в голосовом чате"),
    "voice_300": ("🎧", "Меломан", "Проведите 300 минут в голосовом чате"),
    "level_5": ("⭐", "Новичок", "Достигните 5 уровня"),
    "level_10": ("🌟", "Опытный", "Достигните 10 уровня"),
    "level_20": ("🔥", "Ветеран", "Достигните 20 уровня"),
    "first_quest": ("📜", "Квестобоец", "Выполните первый квест"),
    "quests_10": ("🏆", "Исследователь", "Выполните 10 квестов"),
    "daily_3": ("📅", "Постоянный", "Соберите стрик из 3 дней"),
    "daily_7": ("🗓️", "Неделя с ботом", "Соберите стрик из 7 дней"),
    "first_buy": ("🛒", "Покупатель", "Совершите первую покупку в магазине"),
    "rich_1000": ("💰", "Богач", "Накопите 1000 монет"),
    "rich_10000": ("💎", "Миллиардер", "Накопите 10 000 монет"),
    "duel_win": ("⚔️", "Дуэлянт", "Выиграйте первую дуэль"),
    "duel_10": ("🥇", "Чемпион", "Выиграйте 10 дуэлей"),
    "roulette_win": ("🎰", "Везунчик", "Выиграйте в рулетке"),
    "reminder_1": ("⏰", "Пунктуальный", "Создайте первое напоминание"),
}


async def award_achievement(db: Database, guild_id: str, user_id: str, aid: str, member: discord.Member = None) -> tuple:
    """Выдаёт достижение, если оно ещё не получено.

    Возвращает (achievement_name, newly_awarded).
    При newly_awarded и переданном member отправляет ему DM.
    """
    info = ACHIEVEMENTS.get(aid)
    if not info:
        return None, False
    happy = await db.award_achievement(guild_id, user_id, aid)
    if happy and member is not None:
        emoji, name, desc = info
        embed = discord.Embed(
            title=f"{emoji} Достижение получено!",
            description=f"**{name}**\n{desc}\n\nВсего у вас: **{await db.count_achievements(guild_id, user_id)}**",
            color=Colors.MAIN,
        )
        embed.set_footer(text="Ayanami System")
        try:
            await member.send(embed=embed)
        except Exception:
            pass
    return info, happy


async def check_rich_achievements(db: Database, guild_id: str, user_id: str, member: discord.Member = None):
    user = await db.get_or_create_user(guild_id, user_id)
    balance = user.get("balance", 0)
    if balance >= 10000:
        await award_achievement(db, guild_id, user_id, "rich_10000", member)
    if balance >= 1000:
        await award_achievement(db, guild_id, user_id, "rich_1000", member)


class Achievements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(name="achievements", description="Твои достижения")
    async def achievements(self, interaction: discord.Interaction, member: discord.Member = None):
        if not interaction.guild:
            return
        await interaction.response.defer()
        target = member or interaction.user
        guild_id, user_id = str(interaction.guild.id), str(target.id)

        earned = await self.db.get_user_achievements(guild_id, user_id)
        earned_ids = {e["achievement_id"] for e in earned}

        lines = []
        for aid, (emoji, name, desc) in ACHIEVEMENTS.items():
            status = "✅" if aid in earned_ids else "🔒"
            lines.append(f"{status} {emoji} **{name}** — {desc}")

        embed = discord.Embed(
            title=f"🏅 Достижения — {target.display_name}",
            description="\n".join(lines),
            color=Colors.MAIN,
        )
        embed.set_footer(text=f"Выполнено: {len(earned_ids)} из {len(ACHIEVEMENTS)}")
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.followup.send(embed=embed)

    @commands.command(name="achievements")
    async def achievements_prefix(self, ctx, member: discord.Member = None):
        await self.achievements.callback(self, InteractionAdapter(ctx), member)


async def setup(bot):
    await bot.add_cog(Achievements(bot))