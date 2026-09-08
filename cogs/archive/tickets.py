import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
from datetime import datetime
from db import Database

# Базовая анкета для верификации на сервере
VERIFICATION_FORM = "Анкета для вступления\n\n1. Как вас зовут / ваш ник?\n2. Откуда узнали о сервере?\n3. Сколько вам лет?\n4. В какие игры играете?"

async def generate_transcript(channel):
    msgs = [m async for m in channel.history(limit=500, oldest_first=True)]
    h = "<html><head><meta charset='utf-8'></head><body style='background-color:#313338;color:#dcdee1;font-family:sans-serif;'>"
    for m in msgs: 
        time_str = m.created_at.strftime("%Y-%m-%d %H:%M")
        h += f"<p><span style='color:#949ba4'>[{time_str}]</span> <b>{m.author.name}</b>: {m.content}</p>"
    h += "</body></html>"
    return discord.File(fp=io.BytesIO(h.encode()), filename=f"transcript-{channel.name}.html")

async def is_authorized(it: discord.Interaction):
    cog = it.client.get_cog("Tickets")
    config = (await cog.db.get_guild_config(str(it.guild.id))) or {}
    staff_roles = config.get("tickets", {}).get("staff_roles", [])
    admin_roles = config.get("admin_roles", [])
    allowed = set(staff_roles + admin_roles)
    return it.user.guild_permissions.administrator or any(r.id in allowed for r in it.user.roles)

# ================= VIEWS =================

