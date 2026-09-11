import discord
from discord.ext import commands

from db import Database


class Greetings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    def _format_message(self, text: str, member: discord.Member) -> str:
        if not text:
            return ""
        guild = member.guild
        text = text.replace("{user}", member.mention)
        text = text.replace("{username}", member.name)
        text = text.replace("{user_id}", str(member.id))
        text = text.replace("{nickname}", member.nick or member.name)
        text = text.replace("{server}", guild.name)
        text = text.replace("{server_id}", str(guild.id))
        text = text.replace("{server_count}", str(guild.member_count))
        text = text.replace("{boost_count}", str(guild.premium_subscription_count or 0))
        text = text.replace("{role_count}", str(len(member.roles) - 1))
        text = text.replace("{top_role}", member.top_role.mention if len(member.roles) > 1 else "Нет")
        text = text.replace("{created_at}", f"<t:{int(member.created_at.timestamp())}:R>")
        if member.joined_at:
            text = text.replace("{joined_at}", f"<t:{int(member.joined_at.timestamp())}:R>")
        else:
            text = text.replace("{joined_at}", "Неизвестно")
        if member.premium_since:
            text = text.replace("{boost}", f"Буст с <t:{int(member.premium_since.timestamp())}:R>")
            text = text.replace("{boost_since}", f"<t:{int(member.premium_since.timestamp())}:R>")
        else:
            text = text.replace("{boost}", "")
            text = text.replace("{boost_since}", "Не бустит")
        return text

    async def _get_config(self, guild_id: int):
        return await self.db.get_guild_config(str(guild_id))

    async def _send_channel(self, guild_id: int, channel_id_key: str, view: discord.ui.LayoutView):
        config = await self._get_config(guild_id)
        ch_id = config.get(channel_id_key)
        if not ch_id:
            return
        channel = self.bot.get_channel(int(ch_id))
        if not channel:
            return
        try:
            await channel.send(view=view)
        except Exception:
            pass

    # ==========================================
    #               ПРИВЕТСТВИЕ
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member):
        config = await self._get_config(member.guild.id)

        if config.get("autorole_enabled", False):
            role_ids = config.get("autorole_roles", [])
            for role_id in role_ids:
                role = member.guild.get_role(int(role_id))
                if role:
                    try:
                        await member.add_roles(role, reason="Auto-role")
                    except Exception:
                        pass

        if not config.get("welcome_enabled", False):
            return
        channel_id = config.get("welcome_channel_id")
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        msg_template = config.get("welcome_message", "")
        msg_text = self._format_message(msg_template, member) if msg_template else None

        fields = [
            ("Участник", f"{member.mention} (`{member.id}`)"),
            ("Аккаунт создан", f"<t:{int(member.created_at.timestamp())}:R>"),
            ("Участников", str(member.guild.member_count)),
            ("Ролей", str(len(member.roles) - 1)),
        ]
        if member.premium_since:
            fields.append(("💎 Буст", f"Активен с <t:{int(member.premium_since.timestamp())}:R>"))

        embed = discord.Embed(
            title=f"Добро пожаловать на {member.guild.name}!",
            description=msg_text if msg_text else f"{member.mention} присоединился к серверу! Рады видеть тебя!",
            color=discord.Color.green(),
        )
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_image(url=config.get("welcome_banner", "") or None)
        embed.set_footer(text=member.guild.name)

        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    # ==========================================
    #               ПРОЩАНИЕ
    # ==========================================

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        config = await self._get_config(member.guild.id)
        if not config.get("leave_enabled", False):
            return
        channel_id = config.get("leave_channel_id")
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        msg_template = config.get("leave_message", "")
        msg_text = self._format_message(msg_template, member) if msg_template else None

        fields = [("Участник", f"`{member.name}` (`{member.id}`)")]
        if member.joined_at:
            fields.append(("Был на сервере", f"<t:{int(member.joined_at.timestamp())}:R>"))
        roles = [r.mention for r in member.roles if not r.is_default()]
        if roles:
            fields.append(("Роли", ", ".join(roles[:10])))

        embed = discord.Embed(
            title=f"Участник покинул {member.guild.name}",
            description=msg_text if msg_text else f"{member.name} покинул сервер.",
            color=discord.Color.red(),
        )
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_image(url=config.get("leave_banner", "") or None)
        embed.set_footer(text=member.guild.name)

        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    # ==========================================
    #               БУСТ
    # ==========================================

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        was_boosting = before.premium_since is not None
        is_boosting = after.premium_since is not None
        if was_boosting == is_boosting:
            return

        config = await self._get_config(after.guild.id)
        if not config.get("boost_enabled", False):
            return
        channel_id = config.get("boost_channel_id")
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        if is_boosting:
            msg_template = config.get("boost_message", "")
            msg_text = self._format_message(msg_template, after) if msg_template else None
            fields = [
                ("Участник", f"{after.mention} (`{after.id}`)"),
                ("Всего бустов", str(after.guild.premium_subscription_count or 0)),
                ("Буст с", f"<t:{int(after.premium_since.timestamp())}:R>"),
            ]
            embed = discord.Embed(
                title="💎 Новый буст!",
                description=msg_text if msg_text else f"{after.mention} забустил **{after.guild.name}**!",
                color=discord.Color.gold(),
            )
            for name, value in fields:
                embed.add_field(name=name, value=value, inline=False)
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.set_image(url=config.get("boost_banner", "") or None)
            embed.set_footer(text=after.guild.name)
        else:
            fields = [
                ("Участник", f"{after.mention} (`{after.id}`)"),
                ("Всего бустов", str(after.guild.premium_subscription_count or 0)),
            ]
            embed = discord.Embed(
                title="💎 Буст снят",
                description=f"{after.mention} снял буст с **{after.guild.name}**.",
                color=discord.Color.greyple(),
            )
            for name, value in fields:
                embed.add_field(name=name, value=value, inline=False)
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.set_image(url=config.get("boost_banner", "") or None)
            embed.set_footer(text=after.guild.name)

        try:
            await channel.send(embed=embed)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Greetings(bot))
