import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import random
from db import Database

def format_roblox_nickname(display_name: str, username: str) -> str:
    new_nick = f"{display_name} (@{username})"
    return new_nick if len(new_nick) <= 32 else f"@{username}"[:32]

class RobloxVerifyView(discord.ui.View):
    def __init__(self, cog, discord_id: int, r_username: str, r_id: int, code: str):
        super().__init__(timeout=600)
        self.cog, self.discord_id, self.r_username, self.r_id, self.code = cog, discord_id, r_username, r_id, code
        btn = discord.ui.Button(label="Проверить код", style=discord.ButtonStyle.green)
        btn.callback = self.check_callback
        self.add_item(btn)

    async def check_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.discord_id: 
            return await interaction.response.send_message("Это не ваше меню.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://users.roblox.com/v1/users/{self.r_id}") as r:
                    data = await r.json()
                    if self.code in data.get("description", ""):
                        await self.cog.db.save_roblox_account(str(self.discord_id), str(self.r_id), self.r_username, data.get("displayName", self.r_username))
                        try: await interaction.user.edit(nick=format_roblox_nickname(data.get("displayName", self.r_username), self.r_username))
                        except: pass
                        await interaction.followup.send(f"Аккаунт **{self.r_username}** успешно привязан!", ephemeral=True)
                    else: 
                        await interaction.followup.send("Код не найден в описании профиля (О себе).", ephemeral=True)
        except: 
            await interaction.followup.send("Ошибка API Roblox.", ephemeral=True)

class RobloxLinkModal(discord.ui.Modal, title="Никнейм Roblox"):
    username = discord.ui.TextInput(label="Ваш никнейм в Roblox", min_length=3, max_length=25)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [self.username.value]}) as r:
                    data = await r.json()
                    if not data.get("data"): 
                        return await interaction.followup.send(f"Аккаунт **{self.username.value}** не найден.", ephemeral=True)
                    r_id, r_name = data["data"][0]["id"], data["data"][0]["name"]
            
            code = f"VERIFY-{random.randint(1000,9999)}"
            desc = f"Аккаунт: **{r_name}**\nСкопируйте этот код и вставьте его в описание профиля Roblox (О себе):\n```\n{code}\n```\nПосле этого нажмите кнопку «Проверить код»."
            embed = discord.Embed(description=desc, color=discord.Color.blue())
            await interaction.followup.send(embed=embed, view=RobloxVerifyView(self.cog, interaction.user.id, r_name, r_id, code), ephemeral=True)
        except: 
            await interaction.followup.send("Ошибка при обработке запроса.", ephemeral=True)

class RobloxMenuView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Привязать Roblox", style=discord.ButtonStyle.blurple, custom_id="rbx_main_btn")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RobloxLinkModal(self.cog))


class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def cog_load(self):
        self.bot.add_view(RobloxMenuView(self))

    @app_commands.command(name="unlink", description="Отвязать аккаунт Roblox от Discord")
    async def roblox_unlink(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.db.delete_roblox_account(str(interaction.user.id))
        try: await interaction.user.edit(nick=None)
        except: pass 
        await interaction.followup.send("Аккаунт Roblox отвязан. Никнейм сброшен.", ephemeral=True)

    @app_commands.command(name="set_verify", description="Настроить роли для ручной верификации (Админ)")
    @app_commands.default_permissions(administrator=True)
    async def set_verify_slash(self, interaction: discord.Interaction, verified_role: discord.Role, unverified_role: discord.Role = None):
        config = await self.db.get_guild_config(str(interaction.guild.id))
        if 'verification' not in config: config['verification'] = {}
        
        config['verification']['verified_roles'] = [verified_role.id]
        if unverified_role:
            config['verification']['unverified_role_id'] = unverified_role.id
        
        await self.db.update_guild_config(str(interaction.guild.id), **config)
        await interaction.response.send_message(f"Настройки сохранены. Выдача: {verified_role.name}, Удаление: {unverified_role.name if unverified_role else 'Нет'}", ephemeral=True)

    @app_commands.command(name="verify", description="Ручная верификация пользователя (Админ)")
    @app_commands.default_permissions(administrator=True)
    async def verify_slash(self, interaction: discord.Interaction, member: discord.Member):
        guild = interaction.guild
        config = await self.db.get_guild_config(str(guild.id))
        vc = config.get('verification', {})
        
        if not vc:
            return await interaction.response.send_message("Настройки не найдены. Используйте /set_verify.", ephemeral=True)

        try:
            for rid in vc.get("verified_roles", []):
                role = guild.get_role(rid)
                if role: await member.add_roles(role)
            
            unverified_id = vc.get("unverified_role_id")
            if unverified_id:
                role = guild.get_role(unverified_id)
                if role: await member.remove_roles(role)

            await interaction.response.send_message(f"Пользователь {member.display_name} успешно верифицирован.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Ошибка прав! Бот не может выдавать эту роль (проверьте иерархию ролей).", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Verification(bot))
