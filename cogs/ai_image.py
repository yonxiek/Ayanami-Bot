import aiohttp
import discord
import base64
from discord.ext import commands
from discord import app_commands
from db import Database
from ui_components import Colors
import config
import ai_client

IMAGEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"
IMAGEN_MODELS = ["imagen-3.0-generate-002", "imagen-4.0-generate-001", "imagen-3.0-generate-001"]

PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI GPT",
    "deepseek": "DeepSeek",
}


def _detect_image_ext(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    return ".png"


class PublicImageButton(discord.ui.View):
    def __init__(self, img_bytes: bytes, prompt: str, style: str, model: str):
        super().__init__(timeout=300)
        self.img_bytes = img_bytes
        self.prompt = prompt
        self.style = style
        self.model = model
        self.posted = False

    @discord.ui.button(label="Показать в чате", emoji="📢", style=discord.ButtonStyle.grey)
    async def btn_public(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.posted:
            return
        ext = _detect_image_ext(self.img_bytes)
        file = discord.File(self.img_bytes, filename=f"generated{ext}")
        embed = discord.Embed(
            title=f"🎨 {self.prompt[:100]}",
            description=f"*{self.style}* — автор: {interaction.user.display_name}",
            color=Colors.MAIN,
        )
        embed.set_image(url=f"attachment://generated{ext}")
        embed.set_footer(text=f"Модель: {self.model} • Стиль: {self.style}")
        await interaction.response.send_message(embed=embed, file=file)
        self.posted = True
        button.disabled = True
        button.label = "Отправлено ✅"
        await interaction.message.edit(view=self)


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

        full_prompt = f"Сгенерируй изображение по описанию. Стиль: {style}. Описание: {prompt}"
        body = {
            "instances": [{"prompt": full_prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "1:1",
                "personGeneration": "allow_all",
            },
        }

        last_error = ""
        for model in IMAGEN_MODELS:
            try:
                timeout = aiohttp.ClientTimeout(total=60)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        IMAGEN_URL.format(model=model),
                        params={"key": self.api_key},
                        json=body,
                    ) as resp:
                        if resp.status == 404:
                            continue
                        if resp.status != 200:
                            last_error = f"{resp.status}: {await resp.text()}"
                            print(f"Imagen {model} error {resp.status}: {last_error[:300]}")
                            continue
                        data = await resp.json()

                try:
                    img_b64 = data["predictions"][0]["bytesBase64Encoded"]
                except (KeyError, IndexError):
                    last_error = "пустой ответ от API"
                    continue
                if not img_b64:
                    last_error = "пустое изображение в ответе"
                    continue

                img_bytes = base64.b64decode(img_b64)
                ext = _detect_image_ext(img_bytes)
                file = discord.File(img_bytes, filename=f"generated{ext}")
                embed = discord.Embed(
                    title=f"🎨 {prompt[:100]}",
                    description=f"*{style}*",
                    color=Colors.MAIN,
                )
                embed.set_image(url=f"attachment://generated{ext}")
                embed.set_footer(text=f"Модель: {model} • Стиль: {style}")
                view = PublicImageButton(img_bytes, prompt, style, model)
                return await interaction.followup.send(embed=embed, file=file, view=view)

            except Exception as e:
                last_error = str(e)
                print(f"Imagen error: {e}")

        await interaction.followup.send(
            f"❌ Ошибка генерации: {last_error or 'не удалось получить изображение'}. Попробуйте ещё раз.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(AIImageGeneration(bot))