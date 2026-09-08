import discord
import random
from discord.ext import commands
from db import Database


DEFAULT_REACTIONS = {
    "спс": ["❤️"],
    "спасибо": ["❤️"],
    "thanks": ["❤️"],
    "thank you": ["❤️"],
    "хай": ["👋"],
    "привет": ["👋"],
    "hello": ["👋"],
    "hi": ["👋"],
    "лол": ["😂"],
    "ахах": ["😂"],
    "хаха": ["😂"],
    "ахахах": ["😂"],
    "кек": ["😂"],
    "грустно": ["😔"],
    "печально": ["😔"],
    "грусть": ["😔"],
    "хорошо": ["👍"],
    "норм": ["👍"],
    "ок": ["👍"],
    "окей": ["👍"],
    "люблю": ["💕"],
    "love": ["💕"],
    "помоги": ["🆘"],
    "help": ["🆘"],
    "пж": ["🙏"],
    "пожалуйста": ["🙏"],
    "please": ["🙏"],
    "круто": ["🔥"],
    "огонь": ["🔥"],
    "fire": ["🔥"],
    "класс": ["⭐"],
    "супер": ["⭐"],
    "wow": ["😮"],
    "вау": ["😮"],
    "нет": ["👎"],
    "no": ["👎"],
    "ужас": ["💀"],
    "death": ["💀"],
}


class Reactions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if message.author.bot:
            return

        text = message.content.lower().strip()

        config = await self.db.get_guild_config(str(message.guild.id))
        custom_reactions = config.get("reactions", {})

        all_reactions = {}
        for k, v in DEFAULT_REACTIONS.items():
            if isinstance(v, str):
                v = [v]
            elif not isinstance(v, list):
                v = [str(v)]
            all_reactions[k] = v
        for k, v in custom_reactions.items():
            if isinstance(v, str):
                v = [e.strip() for e in v.replace(";", ",").replace(" ", ",").split(",") if e.strip()]
            elif isinstance(v, list):
                fixed = []
                for item in v:
                    if isinstance(item, str) and (" " in item or ";" in item):
                        fixed.extend([e.strip() for e in item.replace(";", ",").replace(" ", ",").split(",") if e.strip()])
                    else:
                        fixed.append(item)
                v = fixed
            else:
                v = [str(v)]
            all_reactions[k] = v

        for trigger, emojis in all_reactions.items():
            if trigger in text:
                for emoji in emojis:
                    try:
                        await message.add_reaction(emoji)
                    except Exception:
                        pass
                break


async def setup(bot):
    await bot.add_cog(Reactions(bot))
