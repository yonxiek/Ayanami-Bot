import discord
from discord.ext import commands
from db import Database


class Activities(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()


async def setup(bot):
    await bot.add_cog(Activities(bot))
