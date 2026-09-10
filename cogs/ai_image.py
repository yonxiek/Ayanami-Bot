import aiohttp
import discord
import base64
from discord.ext import commands
from discord import app_commands
from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors
import config

IMAGEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class AIImageGeneration(commands.Cog):
    """Генерация изображений через Gemini Imagen."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.api_key = config.GEMINI_API_KEY
        self.model = "gemini-2.0-flash-exp"  # модель с поддержкой изображений

    @app_commands.command(name="ai_imagine", description="Сгенерировать изображение по описанию")
    @app_commands.describe(prompt="Описание изображения", style="Стиль (фотореализм, аниме, пиксель-арт и т.д.)")
    async def ai_imagine(self, interaction: discord.Interaction, prompt: str, style: str = "фотореализм"):
        if not self.api_key:
            return await interaction.response.send_message(
                "❌ Не настроен API-ключ Gemini. Обратитесь к администратору.", ephemeral=True
            )

        await interaction.response.defer()

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
            import json as json_mod
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

    # ==========================================================
    #                ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================================

    @commands.command(name="ai_imagine")
    async def ai_imagine_prefix(self, ctx, prompt: str, style: str = "фотореализм"):
        await self.ai_imagine.callback(self, InteractionAdapter(ctx), prompt, style)


async def setup(bot):
    await bot.add_cog(AIImageGeneration(bot))