class ConfirmView(discord.ui.View):
    def __init__(self, action, user_id):
        super().__init__(timeout=120)
        self.action = action
        self.user_id = user_id
        
    @discord.ui.button(label="Да / Yes", style=discord.ButtonStyle.green)
    async def confirm(self, it: discord.Interaction, btn: discord.ui.Button): 
        if it.user.id != self.user_id: return await it.response.send_message("Это не ваша кнопка.", ephemeral=True)
        await it.client.get_cog("Tickets").execute_close_action(it, self.action)
        
    @discord.ui.button(label="Отмена / Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, it: discord.Interaction, btn: discord.ui.Button): 
        if it.user.id != self.user_id: return await it.response.send_message("Это не ваша кнопка.", ephemeral=True)
        await it.response.defer()
        try: await it.delete_original_response()
        except: pass

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim | Взять", custom_id="tc_claim", style=discord.ButtonStyle.green)
    async def claim(self, it: discord.Interaction, btn: discord.ui.Button):
        if not await is_authorized(it): return await it.response.send_message("Нет прав.", ephemeral=True)
        await it.response.defer(ephemeral=True)
        
        cog = it.client.get_cog("Tickets")
        config = (await cog.db.get_guild_config(str(it.guild.id))) or {}
        staff_roles = config.get("tickets", {}).get("staff_roles", [])
        admin_roles = config.get("admin_roles", [])
        ping_role = config.get("staff_ping_role")

        overwrites = it.channel.overwrites
        overwrites[it.user] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
        
        roles_to_hide = staff_roles + admin_roles
        if ping_role: roles_to_hide.append(ping_role)
            
        for r_id in set(roles_to_hide):
            role = it.guild.get_role(r_id)
            if role: overwrites[role] = discord.PermissionOverwrite(read_messages=False)
            
        try: await it.channel.edit(overwrites=overwrites, name=f"claimed-{it.user.name[:10]}")
        except: pass

        await it.message.edit(view=TicketClaimedView())
        embed = discord.Embed(description=f"Модератор {it.user.mention} взял тикет. Он поможет вам в ближайшее время.", color=discord.Color.green())
        await it.channel.send(embed=embed) 
        await it.followup.send("Вы взяли тикет.", ephemeral=True)

    @discord.ui.button(label="Close | Закрыть", custom_id="tc_close", style=discord.ButtonStyle.grey)
    async def close(self, it: discord.Interaction, btn: discord.ui.Button):
        if not await is_authorized(it): return await it.response.send_message("Нет прав.", ephemeral=True)
        await it.response.send_message("Закрыть тикет?", view=ConfirmView("close", it.user.id), ephemeral=True)


class TicketClaimedView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify & Close | Принять", custom_id="tcl_verify", style=discord.ButtonStyle.success)
    async def v_close(self, it: discord.Interaction, btn: discord.ui.Button):
        if not await is_authorized(it): return await it.response.send_message("Нет прав.", ephemeral=True)
        await it.response.send_message("Выдать роли верификации и закрыть тикет?", view=ConfirmView("verify", it.user.id), ephemeral=True)

    @discord.ui.button(label="Close | Закрыть", custom_id="tcl_close", style=discord.ButtonStyle.grey)
    async def close(self, it: discord.Interaction, btn: discord.ui.Button):
        if not await is_authorized(it): return await it.response.send_message("Нет прав.", ephemeral=True)
        await it.response.send_message("Просто закрыть тикет?", view=ConfirmView("close", it.user.id), ephemeral=True)


class TicketClosedStaffView(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Transcript | Транскрипт", style=discord.ButtonStyle.blurple, custom_id="cl_ts")
    async def ts(self, it: discord.Interaction, b: discord.ui.Button): 
        if not await is_authorized(it): return await it.response.send_message("Нет прав.", ephemeral=True)
        await it.response.defer(ephemeral=True)
        await it.followup.send("Транскрипт сгенерирован:", file=await generate_transcript(it.channel), ephemeral=True)
        
    @discord.ui.button(label="Delete | Удалить", style=discord.ButtonStyle.red, custom_id="cl_del")
    async def dl(self, it: discord.Interaction, b: discord.ui.Button): 
        if not await is_authorized(it): return await it.response.send_message("Нет прав.", ephemeral=True)
        await it.client.get_cog("Tickets").delete_ticket(it)

class CombinedPanelView(discord.ui.View):
    def __init__(self, t_type):
        super().__init__(timeout=None)
        self.t_type = t_type
        labels = {"verif": "Создать тикет (Верификация)", "support": "Создать тикет (Поддержка)"}
        styles = {"verif": discord.ButtonStyle.green, "support": discord.ButtonStyle.grey}
        
        b = discord.ui.Button(label=labels.get(t_type, "Создать"), style=styles.get(t_type, discord.ButtonStyle.primary), custom_id=f"panel_open_{t_type}")
        b.callback = self.c
        self.add_item(b)
    
    async def c(self, it: discord.Interaction):
        cog = it.client.get_cog("Tickets")
        config = (await cog.db.get_guild_config(str(it.guild.id))) or {}
        v_cfg = config.get("verification", {})
        
        unverified_id = v_cfg.get("unverified_role_id")
        verified_roles = v_cfg.get("verified_roles", [])
        user_roles = [r.id for r in it.user.roles]
        
        if self.t_type == "verif" and unverified_id and unverified_id not in user_roles:
            return await it.response.send_message("У вас уже есть доступ или отсутствует роль не верифицированного.", ephemeral=True)
            
        if self.t_type == "support" and verified_roles and not any(r in verified_roles for r in user_roles):
            return await it.response.send_message("Вам нужно пройти верификацию для доступа к этому разделу.", ephemeral=True)
            
        await cog.handle_create_ticket(it, self.t_type)


# ================= COG =================
class Tickets(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot
        self.db = Database()
        
    async def cog_load(self):
        for t in ["verif", "support"]: self.bot.add_view(CombinedPanelView(t))
        self.bot.add_view(TicketControlView())
        self.bot.add_view(TicketClaimedView())
        self.bot.add_view(TicketClosedStaffView())

    @app_commands.command(name="panel", description="Установить панель тикетов (Админ)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(panel_type=[
        app_commands.Choice(name="Верификация", value="verif"),
        app_commands.Choice(name="Поддержка", value="support")
    ])
    async def panel_slash(self, interaction: discord.Interaction, panel_type: app_commands.Choice[str]):
        titles = {"verif": "Верификация", "support": "Поддержка"}
        embed = discord.Embed(title=titles[panel_type.value], description="Нажмите на кнопку ниже, чтобы открыть тикет.", color=discord.Color.blue())
        await interaction.channel.send(embed=embed, view=CombinedPanelView(panel_type.value))
        await interaction.response.send_message("Панель установлена.", ephemeral=True)

    async def handle_create_ticket(self, it, t_type):
        if not it.response.is_done(): await it.response.defer(ephemeral=True)
        config = (await self.db.get_guild_config(str(it.guild.id))) or {}
        cfg = config.get("tickets", {})
        
        if not cfg.get("category_id"): return await it.followup.send("Ошибка: Категория для тикетов не настроена в /setup.", ephemeral=True)
        if await self.db.get_active_ticket_by_owner(str(it.user.id)):
            return await it.followup.send("У вас уже есть открытый тикет.", ephemeral=True)

        staff_roles = cfg.get("staff_roles", [])
        admin_roles = config.get("admin_roles", [])
        ping_role = config.get("staff_ping_role")

        overwrites = {
            it.guild.default_role: discord.PermissionOverwrite(read_messages=False), 
            it.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
        }
        
        roles_to_allow = staff_roles + admin_roles
        if ping_role: roles_to_allow.append(ping_role)
            
        for r_id in set(roles_to_allow):
            role = it.guild.get_role(r_id)
            if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
                
        ch = await it.guild.create_text_channel(name=f"{t_type}-{it.user.name[:10]}", category=it.guild.get_channel(cfg["category_id"]), overwrites=overwrites)
        await self.db.create_ticket(str(ch.id), str(it.user.id), ch.name)
            
        em = discord.Embed(color=discord.Color.blue())
        if t_type == "verif": 
            em.title, em.description = "Верификация", VERIFICATION_FORM
        else: 
            em.title, em.description = "Поддержка", "Опишите вашу проблему или вопрос, администрация скоро ответит."
            
        ping_text = f"{it.user.mention} <@&{ping_role}>" if ping_role else f"{it.user.mention}"
        msg = await ch.send(content=ping_text, embed=em, view=TicketControlView())
        await msg.pin()
        await it.followup.send(f"Тикет создан: {ch.mention}", ephemeral=True)
        
    async def execute_close_action(self, it, action):
        if not it.response.is_done(): await it.response.defer()
        try: await it.delete_original_response()
        except: pass
        
        row = await self.db.get_active_ticket_by_channel(str(it.channel_id))
        owner = it.guild.get_member(int(row['owner_id'])) if row else None
            
        # ЛОГИКА ВЕРИФИКАЦИИ (как в /verify)
        if action == "verify" and owner:
            config = (await self.db.get_guild_config(str(it.guild.id))) or {}
            v_cfg = config.get("verification", {})
            
            # Выдаем роли из настроек верификации
            for rid in v_cfg.get("verified_roles", []):
                role = it.guild.get_role(rid)
                if role: await owner.add_roles(role)
            
            # Удаляем роль не верифицированного
            uv_id = v_cfg.get("unverified_role_id")
            if uv_id:
                role = it.guild.get_role(uv_id)
                if role: await owner.remove_roles(role)
            
        if owner: 
            try: await it.channel.set_permissions(owner, overwrite=None)
            except: pass
        
        await it.channel.edit(name=f"closed-{it.channel.name.split('-')[-1]}")
        embed = discord.Embed(title="Тикет закрыт", description="Панель управления закрытым тикетом:", color=discord.Color.red())
        await it.channel.send(embed=embed, view=TicketClosedStaffView())
                
    async def delete_ticket(self, it):
        await it.response.send_message("Удаление через 5 секунд...", ephemeral=True)
        await asyncio.sleep(5)
        await self.db.delete_ticket(str(it.channel_id))
        try: await it.channel.delete()
        except: pass

async def setup(bot): 
    await bot.add_cog(Tickets(bot))
