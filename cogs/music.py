from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from db import Database
from prefix_adapter import InteractionAdapter
from ui_components import Colors

try:
    import wavelink
    WAVELINK_AVAILABLE = True
except ImportError:
    WAVELINK_AVAILABLE = False

URL_RE = re.compile(r"https?://(?:www\.)?.+")


class MusicPlayerView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="⏯️", style=discord.ButtonStyle.secondary, custom_id="music_playpause")
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._toggle(interaction)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._skip(interaction)

    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._stop(interaction)

    @discord.ui.button(label="📃", style=discord.ButtonStyle.secondary, custom_id="music_queue")
    async def queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._queue(interaction)


class Music(commands.Cog):
    """Музыка в голосовых каналах (требуется Lavalink сервер)."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.players: dict[int, wavelink.Player] = {}
        self.views: dict[int, discord.ui.View] = {}

    async def cog_load(self):
        # Автоподключение к Lavalink при запуске бота
        try:
            self.bot.loop.create_task(self._setup_lavalink())
        except (RuntimeError, AttributeError):
            pass

    async def _setup_lavalink(self):
        await self.bot.wait_until_ready()
        if not WAVELINK_AVAILABLE:
            print("🎵 wavelink не установлен — музыка отключена (pip install wavelink)")
            return
        from config import LAVALINK_HOST, LAVALINK_PASSWORD, LAVALINK_PORT
        if not LAVALINK_HOST:
            return

        node = wavelink.Node(
            uri=f"http://{LAVALINK_HOST}:{LAVALINK_PORT}",
            password=LAVALINK_PASSWORD,
        )
        try:
            await wavelink.Pool.connect(client=self.bot, nodes=[node])
            print("🎵 Lavalink подключен!")
        except Exception as e:
            print(f"🎵 Ошибка подключения Lavalink: {e}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player:
            return
        if player.queue.is_empty:
            await player.voice_state.disconnect() if hasattr(player, "voice_state") else await player.disconnect()
            return
        next_track = player.queue.get()
        await player.play(next_track)

    def _get_player_view(self, guild_id: int) -> discord.ui.View:
        if guild_id not in self.views:
            self.views[guild_id] = MusicPlayerView(self)
        return self.views[guild_id]

    async def _ensure_voice(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice:
            await interaction.response.send_message("❌ Вы не в голосовом канале!", ephemeral=True)
            return False
        player = self.players.get(interaction.guild.id)
        if not player:
            try:
                player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
                self.players[interaction.guild.id] = player
            except Exception as e:
                await interaction.response.send_message(f"❌ Не удалось подключиться: {e}", ephemeral=True)
                return False
        if not player.guild.me.voice:
            try:
                player = await player.move_to(interaction.user.voice.channel)
            except Exception:
                await interaction.response.send_message("❌ Не удалось переключить бота в ваш канал.", ephemeral=True)
                return False
        return True

    @app_commands.command(name="play", description="Воспроизвести трек (название или ссылка)")
    @app_commands.describe(query="Название трека или URL")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        if not await self._ensure_voice(interaction):
            return

        player = self.players[interaction.guild.id]

        try:
            if URL_RE.match(query):
                tracks = await wavelink.Playable.search(query)
            else:
                tracks = await wavelink.Playable.search(f"ytsearch:{query}")
        except Exception as e:
            return await interaction.followup.send(f"❌ Ошибка поиска: {e}", ephemeral=True)

        if not tracks:
            return await interaction.followup.send("❌ Треки не найдены.", ephemeral=True)

        track = tracks[0]
        if player.playing or not player.queue.is_empty:
            await player.queue.put_wait(track)
            embed = discord.Embed(
                title=f"🎵 Добавлен в очередь: {track.title}",
                description=f"**Автор:** {getattr(track, 'author', 'Неизвестно')}\n**Позиция:** {len(player.queue)}",
                color=Colors.MAIN,
            )
            return await interaction.followup.send(embed=embed)

        await player.play(track)
        embed = discord.Embed(
            title=f"🎵 Играет: {track.title}",
            description=f"**Автор:** {getattr(track, 'author', 'Неизвестно')}\n"
                        f"**Длительность:** {self._format_duration(getattr(track, 'length', 0) / 1000)}",
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed, view=self._get_player_view(interaction.guild.id))

    @app_commands.command(name="pause", description="Пауза")
    async def pause(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if player and player.playing:
            await player.pause(True)
            await interaction.response.send_message("⏸️ Пауза.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Ничего не играет.", ephemeral=True)

    @app_commands.command(name="resume", description="Продолжить")
    async def resume(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if player and player.paused:
            await player.pause(False)
            await interaction.response.send_message("▶️ Продолжаю.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Музыка не на паузе.", ephemeral=True)

    @app_commands.command(name="skip", description="Пропустить трек")
    async def skip_cmd(self, interaction: discord.Interaction):
        await self._skip(interaction)

    @app_commands.command(name="stop", description="Остановить музыку и очистить очередь")
    async def stop_cmd(self, interaction: discord.Interaction):
        await self._stop(interaction)

    @app_commands.command(name="queue", description="Текущая очередь")
    async def queue_cmd(self, interaction: discord.Interaction):
        await self._queue(interaction)

    # ---- внутренние обработчики кнопок ----

    async def _toggle(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message("❌ Нет плеера.", ephemeral=True)
        if player.playing:
            await player.pause(True)
            text = "⏸️ Пауза"
        else:
            await player.pause(False)
            text = "▶️ Продолжаю"
        await interaction.response.send_message(text, ephemeral=True)

    async def _skip(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player or not player.playing:
            return await interaction.response.send_message("❌ Ничего не играет.", ephemeral=True)
        if player.queue.is_empty:
            await player.stop()
            await interaction.response.send_message("⏹️ Очередь пуста — музыка остановлена.")
        else:
            skipped = getattr(player.current, "title", "трек")
            next_track = player.queue.get()
            await player.play(next_track)
            await interaction.response.send_message(f"⏭️ Пропущен: **{skipped}**\n🎵 Играет: **{getattr(next_track, 'title', '')}**")

    async def _stop(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message("❌ Нет плеера.", ephemeral=True)
        await player.stop()
        player.queue.clear()
        await player.disconnect()
        self.players.pop(interaction.guild.id, None)
        await interaction.response.send_message("⏹️ Музыка остановлена, очередь очищена.")

    async def _queue(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message("❌ Нет плеера.", ephemeral=True)
        lines = []
        current = player.current
        if current:
            lines.append(f"▶️ **Сейчас:** {current.title}")
        for i, track in enumerate(list(player.queue)[:10], 1):
            lines.append(f"**{i}.** {track.title}")
        if not lines:
            lines.append("Очередь пуста.")
        embed = discord.Embed(
            title="📃 Очередь",
            description="\n".join(lines),
            color=Colors.MAIN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    # ==========================================================
    #                ПРЕФИКСНЫЕ КОМАНДЫ
    # ==========================================================

    @commands.command(name="play")
    async def play_prefix(self, ctx, *, query: str):
        await self.play.callback(self, InteractionAdapter(ctx), query)

    @commands.command(name="pause")
    async def pause_prefix(self, ctx):
        await self.pause.callback(self, InteractionAdapter(ctx))

    @commands.command(name="resume")
    async def resume_prefix(self, ctx):
        await self.resume.callback(self, InteractionAdapter(ctx))

    @commands.command(name="skip")
    async def skip_prefix(self, ctx):
        await self.skip_cmd.callback(self, InteractionAdapter(ctx))

    @commands.command(name="stop")
    async def stop_prefix(self, ctx):
        await self.stop_cmd.callback(self, InteractionAdapter(ctx))

    @commands.command(name="queue")
    async def queue_prefix(self, ctx):
        await self.queue_cmd.callback(self, InteractionAdapter(ctx))


async def setup(bot):
    await bot.add_cog(Music(bot))