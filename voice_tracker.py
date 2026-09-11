"""Общий трекер voice-сессий для когов.

Дедупликация логики отслеживания нахождения в голосовых каналах:
economy, stats, logging, quests используют одинаковую схему
(join → запись времени, leave → расчёт минут), отличаясь только
действиями после расчёта.
"""

from datetime import datetime, timezone


class VoiceTrackerMixin:
    """Миксин для отслеживания voice-сессий.

    Добавляет атрибут self.voice_sessions в формате
    {guild_id: {user_id: datetime}} и методы:
    - restore_voice_sessions(bot) — восстановление активных сессий при старте;
    - track_voice_join(guild_id, user_id) — запись времени входа;
    - track_voice_leave(guild_id, user_id) -> (minutes, start_time) — завершение сессии;
    - get_ongoing_minutes(guild_id, user_id) -> int — минуты текущей сессии без её завершения.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.voice_sessions: dict[str, dict[str, datetime]] = {}

    def restore_voice_sessions(self, bot) -> None:
        """Восстанавливает активные сессии участников, уже находящихся в голосовых каналах."""
        for guild in bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        self.track_voice_join(guild.id, member.id)

    def track_voice_join(self, guild_id: int | str, user_id: int | str) -> None:
        """Записывает время входа участника в голосовой канал."""
        self.voice_sessions.setdefault(str(guild_id), {})[str(user_id)] = datetime.now(timezone.utc)

    def track_voice_leave(self, guild_id: int | str, user_id: int | str) -> tuple[int, datetime | None]:
        """Завершает сессию и возвращает (полные минуты, время начала сессии).

        Если активной сессии не было — возвращает (0, None).
        """
        start = self.voice_sessions.get(str(guild_id), {}).pop(str(user_id), None)
        if start is None:
            return 0, None
        minutes = int((datetime.now(timezone.utc) - start).total_seconds() / 60)
        return minutes, start

    def get_ongoing_minutes(self, guild_id: int | str, user_id: int | str) -> int:
        """Возвращает минуты текущей активной сессии без её завершения."""
        start = self.voice_sessions.get(str(guild_id), {}).get(str(user_id))
        if start is None:
            return 0
        return int((datetime.now(timezone.utc) - start).total_seconds() / 60)