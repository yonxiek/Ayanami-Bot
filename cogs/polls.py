import discord
import json
from datetime import datetime, timezone, timedelta
from discord.ext import commands
from discord import app_commands
from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors


OPTION_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class PollVoteView(discord.ui.View):
    def __init__(self, poll_id: int, options: list[str], multi_select: bool):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        self.multi_select = multi_select
        for i, opt in enumerate(options[:10]):
            btn = discord.ui.Button(
                label=opt[:80],
                emoji=OPTION_EMOJIS[i],
                style=discord.ButtonStyle.secondary,
                custom_id=f"poll_vote_{poll_id}_{i}",
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            cog = interaction.client.get_cog("Polls")
            if not cog:
                return await interaction.response.send_message("❌ Модуль недоступен.", ephemeral=True)
            await cog._handle_vote(interaction, self.poll_id, index, self.multi_select)
        return callback


class Polls(commands.Cog):
    """Голосования с кнопками, анонимностью и множественным выбором."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(name="poll", description="Создать голосование")
    @app_commands.describe(
        question="Вопрос голосования",
        options="Варианты ответов через ;",
        multi_select="Множественный выбор (да/нет)",
        anonymous="Анонимное голосование (да/нет)",
        duration="Длительность (например: 1ч, 1д, 30м)"
    )
    async def poll(self, interaction: discord.Interaction, question: str, options: str,
                   multi_select: bool = False, anonymous: bool = False, duration: str = None):
        parts = [o.strip() for o in options.split(";") if o.strip()]
        if len(parts) < 2:
            return await interaction.response.send_message(
                "❌ Нужно минимум 2 варианта через `;` (точка с запятой).", ephemeral=True
            )
        if len(parts) > 10:
            return await interaction.response.send_message("❌ Максимум 10 вариантов.", ephemeral=True)

        ends_at = None
        if duration:
            ends_at = self._parse_duration(duration)
            if not ends_at:
                return await interaction.response.send_message(
                    "❌ Не понимаю время. Примеры: `30м`, `1ч`, `1д`.", ephemeral=True
                )

        options_json = json.dumps(parts, ensure_ascii=False)
        cursor = await self.db.conn.execute(
            "INSERT INTO polls (guild_id, creator_id, channel_id, question, options, multi_select, anonymous, status, created_at, ends_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (str(interaction.guild.id), str(interaction.user.id), str(interaction.channel.id),
             question, options_json, int(multi_select), int(anonymous),
             datetime.now(timezone.utc).isoformat(), ends_at.isoformat() if ends_at else None)
        )
        await self.db.conn.commit()
        poll_id = cursor.lastrowid

        desc_lines = []
        for i, opt in enumerate(parts):
            desc_lines.append(f"{OPTION_EMOJIS[i]} **{opt}**")
        desc = "\n".join(desc_lines)
        if multi_select:
            desc += "\n\n*(Можно выбирать несколько вариантов)*"

        embed = discord.Embed(
            title=f"📊 {question}",
            description=desc,
            color=Colors.MAIN,
            timestamp=datetime.now(timezone.utc),
        )
        footer = f"Создал: {interaction.user.name}"
        if anonymous:
            footer += " • Анонимное"
        if ends_at:
            footer += f" • До <t:{int(ends_at.timestamp())}:f>"
        embed.set_footer(text=footer)

        view = PollVoteView(poll_id, parts, multi_select)
        msg = await interaction.channel.send(embed=embed, view=view)

        await self.db.conn.execute(
            "UPDATE polls SET message_id = ? WHERE id = ?", (str(msg.id), poll_id)
        )
        await self.db.conn.commit()

        await interaction.response.send_message(f"✅ Голосование создано!", ephemeral=True)

    @app_commands.command(name="poll_end", description="Завершить голосование")
    @app_commands.describe(message_id="ID сообщения с голосованием")
    async def poll_end(self, interaction: discord.Interaction, message_id: str):
        cursor = await self.db.conn.execute(
            "SELECT id, question, options FROM polls WHERE guild_id = ? AND message_id = ? AND status = 'active'",
            (str(interaction.guild.id), message_id)
        )
        row = await cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Голосование не найдено или уже завершено.", ephemeral=True)

        poll_id, question, options_json = row["id"], row["question"], row["options"]
        options = json.loads(options_json)

        await self.db.conn.execute(
            "UPDATE polls SET status = 'ended' WHERE id = ?", (poll_id,)
        )
        await self.db.conn.commit()

        results = await self._get_results(poll_id, options)
        embed = discord.Embed(
            title=f"📊 Результаты: {question}",
            description=results["text"],
            color=Colors.SUCCESS,
        )
        embed.set_footer(text=f"Всего голосов: {results['total']}")

        await interaction.response.send_message(embed=embed)

        try:
            channel = interaction.channel
            msg = await channel.fetch_message(int(message_id))
            for item in msg.components:
                for child in item.children:
                    child.disabled = True
            await msg.edit(view=None)
        except Exception:
            pass

    @app_commands.command(name="poll_results", description="Показать результаты голосования")
    @app_commands.describe(message_id="ID сообщения с голосованием")
    async def poll_results(self, interaction: discord.Interaction, message_id: str):
        cursor = await self.db.conn.execute(
            "SELECT id, question, options FROM polls WHERE guild_id = ? AND message_id = ?",
            (str(interaction.guild.id), message_id)
        )
        row = await cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Голосование не найдено.", ephemeral=True)

        options = json.loads(row["options"])
        results = await self._get_results(row["id"], options)
        embed = discord.Embed(
            title=f"📊 {row['question']}",
            description=results["text"],
            color=Colors.MAIN,
        )
        embed.set_footer(text=f"Всего голосов: {results['total']}")
        await interaction.response.send_message(embed=embed)

    async def _handle_vote(self, interaction: discord.Interaction, poll_id: int, option_index: int, multi_select: bool):
        user_id = str(interaction.user.id)

        cursor = await self.db.conn.execute(
            "SELECT status, options FROM polls WHERE id = ?", (poll_id,)
        )
        row = await cursor.fetchone()
        if not row or row["status"] != "active":
            return await interaction.response.send_message("❌ Голосование уже завершено.", ephemeral=True)

        options = json.loads(row["options"])

        if multi_select:
            existing = await self.db.conn.execute(
                "SELECT option_index FROM poll_votes WHERE poll_id = ? AND user_id = ? AND option_index = ?",
                (poll_id, user_id, option_index)
            )
            if await existing.fetchone():
                await self.db.conn.execute(
                    "DELETE FROM poll_votes WHERE poll_id = ? AND user_id = ? AND option_index = ?",
                    (poll_id, user_id, option_index)
                )
                await self.db.conn.commit()
                return await interaction.response.send_message(
                    f"✅ Голос за **{options[option_index]}** отменён.", ephemeral=True
                )
            else:
                try:
                    await self.db.conn.execute(
                        "INSERT INTO poll_votes (poll_id, user_id, option_index, created_at) VALUES (?, ?, ?, ?)",
                        (poll_id, user_id, option_index, datetime.now(timezone.utc).isoformat())
                    )
                    await self.db.conn.commit()
                    return await interaction.response.send_message(
                        f"✅ Голос за **{options[option_index]}** засчитан!", ephemeral=True
                    )
                except Exception:
                    return await interaction.response.send_message("❌ Ошибка записи голоса.", ephemeral=True)
        else:
            await self.db.conn.execute(
                "DELETE FROM poll_votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id)
            )
            try:
                await self.db.conn.execute(
                    "INSERT INTO poll_votes (poll_id, user_id, option_index, created_at) VALUES (?, ?, ?, ?)",
                    (poll_id, user_id, option_index, datetime.now(timezone.utc).isoformat())
                )
                await self.db.conn.commit()
                return await interaction.response.send_message(
                    f"✅ Ваш голос: **{options[option_index]}**", ephemeral=True
                )
            except Exception:
                return await interaction.response.send_message("❌ Ошибка записи голоса.", ephemeral=True)

    async def _get_results(self, poll_id: int, options: list[str]) -> dict:
        cursor = await self.db.conn.execute(
            "SELECT option_index, COUNT(*) as cnt FROM poll_votes WHERE poll_id = ? GROUP BY option_index",
            (poll_id,)
        )
        rows = await cursor.fetchall()
        counts = {row["option_index"]: row["cnt"] for row in rows}
        total = sum(counts.values()) or 1

        lines = []
        for i, opt in enumerate(options):
            count = counts.get(i, 0)
            pct = round(count / total * 100) if total else 0
            bar_len = round(pct / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"{OPTION_EMOJIS[i]} **{opt}**\n`{bar}` **{count}** ({pct}%)")

        return {"text": "\n\n".join(lines), "total": sum(counts.values())}

    def _parse_duration(self, text: str) -> datetime | None:
        import re
        m = re.match(r"(\d+)([smhd])", text.lower())
        if not m:
            return None
        value, unit = int(m.group(1)), m.group(2)
        kwargs = {"seconds": value} if unit == "s" else \
                 {"minutes": value} if unit == "m" else \
                 {"hours": value} if unit == "h" else {"days": value}
        return datetime.now(timezone.utc) + timedelta(**kwargs)

    # ==========================================================
    #                ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================================

    @commands.command(name="poll")
    async def poll_prefix(self, ctx, question: str, *, options: str):
        from prefix_adapter import InteractionAdapter
        await self.poll.callback(self, InteractionAdapter(ctx), question, options)

    @commands.command(name="poll_end")
    async def poll_end_prefix(self, ctx, message_id: str):
        from prefix_adapter import InteractionAdapter
        await self.poll_end.callback(self, InteractionAdapter(ctx), message_id)

    @commands.command(name="poll_results")
    async def poll_results_prefix(self, ctx, message_id: str):
        from prefix_adapter import InteractionAdapter
        await self.poll_results.callback(self, InteractionAdapter(ctx), message_id)


async def setup(bot):
    await bot.add_cog(Polls(bot))
