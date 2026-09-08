import discord
import random
import aiohttp
from discord.ext import commands
from discord import app_commands
from db import Database



RPS_CHOICES = {
    "rock": {"emoji": "🪨", "name": "Камень"},
    "scissors": {"emoji": "✂️", "name": "Ножницы"},
    "paper": {"emoji": "📄", "name": "Бумага"},
}

RPS_WIN = {
    ("rock", "scissors"): True,
    ("scissors", "paper"): True,
    ("paper", "rock"): True,
}

ROULETTE_TABLE = [
    (5,  "🎰", "МЕГА-ДЖЕКПОТ!", "+1000", 0xf1c40f, 1000),
    (10, "🏆", "ДЖЕКПОТ!",     "+500",  0xe74c3c, 500),
    (20, "🎁", "Приз",          "+100",  0x2ecc71, 100),
    (25, "😊", "Удача",         "+50",   0x3498db, 50),
    (25, "🤷", "Ничего",        "0",     0x95a5a6, 0),
    (15, "💸", "Потеря",        "-50",   0xe74c3c, -50),
]


class RPSView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.result = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоя игра!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Камень", emoji="🪨", style=discord.ButtonStyle.secondary)
    async def btn_rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = "rock"
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Ножницы", emoji="✂️", style=discord.ButtonStyle.secondary)
    async def btn_scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = "scissors"
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Бумага", emoji="📄", style=discord.ButtonStyle.secondary)
    async def btn_paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = "paper"
        await interaction.response.defer()
        self.stop()


class NumberGameView(discord.ui.View):
    def __init__(self, answer: int, author_id: int):
        super().__init__(timeout=120)
        self.answer = answer
        self.author_id = author_id
        self.attempts = 0
        self.guesses = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоя игра!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ввести число", emoji="🔢", style=discord.ButtonStyle.primary)
    async def btn_guess(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GuessModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Завершить", emoji="🛑", style=discord.ButtonStyle.danger)
    async def btn_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content=f"Игра окончена. Число было: **{self.answer}**",
            view=None
        )


class GuessModal(discord.ui.Modal, title="Угадай число"):
    guess_input = discord.ui.TextInput(
        label="Твоё число (1-100)",
        placeholder="Напиши число",
        max_length=3,
        required=True
    )

    def __init__(self, game_view: NumberGameView):
        super().__init__()
        self.game_view = game_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            guess = int(self.guess_input.value)
            if guess < 1 or guess > 100:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Введи число от 1 до 100!", ephemeral=True)

        self.game_view.attempts += 1
        self.game_view.guesses.append(guess)
        db = Database()

        if guess == self.game_view.answer:
            await db.conn.execute('''
                INSERT INTO game_scores (guild_id, user_id, wins, total)
                VALUES (?, ?, 1, 1)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET wins = wins + 1, total = total + 1
            ''', (str(interaction.guild.id), str(interaction.user.id)))
            await db.conn.commit()
            history = " → ".join(str(g) for g in self.game_view.guesses)
            embed = discord.Embed(
                title="🎯 Угадал!",
                description=f"**Число:** {self.game_view.answer}\n**Попыток:** {self.game_view.attempts}\n**Попытки:** {history}",
                color=discord.Color.green(),
            )
            self.game_view.stop()
            await interaction.response.edit_message(view=view)
        else:
            hint = "Больше ⬆️" if guess < self.game_view.answer else "Меньше ⬇️"
            history = " → ".join(str(g) for g in self.game_view.guesses)
            if self.game_view.attempts >= 10:
                await db.conn.execute('''
                    INSERT INTO game_scores (guild_id, user_id, wins, total)
                    VALUES (?, ?, 0, 1)
                    ON CONFLICT(guild_id, user_id)
                    DO UPDATE SET total = total + 1
                ''', (str(interaction.guild.id), str(interaction.user.id)))
                await db.conn.commit()
                embed = discord.Embed(
                    title="💀 Проиграл!",
                    description=f"**Число было:** {self.game_view.answer}\n**Попытки:** {history}",
                    color=discord.Color.red(),
                )
                self.game_view.stop()
                await interaction.response.edit_message(view=view)
            else:
                embed = discord.Embed(
                    title=hint,
                    description=f"Попытка {self.game_view.attempts}/10\n**Попытки:** {history}",
                    color=discord.Color(0xf39c12),
                )
                await interaction.response.edit_message(view=self.game_view)


class MiniGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(name="fact", description="Случайный интересный факт")
    async def fact(self, interaction: discord.Interaction):
        await interaction.response.defer()
        text = await self._fetch_fact()
        embed = discord.Embed(title="📚 Случайный факт", description=text, color=discord.Color(0x3498db))
        await interaction.followup.send(embed=embed)

    async def _fetch_fact(self) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://randstuff.ru/fact/",
                    timeout=aiohttp.ClientTimeout(total=5),
                    headers={"User-Agent": "Mozilla/5.0"}
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        start = html.find('<td>') + 4
                        end = html.find('</td>', start)
                        if start > 3 and end > start:
                            fact = html[start:end].strip()
                            if fact and len(fact) > 10:
                                return fact
        except Exception:
            pass
        facts_ru = [
            "Япония моноэтническая страна, 98.4% населения — этнические японцы.",
            "У кошек 32 мышцы в ушах, что позволяет им поворачивать уши на 180 градусов.",
            "У осьминога три сердца и голубая кровь.",
            "Земля вращается со скоростью около 1 670 км/ч на экваторе.",
            "Человеческий мозг использует около 20% всей энергии тела.",
            "Луна удаляется от Земли примерно на 3.8 см каждый год.",
            "Пчёлы могут узнавать лица людей.",
            "Акулы существуют дольше деревьев — около 400 миллионов лет.",
            "Свет от Солнца до Земли идёт около 8 минут и 20 секунд.",
            "Ботанически банан — это ягода, а клубника — нет.",
            "Мёд не портится — археологи находили мёд в египетских гробницах возрастом 3 000 лет.",
            "Некоторые динозавры были размером с курицу.",
            "Подсолнухи поворачиваются за солнцем в течение дня.",
            "Снег бывает розовым — из-за водорослей в Антарктиде.",
            "Попугаи могут жить до 80 лет и старше.",
            "На Марсе есть гора высотой 21 км — Олимп.",
            "Муравьи могут поднимать предметы в 50 раз тяжелее себя.",
            "В Японии есть остров кроликов — Окуношима.",
            "Собаки видят сны, как и люди.",
            "Кенгуру не могут прыгать назад.",
            "Во Вселенной примерно 2 триллиона галактик.",
            "Ленивцы проводят 90% своей жизни вис головой вниз.",
            "Змеи могут есть в 3 раза больше своего веса за один раз.",
            "Самый большой организм на Земле — гриб в Орегоне диаметром 3.4 км.",
            "70% поверхности Земли покрыто водой.",
            "Сакура цветёт всего 2 недели.",
            "Хамелеоны меняют цвет для общения и температуры, а не для маскировки.",
            "Кошки проводят 70% своей жизни во сне.",
            "В Антарктиде нет постоянного населения.",
            "Мёд — единственная пища, которая не портится.",
        ]
        return random.choice(facts_ru)

    @app_commands.command(name="rps", description="Камень-ножницы-бумага")
    async def rps(self, interaction: discord.Interaction):
        view = RPSView(interaction.user.id)
        await interaction.response.send_message("Выбери свой ход:", view=view)
        await view.wait()
        if view.result is None:
            return
        bot_choice = random.choice(["rock", "scissors", "paper"])
        player = {"rock": ("🪨", "Камень"), "scissors": ("✂️", "Ножницы"), "paper": ("📄", "Бумага")}
        p_emoji, p_name = player[view.result]
        b_emoji, b_name = player[bot_choice]
        if view.result == bot_choice:
            result_text = "Ничья! 🤝"
            color = discord.Color(0xf39c12)
        elif (view.result, bot_choice) in RPS_WIN:
            result_text = "Ты выиграл! 🎉"
            color = discord.Color.green()
            await self.db.conn.execute('''
                INSERT INTO game_scores (guild_id, user_id, wins, total) VALUES (?, ?, 1, 1)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET wins = wins + 1, total = total + 1
            ''', (str(interaction.guild.id), str(interaction.user.id)))
            await self.db.conn.commit()
        else:
            result_text = "Ты проиграл! 😔"
            color = discord.Color.red()
            await self.db.conn.execute('''
                INSERT INTO game_scores (guild_id, user_id, wins, total) VALUES (?, ?, 0, 1)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET total = total + 1
            ''', (str(interaction.guild.id), str(interaction.user.id)))
            await self.db.conn.commit()
        result_embed = discord.Embed(
            title="⚔️ Камень-ножницы-бумага",
            description=f"**Ты:** {p_emoji} {p_name}\n**Бот:** {b_emoji} {b_name}\n\n**Результат:** {result_text}",
            color=color,
        )
        await interaction.edit_original_response(embed=result_embed)

    @app_commands.command(name="number", description="Угадай число от 1 до 100")
    async def number(self, interaction: discord.Interaction):
        answer = random.randint(1, 100)
        game_view = NumberGameView(answer, interaction.user.id)
        await interaction.response.send_message(content="## 🔢 Угадай число\nЯ загадал число от 1 до 100.\nУ тебя 10 попыток.\n\nНажми кнопку ниже, чтобы ввести число.", view=game_view)

    @app_commands.command(name="roulette", description="Крути рулетку и выигрывай монеты!")
    @app_commands.checks.cooldown(1, 3600, key=lambda i: (i.guild_id, i.user.id))
    async def roulette(self, interaction: discord.Interaction):
        await interaction.response.defer()
        roll = random.randint(1, 100)
        cumulative = 0
        result = ROULETTE_TABLE[-1]
        for chance, emoji, name, amount_str, color, amount in ROULETTE_TABLE:
            cumulative += chance
            if roll <= cumulative:
                result = (chance, emoji, name, amount_str, color, amount)
                break
        _, emoji, name, amount_str, color, amount = result
        if amount > 0:
            await self.db.update_user_balance(str(interaction.guild.id), str(interaction.user.id), amount)
        elif amount < 0:
            await self.db.update_user_balance(str(interaction.guild.id), str(interaction.user.id), amount)
        user_data = await self.db.get_or_create_user(str(interaction.guild.id), str(interaction.user.id))
        balance = user_data.get("balance", 0)
        embed = discord.Embed(
            title="🎰 Рулетка",
            description=f"Выпало: {emoji} **{name}**\n\n**Награда:** {amount_str} монет\n**Баланс:** {balance} монет",
            color=discord.Color(color),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed)

    @roulette.error
    async def roulette_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            minutes = int(error.retry_after // 60)
            seconds = int(error.retry_after % 60)
            embed = discord.Embed(
                title="🎰 Рулетка на кулдауне",
                description=f"Подожди **{minutes}м {seconds}с** перед следующим вращением.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            raise error

    @app_commands.command(name="scores", description="Твоя статистика в играх")
    async def scores(self, interaction: discord.Interaction):
        cursor = await self.db.conn.execute(
            'SELECT wins, total FROM game_scores WHERE guild_id = ? AND user_id = ?',
            (str(interaction.guild.id), str(interaction.user.id))
        )
        row = await cursor.fetchone()
        user_data = await self.db.get_or_create_user(str(interaction.guild.id), str(interaction.user.id))
        balance = user_data.get("balance", 0)
        if not row:
            embed = discord.Embed(
                title="📊 Твоя статистика",
                description=f"**Баланс:** {balance} монет\n\nТы ещё не играл! Начни с `/rps`, `/number` или `/roulette`.",
                color=discord.Color(0x3498db),
            )
            return await interaction.response.send_message(embed=embed)
        wins = row['wins']
        total = row['total']
        winrate = round(wins / total * 100) if total > 0 else 0
        embed = discord.Embed(
            title="📊 Твоя статистика",
            description=f"**Баланс:** {balance} монет\n\n**Побед:** {wins}\n**Всего игр:** {total}\n**Винрейт:** {winrate}%",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)


    @commands.command(name="fact")
    async def fact_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.fact.callback(self, InteractionAdapter(ctx))

    @commands.command(name="rps")
    async def rps_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.rps.callback(self, InteractionAdapter(ctx))

    @commands.command(name="number")
    async def number_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.number.callback(self, InteractionAdapter(ctx))

    @commands.command(name="roulette")
    async def roulette_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.roulette.callback(self, InteractionAdapter(ctx))

    @commands.command(name="scores")
    async def scores_prefix(self, ctx):
        from prefix_adapter import InteractionAdapter
        await self.scores.callback(self, InteractionAdapter(ctx))

async def setup(bot):
    await bot.add_cog(MiniGames(bot))
