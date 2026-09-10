"""Веб-дашборд для мониторинга бота.

Запускается как отдельный aiohttp-сервер внутри кога.
Доступ защищён базик-аутентификацией (DASHBOARD_SECRET из .env).
"""

import discord
import json
from aiohttp import web
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
from db import Database
from ui_components import Colors
import config


class DashboardPages(commands.Cog):
    """Лёгкий веб-дашборд: статистика бота, статус серверов, база данных."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.app = None
        self.runner = None

    async def cog_load(self):
        if not config.DASHBOARD_SECRET:
            return
        self.app = web.Application()
        self.app.router.add_get("/", self._page_index)
        self.app.router.add_get("/api/stats", self._api_stats)
        self.app.router.add_get("/api/guilds", self._api_guilds)
        self.app.router.add_get("/api/db", self._api_db)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, config.DASHBOARD_HOST, config.DASHBOARD_PORT)
        await site.start()
        print(f"📊 Веб-дашборд запущен: http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()

    def _check_auth(self, request: web.Request) -> bool:
        secret = request.query.get("key", "") or request.headers.get("X-API-KEY", "")
        return secret == config.DASHBOARD_SECRET

    async def _page_index(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized. Add ?key=YOUR_SECRET")
        return web.Response(
            text=(
                "<html><body style='font-family:sans-serif;background:#1a1a1a;color:#fff'>"
                "<h1>Ayanami System — Dashboard</h1>"
                "<p><a href='/api/stats?key'>Статистика бота</a></p>"
                "<p><a href='/api/guilds?key'>Серверы</a></p>"
                "<p><a href='/api/db?key'>Таблицы БД</a></p>"
                "</body></html>"
            ),
            content_type="text/html",
        )

    async def _api_stats(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        uptime = (datetime.now(timezone.utc) - self.bot.started_at).total_seconds() if hasattr(self.bot, "started_at") else 0
        data = {
            "guilds": len(self.bot.guilds),
            "users": sum(g.member_count for g in self.bot.guilds),
            "shards": self.bot.shard_count or 1,
            "commands": len(self.bot.tree.get_commands()),
            "uptime_seconds": round(uptime),
            "latency_ms": round(self.bot.latency * 1000, 1),
        }
        return web.json_response(data)

    async def _api_guilds(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        data = []
        for g in self.bot.guilds:
            data.append({
                "id": str(g.id),
                "name": g.name,
                "members": g.member_count,
                "channels": len(g.channels),
                "icon": g.icon.url if g.icon else None,
            })
        return web.json_response(data)

    async def _api_db(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        tables = {}
        cursor = await self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        for row in await cursor.fetchall():
            name = row[0]
            cnt_cursor = await self.db.conn.execute(f"SELECT COUNT(*) FROM {name}")
            count_row = await cnt_cursor.fetchone()
            tables[name] = count_row[0]
        return web.json_response(tables)

    # Никаких slash-команд, вопрос открыт на будущее.
    # ==========================================================
    #                ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================================

    @commands.command(name="dashboard_start")
    @commands.is_owner()
    async def dashboard_start(self, ctx):
        if config.DASHBOARD_SECRET:
            await ctx.send(f"📊 Дашборд уже запущен, если был включён.")
        else:
            await ctx.send("❌ DASHBOARD_SECRET не задан в .env.")


async def setup(bot):
    bot.started_at = datetime.now(timezone.utc)
    await bot.add_cog(DashboardPages(bot))