import discord
from datetime import timedelta, timezone, datetime
from discord.ext import commands
import os
import sys
import logging
import traceback
from db import Database


logging.getLogger('discord.app_commands').setLevel(logging.CRITICAL)

os.makedirs("data", exist_ok=True)
os.makedirs("cogs", exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import TOKEN, PREFIX
except ImportError:
    print("Ошибка: Файл config.py не найден!")
    exit(1)

if not TOKEN:
    print("Ошибка: TOKEN не задан в .env файле!")
    exit(1)


async def get_dynamic_prefix(bot, message):
    if not message.guild:
        return PREFIX
    db = Database()
    config = await db.get_guild_config(str(message.guild.id))
    return config.get("prefix", PREFIX)


intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.members = True
intents.guilds = True
intents.messages = True
intents.reactions = True
intents.presences = True

bot = commands.Bot(
    command_prefix=get_dynamic_prefix,
    intents=intents,
    help_command=None,
    case_insensitive=True
)


@bot.event
async def on_error(event, *args, **kwargs):
    print(f'Ошибка в {event}: {args} {kwargs}')
    traceback.print_exc()


@bot.event
async def on_ready():
    print(f"Бот {bot.user} успешно запущен!")
    print("Начинаем инициализацию БД...")
    try:
        db = Database()
        await db.init_db()
        print("База данных инициализирована.")
    except Exception as e:
        print(f"Критическая ошибка при инициализации БД: {e}")
        traceback.print_exc()
        await bot.close()
        return
    await load_cogs()
    try:
        synced = await bot.tree.sync()
        print(f"Синхронизировано {len(synced)} слэш-команд.")
    except Exception as e:
        print(f"Ошибка синхронизации команд: {e}")
        traceback.print_exc()


async def load_cogs():
    cogs_loaded, cogs_failed = 0, 0
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename not in ("__init__.py",):
            cog_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                cogs_loaded += 1
            except Exception as e:
                print(f"  ✗ Ошибка загрузки {filename}:")
                traceback.print_exc()
                cogs_failed += 1
    print(f"Итого: {cogs_loaded} когов загружено, {cogs_failed} ошибок")


async def check_modules_slash(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not interaction.command:
        return True
    binding = getattr(interaction.command, "binding", None)
    cog_name = binding.__class__.__name__ if binding else None
    if not cog_name:
        return True
    db = Database()
    config = await db.get_guild_config(str(interaction.guild.id))
    if not config.get("modules", {}).get(cog_name, True):
        error_msg = f"❌ Модуль `{cog_name}` отключен на этом сервере."
        await interaction.response.send_message(error_msg, ephemeral=True)
        return False
    return True

bot.tree.interaction_check = check_modules_slash


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if interaction.response.is_done():
        return
    main_color = discord.Color(0x2b2d31)

    if isinstance(error, discord.app_commands.CommandOnCooldown):
        unix_time = int((datetime.now(timezone.utc) + timedelta(seconds=error.retry_after)).timestamp())
        embed = discord.Embed(
            title="⌛ Перезарядка",
            description=f"**{interaction.user.name}**, команда еще не готова!",
            color=main_color,
        )
        for name, value in [("Попробуйте снова:", f"<t:{unix_time}:R>")]:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text=interaction.user.name)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if isinstance(error, discord.app_commands.MissingPermissions):
        embed = discord.Embed(
            title="⛔ Доступ запрещен",
            description=f"**{interaction.user.name}**, у вас не хватает прав!",
            color=main_color,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    print(f"❌ Ошибка: {error}")
    if not interaction.response.is_done():
        embed = discord.Embed(
            title="❌ Ошибка",
            description=f"Произошла ошибка: {error}",
            color=main_color,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.check
async def check_modules_prefix(ctx):
    if not ctx.guild or not ctx.command or not ctx.command.cog_name:
        return True
    db = Database()
    config = await db.get_guild_config(str(ctx.guild.id))
    if not config.get("modules", {}).get(ctx.command.cog_name, True):
        error_msg = f"❌ Модуль `{ctx.command.cog_name}` отключен на этом сервере."
        await ctx.send(error_msg, delete_after=5)
        return False
    return True


if __name__ == "__main__":
    print("Запуск бота...")
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("Ошибка авторизации! Проверьте TOKEN в .env")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
