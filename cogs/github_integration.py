import discord
import aiohttp
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors

GITHUB_API = "https://api.github.com"


class GitHubIntegration(commands.Cog):
    """Интеграция с GitHub: отслеживание репозиториев, уведомления о коммитах и PR."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @app_commands.command(name="github_commits", description="Последние коммиты репозитория")
    @app_commands.describe(repo="Репозиторий (owner/name)", count="Количество (макс. 10)")
    async def github_commits(self, interaction: discord.Interaction, repo: str, count: int = 5):
        count = min(count, 10)
        await interaction.response.defer()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GITHUB_API}/repos/{repo}/commits?per_page={count}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return await interaction.followup.send("❌ Ошибка API.", ephemeral=True)
                data = await resp.json()

        if not data:
            return await interaction.followup.send("📭 Коммитов нет.", ephemeral=True)

        lines = []
        for c in data:
            author = c.get("commit", {}).get("author", {}).get("name", "Unknown")
            msg = c.get("commit", {}).get("message", "")[:80]
            sha = c["sha"][:7]
            lines.append(f"`{sha}` {msg}\n*— {author}*")

        embed = discord.Embed(
            title=f"📝 Последние коммиты: {repo}",
            description="\n\n".join(lines),
            color=Colors.MAIN,
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="github_pr", description="Последние Pull Requests")
    @app_commands.describe(repo="Репозиторий (owner/name)")
    async def github_pr(self, interaction: discord.Interaction, repo: str):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GITHUB_API}/repos/{repo}/pulls?state=open&per_page=5",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return await interaction.followup.send("❌ Ошибка API.", ephemeral=True)
                data = await resp.json()

        if not data:
            return await interaction.followup.send("📭 Открытых PR нет.", ephemeral=True)

        lines = []
        for pr in data:
            user = pr.get("user", {}).get("login", "Unknown")
            lines.append(f"**#{pr['number']}** {pr['title'][:60]}\n*от {user}* — {pr['html_url']}")

        embed = discord.Embed(
            title=f"🔀 Pull Requests: {repo}",
            description="\n\n".join(lines),
            color=Colors.MAIN,
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="github_issues", description="Последние Issues")
    @app_commands.describe(repo="Репозиторий (owner/name)")
    async def github_issues(self, interaction: discord.Interaction, repo: str):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GITHUB_API}/repos/{repo}/issues?state=open&per_page=5",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return await interaction.followup.send("❌ Ошибка API.", ephemeral=True)
                data = await resp.json()

        issues = [i for i in data if "pull_request" not in i]
        if not issues:
            return await interaction.followup.send("📭 Открытых Issues нет.", ephemeral=True)

        lines = []
        for i in issues:
            user = i.get("user", {}).get("login", "Unknown")
            labels = ", ".join(l["name"] for l in i.get("labels", [])[:3])
            label_text = f" [{labels}]" if labels else ""
            lines.append(f"**#{i['number']}** {i['title'][:60]}{label_text}\n*от {user}* — {i['html_url']}")

        embed = discord.Embed(
            title=f"🐛 Issues: {repo}",
            description="\n\n".join(lines),
            color=Colors.MAIN,
        )
        await interaction.followup.send(embed=embed)

    # ==========================================================
    #                ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================================

    @commands.command(name="github_commits")
    async def github_commits_prefix(self, ctx, repo: str, count: int = 5):
        await self.github_commits.callback(self, InteractionAdapter(ctx), repo, count)

    @commands.command(name="github_pr")
    async def github_pr_prefix(self, ctx, repo: str):
        await self.github_pr.callback(self, InteractionAdapter(ctx), repo)

    @commands.command(name="github_issues")
    async def github_issues_prefix(self, ctx, repo: str):
        await self.github_issues.callback(self, InteractionAdapter(ctx), repo)


async def setup(bot):
    await bot.add_cog(GitHubIntegration(bot))
