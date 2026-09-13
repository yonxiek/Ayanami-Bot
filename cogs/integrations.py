"""Интеграции: /weather по ключу OpenWeatherMap (ключ задаётся в /setup → «Интеграции»)."""

import aiohttp

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from ui_components import Colors


class Integrations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(name="weather", description="Погода в городе (ключ OpenWeather — в /setup → Интеграции)")
    @app_commands.describe(город="Название города (можно с регионом: Москва, RU)")
    async def weather(self, interaction: discord.Interaction, город: str):
        await interaction.response.defer(ephemeral=True)
        config = await self.db.get_guild_config(str(interaction.guild.id))
        api_key = config.get("weather_api_key")
        if not api_key:
            return await interaction.followup.send(
                "🌦 Для погоды нужен ключ OpenWeatherMap. Админ может задать его в `/setup` → «Интеграции».",
                ephemeral=True,
            )

        params = {"q": город, "appid": api_key, "units": "metric", "lang": "ru"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    status = resp.status
                    data = await resp.json()
        except Exception as e:
            return await interaction.followup.send(f"❌ Ошибка запроса к OpenWeather: {e}", ephemeral=True)

        if status != 200 or "main" not in data:
            reason = data.get("message", "неизвестная ошибка")
            return await interaction.followup.send(
                f"❌ Город `{город}` не найден ({reason}).", ephemeral=True
            )

        city = data.get("name", город)
        main = data["main"]
        weather = (data.get("weather") or [{}])[0]
        icon = weather.get("icon", "")
        country = (data.get("sys") or {}).get("country", "")

        embed = discord.Embed(
            title=f"🌤 Погода: {city}{f', {country}' if country else ''}",
            description=f"**{weather.get('description', '').capitalize() or '—'}**",
            color=Colors.MAIN,
        )
        embed.add_field(
            name="🌡 Температура",
            value=f"{main['temp']:.0f}°C (ощущается {main.get('feels_like', main['temp']):.0f}°C)",
            inline=True,
        )
        embed.add_field(name="💧 Влажность", value=f"{main.get('humidity', 0)}%", inline=True)
        embed.add_field(name="🌬 Ветер", value=f"{data.get('wind', {}).get('speed', 0)} м/с", inline=True)
        embed.add_field(
            name="☀️ День/ночь",
            value="Ночь 🌙" if weather.get("icon", "").endswith("n") else "День ☀️",
            inline=True,
        )
        if icon:
            embed.set_thumbnail(url=f"https://openweathermap.org/img/wn/{icon}@2x.png")
        embed.set_footer(text="OpenWeatherMap")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="weather")
    async def weather_prefix(self, ctx, *, город: str):
        from prefix_adapter import InteractionAdapter
        await self.weather.callback(self, InteractionAdapter(ctx), город)


async def setup(bot):
    await bot.add_cog(Integrations(bot))