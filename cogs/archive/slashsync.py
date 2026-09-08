import discord
from discord.ext import commands
from discord import app_commands
import asyncio

class SlashSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.syncing = False

    sync_group = app_commands.Group(name="sync", description="Управление синхронизацией команд")

    async def get_command_list(self, guild: discord.Guild = None) -> str:
        cmds = self.bot.tree.get_commands(guild=guild)
        if not cmds: return "Нет команд."
        lines = []
        for cmd in cmds:
            if isinstance(cmd, app_commands.Group):
                lines.append(f"- `/{cmd.name}` - группа команд")
                for sub in cmd.commands:
                    lines.append(f"  - `/{cmd.name} {sub.name}` - {sub.description or 'Нет описания'}")
            else:
                lines.append(f"- `/{cmd.name}` - {cmd.description or 'Нет описания'}")
        return "\n".join(lines[:50])

    # ==========================================
    #             СЛЭШ-КОМАНДЫ
    # ==========================================

    @sync_group.command(name="all", description="Полная синхронизация глобальных команд")
    @app_commands.default_permissions(administrator=True)
    async def sync_all_slash(self, interaction: discord.Interaction):
        await self._logic_sync(interaction, "global")

    @sync_group.command(name="guild", description="Синхронизация команд текущего сервера")
    @app_commands.default_permissions(administrator=True)
    async def sync_guild_slash(self, interaction: discord.Interaction):
        await self._logic_sync(interaction, "guild")

    @sync_group.command(name="list", description="Список зарегистрированных команд")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(scope=[
        app_commands.Choice(name="Глобальные", value="global"),
        app_commands.Choice(name="Серверные", value="guild")
    ])
    async def sync_list_slash(self, interaction: discord.Interaction, scope: app_commands.Choice[str]):
        await self._logic_list(interaction, scope.value)

    @sync_group.command(name="info", description="Информация о конкретной команде")
    @app_commands.default_permissions(administrator=True)
    async def sync_info_slash(self, interaction: discord.Interaction, command_name: str):
        await self._logic_info(interaction, command_name)

    # ==========================================
    #           ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================

    @commands.group(name="sync", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def sync_prefix(self, ctx):
        await ctx.send("Используйте подкоманды: all, guild, list, info")

    @sync_prefix.command(name="all")
    @commands.has_permissions(administrator=True)
    async def sync_all_prefix(self, ctx):
        await self._logic_sync(ctx, "global")

    @sync_prefix.command(name="guild")
    @commands.has_permissions(administrator=True)
    async def sync_guild_prefix(self, ctx):
        await self._logic_sync(ctx, "guild")

    @sync_prefix.command(name="list")
    @commands.has_permissions(administrator=True)
    async def sync_list_prefix(self, ctx, scope: str = "global"):
        if scope not in ["global", "guild"]: return await ctx.send("Укажите 'global' или 'guild'.")
        await self._logic_list(ctx, scope)

    @sync_prefix.command(name="info")
    @commands.has_permissions(administrator=True)
    async def sync_info_prefix(self, ctx, command_name: str):
        await self._logic_info(ctx, command_name)

    # ==========================================
    #              ОБЩАЯ ЛОГИКА
    # ==========================================

    async def _send_msg(self, context, text=None, embed=None):
        if isinstance(context, discord.Interaction):
            if not context.response.is_done():
                if embed: await context.response.send_message(embed=embed, ephemeral=True)
                else: await context.response.send_message(text, ephemeral=True)
            else:
                if embed: await context.followup.send(embed=embed, ephemeral=True)
                else: await context.followup.send(text, ephemeral=True)
        else:
            if embed: await context.send(embed=embed)
            else: await context.send(text)

    async def _logic_sync(self, context, scope):
        if self.syncing:
            return await self._send_msg(context, "Синхронизация уже идет. Пожалуйста, подождите.")
        
        self.syncing = True
        if isinstance(context, discord.Interaction): await context.response.defer(ephemeral=True)

        try:
            if scope == "global":
                cmds = await self.bot.tree.sync()
                msg = f"Синхронизация завершена. Обновлено {len(cmds)} глобальных команд."
            else:
                cmds = await self.bot.tree.sync(guild=context.guild)
                msg = f"Синхронизация завершена. Обновлено {len(cmds)} команд для текущего сервера."
            
            embed = discord.Embed(title="Система синхронизации", description=msg, color=discord.Color.green())
            await self._send_msg(context, embed=embed)
        except Exception as e:
            embed = discord.Embed(title="Ошибка синхронизации", description=str(e), color=discord.Color.red())
            await self._send_msg(context, embed=embed)
        finally:
            self.syncing = False

    async def _logic_list(self, context, scope):
        embed = discord.Embed(title="Список команд", color=discord.Color.blue())
        if scope == "global":
            cmd_list = await self.get_command_list()
            embed.add_field(name="Глобальные", value=cmd_list[:1024], inline=False)
        else:
            cmd_list = await self.get_command_list(guild=context.guild)
            embed.add_field(name=f"Сервер {context.guild.name}", value=cmd_list[:1024], inline=False)
        await self._send_msg(context, embed=embed)

    async def _logic_info(self, context, command_name):
        cmd = self.bot.tree.get_command(command_name)
        if not cmd:
            return await self._send_msg(context, "Команда не найдена.")

        embed = discord.Embed(title=f"Информация о команде: /{command_name}", color=discord.Color.blue())
        embed.add_field(name="Описание", value=cmd.description or "Нет описания", inline=False)

        if hasattr(cmd, 'options') and cmd.options:
            options_text = []
            for opt in cmd.options:
                req = "обязательный" if opt.required else "необязательный"
                options_text.append(f"`{opt.name}` - {opt.description or 'Нет описания'} ({req})")
            embed.add_field(name="Параметры", value="\n".join(options_text), inline=False)

        await self._send_msg(context, embed=embed)

async def setup(bot):
    await bot.add_cog(SlashSync(bot))