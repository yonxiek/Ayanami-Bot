import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from db import Database

logging.getLogger('discord.app_commands').setLevel(logging.CRITICAL)

os.makedirs("data", exist_ok=True)
os.makedirs("cogs", exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import PREFIX, TOKEN, ERROR_WEBHOOK_URL
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


async def _send_error_webhook(title: str, error_text: str, *extra: str) -> None:
    if not ERROR_WEBHOOK_URL:
        return
    try:
        webhook = discord.Webhook.from_url(ERROR_WEBHOOK_URL, client=bot)
        description = error_text.strip() or "Без подробностей"
        if extra:
            description += "\n\n" + "\n".join(x for x in extra if x)
        embed = discord.Embed(
            title=title[:256],
            description=(description[:4000] or "Без подробностей"),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        await webhook.send(embed=embed)
    except Exception:
        print("Ошибка при отправке в error-вебхук:")
        traceback.print_exc()


@bot.event
async def on_error(event, *args, **kwargs):
    print(f'Ошибка в {event}: {args} {kwargs}')
    traceback.print_exc()
    await _send_error_webhook(f"Ошибка события: `{event}`", traceback.format_exc(), repr(args[:2]))


@bot.event
async def on_ready():
    bot.start_time = discord.utils.utcnow()
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
        print(f"Префиксных команд: {len(bot.commands)}")
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
            except Exception:
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

    if interaction.type == discord.InteractionType.application_command:
        seconds, bypass = _get_cooldown_config(config)
        if not _cooldown_bypassed(interaction.user.roles, config, bypass):
            remaining = _cooldown_seconds_remaining(
                interaction.guild.id, interaction.user.id,
                interaction.command.qualified_name, seconds
            )
            if remaining > 0:
                embed = discord.Embed(
                    title="⏳ Перезарядка",
                    description=f"**{interaction.user.name}**, команда `/{interaction.command.qualified_name}` ещё перезаряжается!",
                    color=discord.Color(0x2b2d31),
                )
                embed.add_field(name="Попробуйте через:", value=f"**{int(round(remaining))}** секунд", inline=False)
                embed.set_footer(text=interaction.user.name)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return False
    return True

bot.tree.interaction_check = check_modules_slash


_command_cooldowns: dict[tuple[str, str, str], float] = {}


def _get_cooldown_config(config) -> tuple[int, list[str]]:
    seconds = config.get("command_cooldown_seconds", 8)
    try:
        seconds = max(0, int(seconds))
    except (TypeError, ValueError):
        seconds = 8
    bypass = [str(r) for r in (config.get("command_cooldown_bypass_roles", []) or [])]
    return seconds, bypass


def _has_bypass_role(user_roles, bypass_ids: list[str]) -> bool:
    if not bypass_ids:
        return False
    own = {str(r.id) for r in user_roles}
    return bool(set(bypass_ids) & own)


def _cooldown_bypassed(user_roles, config, bypass_ids: list[str]) -> bool:
    """Кулдаун не действует для выбранных ролей, а также админ- и персонал-ролей."""
    if _has_bypass_role(user_roles, bypass_ids):
        return True
    auto = [str(r) for r in ((config.get("admin_roles", []) or []) + (config.get("staff_roles", []) or []))]
    return _has_bypass_role(user_roles, auto)


def _cooldown_seconds_remaining(guild_id, user_id, command_name, seconds) -> float:
    """Возвращает 0, если команду можно вызывать; иначе — сколько секунд осталось."""
    if not seconds:
        return 0.0
    now = time.monotonic()
    key = (str(guild_id), str(user_id), command_name)
    last = _command_cooldowns.get(key, 0.0)
    remaining = last + seconds - now
    if remaining > 0:
        return remaining
    _command_cooldowns[key] = now
    return 0.0


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
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    await _send_error_webhook(
        f"Ошибка команды `/{interaction.command.qualified_name}`" if interaction.command else "Ошибка команды",
        tb, f"Пользователь: {interaction.user} (id: {interaction.user.id})"
    )
    if not interaction.response.is_done():
        embed = discord.Embed(
            title="❌ Ошибка",
            description=f"Произошла ошибка: {error}",
            color=main_color,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return

    main_color = discord.Color(0x2b2d31)

    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Не хватает аргументов",
            description=f"Вы не указали: **`{error.param.name}`**",
            color=main_color,
        )
        embed.add_field(name="Использование", value=f"`{ctx.clean_prefix}{ctx.command.name} {ctx.command.signature}`", inline=False)
        await ctx.send(embed=embed)
        return

    if isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Неверный аргумент",
            description=str(error),
            color=main_color,
        )
        embed.add_field(name="Использование", value=f"`{ctx.clean_prefix}{ctx.command.name} {ctx.command.signature}`", inline=False)
        await ctx.send(embed=embed)
        return

    if isinstance(error, commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions or [])
        embed = discord.Embed(
            title="⛔ Доступ запрещен",
            description=f"**{ctx.author.name}**, у вас не хватает прав: `{perms}`",
            color=main_color,
        )
        await ctx.send(embed=embed)
        return

    if isinstance(error, commands.BotMissingPermissions):
        perms = ", ".join(error.missing_permissions or [])
        embed = discord.Embed(
            title="⛔ Мне не хватает прав",
            description=f"Для этой команды боту нужны права: `{perms}`",
            color=main_color,
        )
        await ctx.send(embed=embed)
        return

    if isinstance(error, commands.CommandOnCooldown):
        unix_time = int((datetime.now(timezone.utc) + timedelta(seconds=error.retry_after)).timestamp())
        embed = discord.Embed(
            title="⌛ Перезарядка",
            description=f"**{ctx.author.name}**, команда еще не готова!",
            color=main_color,
        )
        embed.add_field(name="Попробуйте снова:", value=f"<t:{unix_time}:R>", inline=False)
        await ctx.send(embed=embed)
        return

    if isinstance(error, commands.CheckFailure):
        return

    print(f"❌ Ошибка в команде {ctx.command}: {error}")
    traceback.print_exc()
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    await _send_error_webhook(
        f"Ошибка команды `{ctx.command}`" if ctx.command else "Ошибка команды",
        tb, f"Пользователь: {ctx.author} (id: {ctx.author.id})"
    )


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

    seconds, bypass = _get_cooldown_config(config)
    if not _cooldown_bypassed(ctx.author.roles, config, bypass):
        remaining = _cooldown_seconds_remaining(
            ctx.guild.id, ctx.author.id, ctx.command.qualified_name, seconds
        )
        if remaining > 0:
            await ctx.send(
                f"⏳ Команда `{ctx.command.qualified_name}` ещё перезаряжается! Попробуйте через **{int(round(remaining))}** секунд.",
                delete_after=5,
            )
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
