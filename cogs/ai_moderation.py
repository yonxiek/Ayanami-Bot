import discord
import json
from datetime import datetime, timezone
from discord.ext import commands
from db import Database
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


async def setup(bot):
    await bot.add_cog(AIModeration(bot))
