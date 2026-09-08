import discord
from discord.ext import commands
from discord import app_commands
from db import Database
from ui_components import Icons, Colors, AyanamiUI



class PermsDashboard(discord.ui.LayoutView):
    def __init__(self, cog, user_id: int, commands_dict: dict):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id
        self.commands_dict = commands_dict
        self.selected_category = None
        self.selected_command = None
        self.build_ui()

    def build_ui(self):
        self.clear_items()
        container = discord.ui.Container(accent_color=discord.Color(0x2b2d31))

        title = "Управление правами" if not self.selected_command else f"Права команды: /{self.selected_command}"
        container.add_item(discord.ui.TextDisplay(f"## {title}"))
        if not self.selected_command:
            container.add_item(discord.ui.TextDisplay("> Выберите категорию и команду ниже для настройки доступа."))

        self.add_item(container)

        cat_options = [discord.SelectOption(label="ВСЕ КАТЕГОРИИ", value="ALL_CATS", emoji="🌐")]
        for cat in self.commands_dict.keys():
            cat_options.append(discord.SelectOption(label=cat, value=cat))
        cat_select = discord.ui.Select(placeholder="📁 1. Выберите категорию", options=cat_options[:25], row=0)
        cat_select.callback = self.cat_callback
        self.add_item(cat_select)

        if self.selected_category:
            cmd_options = [discord.SelectOption(label="ВСЕ КОМАНДЫ", value="ALL_CMDS", emoji="🔥")]
            if self.selected_category != "ALL_CATS":
                cmds = self.commands_dict[self.selected_category][:24]
                for cmd in cmds:
                    cmd_options.append(discord.SelectOption(label=cmd, value=cmd))
            cmd_select = discord.ui.Select(placeholder="🕹️ 2. Выберите команду", options=cmd_options, row=1)
            cmd_select.callback = self.cmd_callback
            self.add_item(cmd_select)

        if self.selected_command:
            allow_select = discord.ui.RoleSelect(placeholder="✅ Разрешить для роли...", row=2)
            allow_select.callback = self.allow_callback
            self.add_item(allow_select)
            deny_select = discord.ui.RoleSelect(placeholder="❌ Запретить для роли...", row=3)
            deny_select.callback = self.deny_callback
            self.add_item(deny_select)
            clear_btn = discord.ui.Button(label="Сбросить правила", style=discord.ButtonStyle.danger, emoji="🗑️", row=4)
            clear_btn.callback = self.clear_callback
            self.add_item(clear_btn)

    async def cat_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        self.selected_category = interaction.data["values"][0]
        self.selected_command = None
        await self.update_message(interaction)

    async def cmd_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        self.selected_command = interaction.data["values"][0]
        await self.update_message(interaction)

    async def apply_rules(self, interaction: discord.Interaction, role_id: str, action: str):
        cmds_to_modify = []
        if self.selected_command == "ALL_CMDS":
            if self.selected_category == "ALL_CATS":
                for cmds in self.commands_dict.values(): cmds_to_modify.extend(cmds)
            else: cmds_to_modify.extend(self.commands_dict[self.selected_category])
        else: cmds_to_modify.append(self.selected_command)
        for cmd in set(cmds_to_modify):
            if action == "clear": await self.cog.clear_rule_db(interaction.guild.id, cmd)
            else: await self.cog.modify_rule_db(interaction.guild.id, cmd, role_id, action)
        await self.update_message(interaction)

    async def allow_callback(self, interaction: discord.Interaction):
        await self.apply_rules(interaction, interaction.data["values"][0], "allow")

    async def deny_callback(self, interaction: discord.Interaction):
        await self.apply_rules(interaction, interaction.data["values"][0], "deny")

    async def clear_callback(self, interaction: discord.Interaction):
        await self.apply_rules(interaction, None, "clear")

    async def update_message(self, interaction: discord.Interaction):
        self.build_ui()
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=self, content=None)
        else:
            await interaction.edit_original_response(view=self, content=None)


