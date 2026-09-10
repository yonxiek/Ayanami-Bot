import random
from functools import partial

import discord
from discord.ext import commands
from discord import app_commands
from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors

MAX_HP = 100
CHALLENGE_TIMEOUT = 45
BATTLE_TIMEOUT = 120
MAX_BET = 1_000_000


def hp_bar(hp: int) -> str:
    filled = round(hp / 10)
    return "█" * filled + "░" * (10 - filled)


class Duels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.pending_challenges: dict[tuple[int, int], ChallengeView] = {}
        self.active_duels: set[int] = set()

    @app_commands.command(name="duel", description="Вызвать игрока на дуэль со ставкой")
    @app_commands.describe(противник="Кого вызываешь", ставка="Ставка в монетах")
    async def duel(self, interaction: discord.Interaction, противник: discord.Member, ставка: int):
        if not interaction.guild:
            return
        if противник.id == interaction.user.id:
            return await interaction.response.send_message("❌ Нельзя дуэлить с самим собой.", ephemeral=True)
        if противник.bot:
            return await interaction.response.send_message("❌ Бот не дуэлирует.", ephemeral=True)
        if not (5 <= ставка <= MAX_BET):
            return await interaction.response.send_message(f"❌ Ставка от 5 до {MAX_BET}.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        if interaction.user.id in self.active_duels or противник.id in self.active_duels:
            return await interaction.response.send_message("❌ Один из игроков уже в дуэли.", ephemeral=True)
        key = (interaction.user.id, противник.id)
        if key in self.pending_challenges:
            return await interaction.response.send_message("❌ Вы уже вызвали этого игрока.", ephemeral=True)
        rev = (противник.id, interaction.user.id)
        if rev in self.pending_challenges:
            return await interaction.response.send_message("❌ Этот игрок уже вызвал вас.", ephemeral=True)

        challenger_bal = (await self.db.get_or_create_user(guild_id, str(interaction.user.id))).get("balance", 0)
        opponent_bal = (await self.db.get_or_create_user(guild_id, str(противник.id))).get("balance", 0)
        if challenger_bal < ставка:
            return await interaction.response.send_message(f"❌ У вас недостаточно монет (нужно {ставка}).", ephemeral=True)
        if opponent_bal < ставка:
            return await interaction.response.send_message(f"❌ У **{противник.display_name}** недостаточно монет.", ephemeral=True)

        embed = discord.Embed(
            title="⚔️ Вызов на дуэль!",
            description=(
                f"**{interaction.user.mention}** вызывает **{противник.mention}** на дуэль!\n\n"
                f"Ставка: **{ставка}** монет с каждого.\n"
                f"Победитель забирает **{ставка * 2}** монет.\n\n"
                f"**{противник.mention}**, принять вызов?"
            ),
            color=Colors.MAIN,
        )
        embed.set_footer(text=f"Вызов истечёт через {CHALLENGE_TIMEOUT} секунд")

        view = ChallengeView(self, interaction.user, противник, ставка)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()
        self.pending_challenges[key] = view

    @commands.command(name="duel")
    async def duel_prefix(self, ctx, противник: discord.Member, ставка: int):
        await self.duel.callback(self, InteractionAdapter(ctx), противник, ставка)


class ChallengeView(discord.ui.View):
    def __init__(self, cog, challenger: discord.Member, opponent: discord.Member, bet: int):
        super().__init__(timeout=CHALLENGE_TIMEOUT)
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent
        self.bet = bet
        self.message = None

    async def _remove_pending(self, key):
        self.cog.pending_challenges.pop(key, None)

    @discord.ui.button(label="Принять", emoji="✅", style=discord.ButtonStyle.success, row=0)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("❌ Принять вызов может только приглашённый.", ephemeral=True)
        if not self.message:
            return
        guild_id = str(interaction.guild.id)
        await self._remove_pending((self.challenger.id, self.opponent.id))
        self.cog.active_duels.update({self.challenger.id, self.opponent.id})

        await self.cog.db.update_user_balance(guild_id, str(self.challenger.id), -self.bet)
        await self.cog.db.update_user_balance(guild_id, str(self.opponent.id), -self.bet)

        battle = DuelView(self.cog, interaction.guild, self.challenger, self.opponent, self.bet)
        battle.message = self.message
        try:
            await interaction.response.edit_message(embed=battle.build_embed(), view=battle)
        except Exception:
            await interaction.response.edit_message(content="⚔️ Дуэль начата!", embed=battle.build_embed(), view=None)
        await battle.start()

    @discord.ui.button(label="Отказаться", emoji="❌", style=discord.ButtonStyle.danger, row=0)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            return await interaction.response.send_message("❌ Это не ваш вызов.", ephemeral=True)
        await self._remove_pending((self.challenger.id, self.opponent.id))
        await interaction.response.edit_message(
            content=f"❌ **{self.opponent.display_name}** отказался от дуэли.",
            embed=None, view=None
        )

    async def on_timeout(self):
        await self._remove_pending((self.challenger.id, self.opponent.id))
        if self.message:
            try:
                await self.message.edit(content="⏳ Вызов истёк.", embed=None, view=None)
            except Exception:
                pass


class DuelView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, p1: discord.Member, p2: discord.Member, bet: int):
        super().__init__(timeout=BATTLE_TIMEOUT)
        self.cog = cog
        self.guild = guild
        self.players = [p1, p2]
        self.hp = [MAX_HP, MAX_HP]
        self.guard = [False, False]
        self.turn = 0
        self.bet = bet
        self.message = None
        self.ended = False
        self.last_actions = ["—", "—"]
        self.action_buttons: dict = {}

        rows = [
            [("Атака", "⚔️", discord.ButtonStyle.danger, "attack"),
             ("Защита", "🛡️", discord.ButtonStyle.primary, "guard"),
             ("Лечение", "💊", discord.ButtonStyle.success, "heal"),
             ("Сдаться", "🏳️", discord.ButtonStyle.secondary, "surrender")],
            [("Атака", "⚔️", discord.ButtonStyle.danger, "attack"),
             ("Защита", "🛡️", discord.ButtonStyle.primary, "guard"),
             ("Лечение", "💊", discord.ButtonStyle.success, "heal"),
             ("Сдаться", "🏳️", discord.ButtonStyle.secondary, "surrender")],
        ]
        for row_idx, row in enumerate(rows):
            for label, emoji, style, action in row:
                btn = discord.ui.Button(label=label, emoji=emoji, style=style, row=row_idx)
                btn.callback = partial(self._action, owner_idx=row_idx, action=action)
                self.action_buttons[(row_idx, action)] = btn
                self.add_item(btn)
        self._refresh_buttons()

    def _refresh_buttons(self):
        for (owner_idx, action), btn in self.action_buttons.items():
            btn.disabled = self.ended or owner_idx != self.turn

    def build_embed(self) -> discord.Embed:
        p1, p2 = self.players
        embed = discord.Embed(
            title="⚔️ Дуэль",
            color=Colors.MAIN,
            description=(
                f"{p1.mention} 🆚 {p2.mention}\n\n"
                f"**{p1.display_name}**\n{hp_bar(self.hp[0])} `{self.hp[0]}/100`"
                f"{' 🛡️' if self.guard[0] else ''}  _({self.last_actions[0]})_\n"
                f"**{p2.display_name}**\n{hp_bar(self.hp[1])} `{self.hp[1]}/100`"
                f"{' 🛡️' if self.guard[1] else ''}  _({self.last_actions[1]})_\n\n"
                f"Банк: **{self.bet * 2}** монет"
            ),
        )
        embed.set_footer(text=f"Ход: {self.players[self.turn].display_name}")
        return embed

    async def _action(self, interaction: discord.Interaction, button: discord.ui.Button, owner_idx: int = None, action: str = None):
        if self.ended:
            return await interaction.response.send_message("Дуэль уже завершена.", ephemeral=True)
        player = interaction.user
        owner = self.players[owner_idx]
        if player.id != owner.id:
            return await interaction.response.send_message("Это не ваши кнопки!", ephemeral=True)
        if owner_idx != self.turn:
            return await interaction.response.send_message("Сейчас не ваш ход!", ephemeral=True)

        if action == "surrender":
            self.ended = True
            self.last_actions[owner_idx] = "Сдался"
            await self._finish(interaction, winner_idx=1 - owner_idx, via="surrender")
            return

        await interaction.response.defer()

        if action == "attack":
            dmg = random.randint(8, 16)
            target = 1 - owner_idx
            if self.guard[target]:
                dmg = max(1, dmg // 2)
                self.guard[target] = False
            self.hp[target] = max(0, self.hp[target] - dmg)
            self.last_actions[owner_idx] = f"⚔️ -{dmg} HP"
        elif action == "guard":
            self.guard[owner_idx] = True
            self.last_actions[owner_idx] = "🛡️ Защита (урон -50%)"
        elif action == "heal":
            heal = random.randint(6, 12)
            if self.guard[owner_idx]:
                self.guard[owner_idx] = False
            self.hp[owner_idx] = min(MAX_HP, self.hp[owner_idx] + heal)
            self.last_actions[owner_idx] = f"💊 +{heal} HP"

        if self.hp[0] <= 0 or self.hp[1] <= 0:
            self.ended = True
            await self._finish(interaction, winner_idx=0 if self.hp[0] > 0 else 1, via="ko")
            return

        self.turn = 1 - self.turn
        self._refresh_buttons()
        try:
            await interaction.edit_original_response(embed=self.build_embed(), view=self)
        except Exception:
            pass

    async def _finish(self, interaction, winner_idx: int, via: str):
        self.ended = True
        self._refresh_buttons()
        winner = self.players[winner_idx]
        loser = self.players[1 - winner_idx]
        guild_id = str(self.guild.id)

        await self.cog.db.update_user_balance(guild_id, str(winner.id), self.bet * 2)
        await self.cog.db.add_duel_result(guild_id, str(winner.id), "win")
        await self.cog.db.add_duel_result(guild_id, str(loser.id), "loss")

        embed = self.build_embed()
        embed.title = "🏆 Дуэль завершена"
        embed.color = discord.Color.green()
        embed.description = (
            f"**{winner.mention} победил** и забирает банк **{self.bet * 2}** монет!\n\n"
            + embed.description
        )
        embed.set_footer(text=via)

        self.cog.active_duels.discard(winner.id)
        self.cog.active_duels.discard(loser.id)

        await self._awards(interaction, winner, loser)

        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass

    async def _awards(self, interaction, winner, loser):
        try:
            from cogs.achievements import award_achievement, check_rich_achievements
            guild_id = str(self.guild.id)
            await award_achievement(self.cog.db, guild_id, str(winner.id), "duel_win", winner)
            stats = await self.cog.db.get_duel_stats(guild_id, str(winner.id))
            if stats["wins"] >= 10:
                await award_achievement(self.cog.db, guild_id, str(winner.id), "duel_10", winner)
            await check_rich_achievements(self.cog.db, guild_id, str(winner.id), winner)
        except Exception:
            pass

    async def on_timeout(self):
        if self.ended or not self.message:
            return
        self.ended = True
        guild_id = str(self.guild.id)
        for p in self.players:
            await self.cog.db.update_user_balance(guild_id, str(p.id), self.bet)
            await self.cog.db.add_duel_result(guild_id, str(p.id), "draw")
            self.cog.active_duels.discard(p.id)
        try:
            await self.message.edit(content="⏳ Дуэль прервана по таймауту — ставки возвращены.", embed=None, view=None)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Duels(bot))