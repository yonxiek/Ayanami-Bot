import aiohttp
import discord
import json
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors
import config
import ai_client

MODERATION_PROMPT = (
    "Ты — модератор Discord-сервера. Проанализируй сообщение и верни JSON:\n"
    '{"action": "none|warn|mute|delete", "reason": "причина на русском", "confidence": 0.0-1.0}\n\n'
    "Критерии:\n"
    "- none: сообщение нормальное\n"
    "- warn: лёгкие оскорбления, токсичность\n"
    "- mute: серьёзные оскорбления, угрозы, спам\n"
    "- delete: оскорбления, NSWM, реклама, запросы личных данных\n\n"
    "Сообщение для анализа: {text}"
)


class AIModeration(commands.Cog):
    """AI-модерация сообщений через Gemini."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def _check_message(self, message: discord.Message) -> dict | None:
        if not message.guild:
            return None
        if message.author.bot:
            return None

        config_data = await self.db.get_guild_config(str(message.guild.id))
        if not config_data.get("ai_moderation_enabled", False):
            return None

        # Не проверяем сообщения модераторов
        staff_roles = [str(r) for r in (config_data.get("staff_roles", []) or [])]
        admin_roles = [str(r) for r in (config_data.get("admin_roles", []) or [])]
        exempt_roles = set(staff_roles + admin_roles)
        if any(str(r.id) in exempt_roles for r in message.author.roles):
            return None

        text = message.content[:500]
        if not text or len(text) < 5:
            return None

        prompt = MODERATION_PROMPT.format(text=text)
        provider = ai_client.normalize_provider(config_data.get("ai_provider"))

        try:
            response_text = await ai_client.complete(
                prompt,
                [{"role": "user", "content": text}],
                provider=provider,
                temperature=0.1,
                max_tokens=150,
            )
        except Exception:
            return None

        if not response_text:
            return None

        # Извлекаем JSON из ответа
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start == -1 or end <= start:
            return None
        try:
            result = json.loads(response_text[start:end])
            return result
        except (ValueError, json.JSONDecodeError):
            return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        result = await self._check_message(message)
        if not result or result.get("action") == "none":
            return

        action = result.get("action", "none")
        reason = result.get("reason", "Нарушение правил (AI)")
        confidence = result.get("confidence", 0)

        # Минимальный порог уверенности
        if confidence < 0.6:
            return

        await self._log_action(message, result)

        try:
            if action == "delete":
                await message.delete()
                await message.channel.send(
                    f"⚠️ {message.author.mention}, сообщение удалено модерацией: {reason}",
                    delete_after=10
                )
            elif action == "warn":
                await self.db.conn.execute(
                    'INSERT INTO warns (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)',
                    (str(message.guild.id), str(message.author.id), str(self.bot.user.id),
                     f"[AI] {reason}", datetime.now(timezone.utc).isoformat())
                )
                await self.db.conn.commit()
                await message.channel.send(
                    f"⚠️ {message.author.mention}, предупреждение: {reason}",
                    delete_after=15
                )
            elif action == "mute":
                until = discord.utils.utcnow() + __import__("datetime").timedelta(minutes=10)
                await message.member.timeout(until, reason=f"[AI] {reason}")
                await message.channel.send(
                    f"🔇 {message.author.mention}, тайм-аут на 10 минут: {reason}",
                    delete_after=15
                )
        except (discord.Forbidden, AttributeError):
            pass

    async def _log_action(self, message: discord.Message, result: dict):
        await self.db.conn.execute(
            "INSERT INTO ai_moderation_log (guild_id, user_id, channel_id, message_id, original_text, action, reason, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(message.guild.id), str(message.author.id), str(message.channel.id),
             str(message.id), message.content[:500], result.get("action"),
             result.get("reason"), result.get("confidence", 0),
             datetime.now(timezone.utc).isoformat())
        )
        await self.db.conn.commit()

    @app_commands.command(name="ai_mod_set", description="Включить/выключить AI-модерацию")
    @app_commands.describe(enabled="Включить или выключить")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Включить", value="on"),
        app_commands.Choice(name="Выключить", value="off"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def ai_mod_set(self, interaction: discord.Interaction, enabled: app_commands.Choice[str]):
        val = enabled.value == "on"
        await self.db.update_config_field(str(interaction.guild.id), "ai_moderation_enabled", val)
        status = "включена" if val else "выключена"
        await interaction.response.send_message(f"✅ AI-модерация {status}.", ephemeral=True)

    @app_commands.command(name="ai_mod_log", description="Последние действия AI-модерации")
    @app_commands.describe(count="Количество записей (макс. 25)")
    @app_commands.default_permissions(moderate_members=True)
    async def ai_mod_log(self, interaction: discord.Interaction, count: int = 10):
        count = min(count, 25)
        cursor = await self.db.conn.execute(
            "SELECT user_id, action, reason, confidence, created_at FROM ai_moderation_log "
            "WHERE guild_id = ? ORDER BY created_at DESC LIMIT ?",
            (str(interaction.guild.id), count)
        )
        rows = await cursor.fetchall()
        if not rows:
            return await interaction.response.send_message("📭 Записей нет.", ephemeral=True)

        action_emojis = {"delete": "🗑️", "warn": "⚠️", "mute": "🔇", "none": "✅"}
        lines = []
        for r in rows:
            emoji = action_emojis.get(r["action"], "❓")
            lines.append(f"{emoji} <@{r['user_id']}> — {r['action']} ({r['confidence']:.0%}) — {r['reason'][:50]}")

        embed = discord.Embed(
            title="🤖 Журнал AI-модерации",
            description="\n".join(lines),
            color=Colors.MAIN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================================
    #                ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================================

    @commands.command(name="ai_mod_set")
    @commands.has_permissions(administrator=True)
    async def ai_mod_set_prefix(self, ctx, enabled: str):
        from prefix_adapter import InteractionAdapter, make_choice
        await self.ai_mod_set.callback(self, InteractionAdapter(ctx), make_choice("on" if enabled.lower() in ("on", "вкл", "1", "да") else "off"))

    @commands.command(name="ai_mod_log")
    @commands.has_permissions(moderate_members=True)
    async def ai_mod_log_prefix(self, ctx, count: int = 10):
        from prefix_adapter import InteractionAdapter
        await self.ai_mod_log.callback(self, InteractionAdapter(ctx), count)


async def setup(bot):
    await bot.add_cog(AIModeration(bot))
