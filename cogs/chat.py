import time
from collections import deque

import aiohttp
import discord
from discord.ext import commands
from db import Database
import config

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

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
        self.api_key = config.GEMINI_API_KEY
        self.model = config.GEMINI_MODEL
        self.history: dict[tuple, deque] = {}
        self.cooldowns: dict[tuple, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not self.api_key:
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
        hist_key = self._history_key(message)
        history = self.history.setdefault(hist_key, deque(maxlen=HISTORY_LIMIT))

        system_prompt = DEFAULT_SYSTEM_PROMPT.format(server=message.guild.name)
        contents = [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in history]
        contents.append({"role": "user", "parts": [{"text": message.content[:800]}]})

        body = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 250},
        }
        headers = {"Content-Type": "application/json"}
        url = API_URL.format(model=self.model)

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{url}?key={self.api_key}", json=body, headers=headers) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        print(f"❌ Gemini API {resp.status}: {err_text[:300]}")
                        if resp.status in (401, 403):
                            return "🔑 У меня не настроен API-ключ ИИ. Попросите администраторов проверить `GEMINI_API_KEY`."
                        if resp.status == 429:
                            return "😮💨 Слишком много запросов к ИИ — попробуйте чуть позже."
                        return "🤖 Я не смогла ответить — ошибка модели. Попробуйте позже."
                    data = await resp.json()

            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError, TypeError):
                return "🤖 Модель не вернула ответ. Попробуйте ещё раз."

            if not text:
                return "🤖 …"
        except Exception:
            return "🤖 Похоже, сеть упала. Попробуйте позже."

        history.append({"role": "user", "text": message.content[:800]})
        history.append({"role": "model", "text": text[:800]})

        return text[:1800]


async def setup(bot):
    await bot.add_cog(Chat(bot))