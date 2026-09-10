import time
from collections import deque

import discord
from discord.ext import commands
from db import Database
import ai_client

DEFAULT_SYSTEM_PROMPT = (
    "Ты — Аянами, дружелюбный Discord-бот русского сервера «{server}». "
    "Отвечай кратко (до 3-4 предложений), тепло и с лёгким юмором. "
    "Пиши на русском языке. Не притворяйся человеком."
)

HISTORY_LIMIT = 20


class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.history: dict[tuple, deque] = {}
        self.cooldowns: dict[tuple, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        config_data = await self.db.get_guild_config(str(message.guild.id))
        if not config_data.get("chat_enabled", False):
            return

        text = message.content
        if not text or text.lower().startswith(config_data.get("prefix", "!")):
            return

        channel_id = config_data.get("chat_channel_id")
        mentioned = self.bot.user in message.mentions

        if channel_id:
            if message.channel.id != int(channel_id):
                return
        else:
            if not mentioned and not self._is_reply_to_bot(message):
                return

        cooldown = int(config_data.get("chat_cooldown_seconds", 3) or 3)
        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        if now - self.cooldowns.get(key, 0) < cooldown:
            return
        self.cooldowns[key] = now

        async with message.channel.typing():
            reply = await self._ask_ai(message)
        if reply:
            await message.reply(reply, mention_author=False)

    def _is_reply_to_bot(self, message: discord.Message) -> bool:
        ref = message.reference
        if not ref or ref.resolved is None:
            return False
        return ref.resolved.author.id == self.bot.user.id

    def _history_key(self, message) -> tuple:
        return (message.guild.id, message.channel.id)

    async def _ask_ai(self, message: discord.Message) -> str | None:
        guild_id = str(message.guild.id)
        config_data = await self.db.get_guild_config(guild_id)
        provider = ai_client.normalize_provider(config_data.get("ai_provider"))

        hist_key = self._history_key(message)
        history = self.history.setdefault(hist_key, deque(maxlen=HISTORY_LIMIT))

        system_prompt = DEFAULT_SYSTEM_PROMPT.format(server=message.guild.name)
        messages = list(history)
        messages.append({"role": "user", "content": message.content[:800]})

        try:
            reply = await ai_client.complete(
                system_prompt,
                messages,
                provider=provider,
                temperature=0.9,
                max_tokens=250,
            )
        except Exception:
            return "🤖 Похоже, сеть упала. Попробуйте позже."

        if reply is None:
            return "🤖 Не удалось получить ответ от ИИ. Проверьте настройки провайдера (`/setup` или `.env`)."
        if not reply.strip():
            return "🤖 Модель не вернула ответ. Попробуйте ещё раз."

        history.append({"role": "user", "text": message.content[:800]})
        history.append({"role": "model", "text": reply[:800]})

        return reply[:1800]


async def setup(bot):
    await bot.add_cog(Chat(bot))