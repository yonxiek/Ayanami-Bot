import aiohttp
import discord
import base64
import json as json_mod
from discord.ext import commands
from discord import app_commands
from db import Database
from ui_components import Colors
import config
import ai_client

IMAGEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI GPT",
    "deepseek": "DeepSeek",
}


class AIImageModal(discord.ui.Modal, title="🎨 Генерация изображения"):
    prompt = discord.ui.TextInput(
        label="Описание изображения",
        style=discord.TextStyle.paragraph,
        placeholder="Например: закат над неоновым городом, дождь...",
        required=True,
        max_length=1500,
    )
    style = discord.ui.TextInput(
        label="Стиль",
        placeholder="фотореализм, аниме, пиксель-арт, акварель...",
        required=False,
        max_length=100,
        default="фотореализм",
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.cog._generate(interaction, self.prompt.value, self.style.value or "фотореализм")


class AIHubView(discord.ui.View):
    def __init__(self, cog, db: Database, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.db = db
        self.guild_id = guild_id

    @discord.ui.button(label="Изображение", emoji="🎨", style=discord.ButtonStyle.blurple, row=0)
    async def btn_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog.api_key:
            return await interaction.response.send_message(
                "❌ Не настроен API-ключ Gemini. Обратитесь к администратору.", ephemeral=True
            )
        await interaction.response.send_modal(AIImageModal(self.cog))

    @discord.ui.button(label="Модерация вкл", emoji="🟢", style=discord.ButtonStyle.success, row=1)
    async def btn_mod_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "ai_moderation_enabled", True)
        await interaction.followup.send("✅ ИИ-модерация включена.", ephemeral=True)

    @discord.ui.button(label="Модерация выкл", emoji="🔴", style=discord.ButtonStyle.danger, row=1)
    async def btn_mod_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await self.db.update_config_field(str(self.guild_id), "ai_moderation_enabled", False)
        await interaction.followup.send("✅ ИИ-модерация выключена.", ephemeral=True)

    @discord.ui.button(label="Журнал модерации", emoji="📋", style=discord.ButtonStyle.grey, row=1)
    async def btn_mod_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        cursor = await self.db.conn.execute(
            "SELECT user_id, action, reason, confidence, created_at FROM ai_moderation_log "
            "WHERE guild_id = ? ORDER BY created_at DESC LIMIT 25",
            (str(self.guild_id),)
        )
        rows = await cursor.fetchall()
        if not rows:
            return await interaction.followup.send("📭 Записей нет.", ephemeral=True)

        action_emojis = {"delete": "🗑️", "warn": "⚠️", "mute": "🔇", "none": "✅"}
        lines = []
        for r in rows:
            emoji = action_emojis.get(r["action"], "❓")
            lines.append(f"{emoji} <@{r['user_id']}> — {r['action']} ({r['confidence']:.0%}) — {r['reason'][:50]}")

        embed = discord.Embed(title="🤖 Журнал AI-модерации", description="\n".join(lines), color=Colors.MAIN)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.select(
        placeholder="🌐 Провайдер ИИ",
        options=[
            discord.SelectOption(label="Google Gemini", value="gemini", description="По умолчанию"),
            discord.SelectOption(label="OpenAI GPT", value="openai"),
            discord.SelectOption(label="DeepSeek", value="deepseek"),
        ],
        row=2,
    )
    async def select_provider(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not await self._require_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        val = select.values[0]
        await self.db.update_config_field(str(self.guild_id), "ai_provider", val)
        available = ai_client._api_key_for(val)
        label = PROVIDER_LABELS.get(val, val)
        status = (
            f"✅ Провайдер: **{label}**"
            if available else
            f"⚠️ Провайдер: **{label}** (ключ не задан в `.env`)"
        )
        await interaction.followup.send(status, ephemeral=True)

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Только администратор может менять настройки ИИ.", ephemeral=True)
            return False
        return True


class AIImageGeneration(commands.Cog):
    """ИИ: генерация изображений, модерация и настройки провайдера."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.api_key = config.GEMINI_API_KEY
        self.model = "gemini-2.0-flash-exp"  # модель с поддержкой изображений

    @app_commands.command(name="ai", description="Меню ИИ: изображения, модерация, провайдер")
    async def ai_hub(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        config_data = await self.db.get_guild_config(guild_id)
        provider = ai_client.normalize_provider(config_data.get("ai_provider"))
        provider_label = PROVIDER_LABELS.get(provider, provider)
        provider_key = ai_client._api_key_for(provider)
        enabled = config_data.get("ai_moderation_enabled", False)

        lines = [
            "### 🎨 Изображения",
            f"**Gemini API-ключ:** {'✅ задан' if self.api_key else '❌ не задан (см. `.env` → GEMINI_API_KEY)'}",
            "",
            "### 🛡️ Модерация сообщений",
            f"**Статус:** {'🟢 Включена' if enabled else '🔴 Выключена'}",
            f"**Провайдер:** {provider_label} ({'ключ ✅' if provider_key else 'ключ ❌'})",
            "",
            "**Настройки чата с ИИ** (канал, промпт, кулдаун) — в `/setup` → «Чат с ИИ».",
        ]
        embed = discord.Embed(title="🤖 Меню ИИ", description="\n".join(lines), color=Colors.MAIN)
        embed.set_footer(text="Настройки менять может только администратор")
        await interaction.followup.send(embed=embed, view=AIHubView(self, self.db, interaction.guild.id), ephemeral=True)

    async def _generate(self, interaction: discord.Interaction, prompt: str, style: str):
        if not self.api_key:
            return await interaction.followup.send(
                "❌ Не настроен API-ключ Gemini. Обратитесь к администратору.", ephemeral=True
            )

        full_prompt = (
            f"Сгенерируй изображение по описанию. Стиль: {style}.\n"
            f"Описание: {prompt}\n\n"
            f"Ответь ТОЛЬКО JSON: {{\"image_base64\": \"<base64 изображения>\", \"text\": \"<описание>\"}}"
        )

        body = {
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
        }
        headers = {"Content-Type": "application/json"}
        url = IMAGEN_URL.format(model=self.model)

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{url}?key={self.api_key}", json=body, headers=headers) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        print(f"Imagen API error {resp.status}: {err[:300]}")
                        return await interaction.followup.send(
                            "❌ Ошибка генерации. Возможно, модель не поддерживает изображения.",
                            ephemeral=True
                        )
                    data = await resp.json()

            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError):
                return await interaction.followup.send("❌ Модель не вернула ответ.", ephemeral=True)

            # Попытка извлечь base64
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                result = json_mod.loads(text[start:end])
                img_b64 = result.get("image_base64", "")
                desc = result.get("text", "")
                if img_b64:
                    img_bytes = base64.b64decode(img_b64)
                    file = discord.File(img_bytes, filename="generated.png")
                    embed = discord.Embed(
                        title=f"🎨 {prompt[:100]}",
                        description=desc[:500] if desc else "",
                        color=Colors.MAIN,
                    )
                    embed.set_image(url="attachment://generated.png")
                    embed.set_footer(text=f"Стиль: {style}")
                    return await interaction.followup.send(embed=embed, file=file)

            # Fallback: текстовое описание
            embed = discord.Embed(
                title=f"🎨 Описание: {prompt[:100]}",
                description=text[:2000],
                color=Colors.MAIN,
            )
            embed.set_footer(text=f"Стиль: {style}")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Imagen error: {e}")
            await interaction.followup.send("❌ Ошибка при генерации изображения.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AIImageGeneration(bot))