class Permissions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = Database()
        self.COG_RU = {
            "Moderation": "🛡️ Модерация",
            "Economy": "💰 Рейды и Экономика",
            "Raids": "⚔️ Система Рейдов",
            "Utils": "🛠️ Утилиты",
            "Dashboard": "⚙️ Настройки",
            "Permissions": "🔒 Права"
        }

    async def cog_load(self):
        prev_check = self.bot.tree.interaction_check

        async def combined_check(interaction: discord.Interaction) -> bool:
            if prev_check is not None:
                if not await prev_check(interaction):
                    return False
            return await self.slash_check(interaction)

        self.bot.tree.interaction_check = combined_check
        self.bot.add_check(self.prefix_check)

    async def get_perms(self, guild_id: int) -> dict:
        config = await self.db.get_guild_config(str(guild_id))
        return config.get('permissions', {"commands": {}})

    async def save_perms(self, guild_id: int, perms: dict):
        await self.db.update_guild_config(str(guild_id), permissions=perms)

    def get_all_commands_grouped(self) -> dict:
        cmds = {}
        for cmd in self.bot.tree.walk_commands():
            if isinstance(cmd, app_commands.Command):
                cog_name = cmd.binding.__class__.__name__ if cmd.binding else "Общие"
                ru_name = self.COG_RU.get(cog_name, f"📁 {cog_name}")
                cmds.setdefault(ru_name, []).append(cmd.qualified_name)
        return cmds

    async def slash_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not interaction.command: return True
        if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator: return True
        cmd_name = interaction.command.qualified_name
        config = await self.db.get_guild_config(str(interaction.guild.id))
        private_cmds = config.get("private_commands", {})
        if cmd_name in private_cmds:
            allowed_role_ids = private_cmds[cmd_name]
            user_role_ids = [str(r.id) for r in interaction.user.roles]
            if not any(rid in allowed_role_ids for rid in user_role_ids):
                return False
        perms = config.get('permissions', {"commands": {}})
        rules = perms.get("commands", {}).get(cmd_name)
        if not rules: return True
        u_roles = [str(r.id) for r in interaction.user.roles]
        if any(rid in rules.get('denied_roles', []) for rid in u_roles):
            embed = discord.Embed(title="Ошибка", description="> У вашей роли нет доступа к этой команде.", color=Colors.MAIN)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        allowed = rules.get('allowed_roles', [])
        if allowed and not any(rid in allowed for rid in u_roles):
            embed = discord.Embed(title="Ошибка", description="> Эта команда доступна только определенным ролям.", color=Colors.MAIN)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    async def prefix_check(self, ctx: commands.Context) -> bool:
        if not ctx.guild or not ctx.command:
            return True
        if ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator:
            return True
        prefix_name = ctx.command.name
        slash_key = None
        for cmd in self.bot.tree.walk_commands():
            if isinstance(cmd, app_commands.Command):
                if cmd.qualified_name == prefix_name or cmd.qualified_name.replace(' ', '_') == prefix_name:
                    slash_key = cmd.qualified_name
                    break
        if slash_key is None:
            return True
        config = await self.db.get_guild_config(str(ctx.guild.id))
        private_cmds = config.get("private_commands", {})
        if slash_key in private_cmds:
            allowed_role_ids = private_cmds[slash_key]
            user_role_ids = [str(r.id) for r in ctx.author.roles]
            if not any(rid in allowed_role_ids for rid in user_role_ids):
                embed = discord.Embed(title="Ошибка", description="> Эта команда вам недоступна.", color=Colors.MAIN)
                await ctx.send(embed=embed)
                return False
        perms = config.get('permissions', {"commands": {}})
        rules = perms.get("commands", {}).get(slash_key)
        if not rules:
            return True
        u_roles = [str(r.id) for r in ctx.author.roles]
        if any(rid in rules.get('denied_roles', []) for rid in u_roles):
            embed = discord.Embed(title="Ошибка", description="> У вашей роли нет доступа к этой команде.", color=Colors.MAIN)
            await ctx.send(embed=embed)
            return False
        allowed = rules.get('allowed_roles', [])
        if allowed and not any(rid in allowed for rid in u_roles):
            embed = discord.Embed(title="Ошибка", description="> Эта команда доступна только определенным ролям.", color=Colors.MAIN)
            await ctx.send(embed=embed)
            return False
        return True

    async def modify_rule_db(self, guild_id, command_name, role_id, action):
        perms = await self.get_perms(guild_id)
        cmd_p = perms["commands"].setdefault(command_name, {"allowed_roles": [], "denied_roles": []})
        role_id = str(role_id)
        if action == "allow":
            if role_id not in cmd_p["allowed_roles"]: cmd_p["allowed_roles"].append(role_id)
            if role_id in cmd_p["denied_roles"]: cmd_p["denied_roles"].remove(role_id)
        elif action == "deny":
            if role_id not in cmd_p["denied_roles"]: cmd_p["denied_roles"].append(role_id)
            if role_id in cmd_p["allowed_roles"]: cmd_p["allowed_roles"].remove(role_id)
        await self.save_perms(guild_id, perms)

    async def clear_rule_db(self, guild_id, command_name):
        perms = await self.get_perms(guild_id)
        if command_name in perms["commands"]:
            del perms["commands"][command_name]
            await self.save_perms(guild_id, perms)

    async def _logic_perms_menu(self, interaction: discord.Interaction):
        cmds_dict = self.get_all_commands_grouped()
        view = PermsDashboard(self, interaction.user.id, cmds_dict)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=view, content=None)
        else:
            await interaction.edit_original_response(view=view, content=None)


async def setup(bot):
    await bot.add_cog(Permissions(bot))
