import time
import random
import discord
from discord.ext import commands
from db import Database


DEFAULT_RESPONSES = {
    "спс": ["Всегда пожалуйста! 😊", "Не за что! 😊"],
    "спасибо": ["Всегда пожалуйста! 😊", "Обращайтесь! 😊"],
    "thanks": ["You're welcome! 😊", "No problem! 😊"],
    "thank you": ["You're welcome! 😊", "No problem! 😊"],
    "хай": ["Привет! 👋", "Приветик! 👋"],
    "привет": ["Привет! 👋", "Здарова! 👋"],
    "hello": ["Hello! 👋", "Hi!"],
    "hi": ["Hello! 👋", "Hi!"],
    "лол": ["😂"],
    "ахах": ["😂"],
    "хаха": ["😂"],
    "ахахах": ["😂"],
    "кек": ["😂"],
    "мда": ["Мда... 😅"],
    "грустно": ["Эй, не грусти! 💙", "Всё наладится! 💙"],
    "печально": ["Эй, не грусти! 💙", "Всё наладится! 💙"],
    "грусть": ["Всё наладится! 💙"],
    "хорошо": ["Отлично! 👍"],
    "норм": ["Круто! 👍"],
    "ок": ["Ок! 👍", "Договорились! 👍"],
    "окей": ["Окей! 👍", "Договорились! 👍"],
    "люблю": ["💕"],
    "love": ["💕"],
    "помоги": ["Нужна помощь? Напишите `/help`! 🆘"],
    "help": ["Команды найдёте в `/help`! 🆘"],
    "пж": ["Пожалуйста! 🙏"],
    "пожалуйста": ["Пожалуйста! 🙏", "Не за что! 🙏"],
    "please": ["Please! 🙏"],
    "круто": ["🔥"],
    "огонь": ["Огонь! 🔥"],
    "fire": ["🔥"],
    "класс": ["⭐"],
    "супер": ["Супер! ⭐"],
    "wow": ["Вау! 😮"],
    "вау": ["Вау! 😮"],
    "нет": ["Жаль... 👎"],
    "no": ["No... 👎"],
    "ужас": ["💀"],
    "death": ["💀"],
}

REPLY_COOLDOWN_SECONDS = 15


class Responses(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self._cooldown: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if message.author.bot:
            return

        text = message.content.lower().strip()
        if not text:
            return

        config = await self.db.get_guild_config(str(message.guild.id))

        prefix = config.get("prefix", "!")
        if text.startswith(prefix):
            return

        custom = config.get("responses", {})
        if not custom:
            old = config.get("reactions", {})
            if old:
                custom = {}
                for trigger, emojis in old.items():
                    if isinstance(emojis, str):
                        emojis = [emojis.rstrip(",")]
                    custom[trigger] = [str(e) for e in emojis] if isinstance(emojis, list) else [str(emojis)]
                await self.db.update_config_field(str(message.guild.id), "responses", custom)
            if not custom:
                return

        all_responses = dict(DEFAULT_RESPONSES)
        all_responses.update(custom)

        now = time.time()
        key = (message.guild.id, message.author.id)
        last = self._cooldown.get(key, 0)
        if now - last < REPLY_COOLDOWN_SECONDS:
            return

        for trigger, variants in all_responses.items():
            if trigger not in text:
                continue
            if isinstance(variants, str):
                variants = [variants]
            elif not isinstance(variants, list):
                variants = [str(variants)]
            reply = random.choice([v for v in variants if str(v).strip()] or [str(variants[0])])
            self._cooldown[key] = now
            try:
                await message.reply(reply, mention_author=False)
            except Exception:
                pass
            break


async def setup(bot):
    await bot.add_cog(Responses(bot))