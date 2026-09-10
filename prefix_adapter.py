"""Адаптер для вызова slash-команд из префиксных (текстовых) команд.

Префиксные команды не имеют объекта `Interaction`, но логика большинства
slash-команд использует его (`.response.send_message`, `.followup.send`,
`.guild`, `.user`, `.channel` и т.д.). Этот адаптер имитирует минимальный
интерфейс `Interaction` поверх `commands.Context`, чтобы можно было
переиспользовать ОДНУ и ту же реализацию и для `/`, и для текстовых команд
без дублирования кода.
"""

from discord.ext import commands


class _ResponseShim:
    """Эмуляция `interaction.response`."""

    def __init__(self, ctx: commands.Context):
        self.ctx = ctx
        self.responded = False
        self._last_message = None

    async def defer(self, ephemeral: bool = False, **kwargs):
        # У текстовых команд нет стадии ожидания ответа — ничего не делаем.
        return None

    async def send_message(self, *args, **kwargs):
        self.responded = True
        kwargs.pop("ephemeral", None)
        kwargs.pop("mention_author", None)
        msg = await self.ctx.send(*args, **kwargs)
        self._last_message = msg
        return msg


class _FollowupShim:
    """Эмуляция `interaction.followup`."""

    def __init__(self, ctx: commands.Context):
        self.ctx = ctx

    async def send(self, *args, **kwargs):
        kwargs.pop("ephemeral", None)
        kwargs.pop("mention_author", None)
        return await self.ctx.send(*args, **kwargs)


def _resolve_guild_permissions(author):
    return getattr(author, "guild_permissions", None)


class _Choice:
    """Имитация `app_commands.Choice`, используется там, где код читает `.value`/`.name`."""

    def __init__(self, value, name=None):
        self.value = value
        self.name = name if name is not None else value


def make_choice(value, name=None):
    """Создать объект с атрибутами `.value`/`.name` для slash-функций, ждущих Choice."""
    return _Choice(value, name)


class InteractionAdapter:
    """Имитирует `Interaction` для вызова slash-метода из текстовой команды."""

    def __init__(self, ctx: commands.Context):
        self.ctx = ctx
        self._author = (ctx.interaction and ctx.interaction.user) or ctx.author
        self.response = _ResponseShim(ctx)
        self.followup = _FollowupShim(ctx)

    @property
    def guild(self):
        return self.ctx.guild

    @property
    def user(self):
        return self._author

    @property
    def channel(self):
        return getattr(self.ctx, "channel", None)

    @property
    def guild_permissions(self):
        return _resolve_guild_permissions(self._author)

    @property
    def guild_id(self):
        return self.ctx.guild.id if self.ctx.guild else None

    async def edit_original_response(self, *args, **kwargs):
        """Имитация `interaction.edit_original_response` — правит сообщение,
        отправленное через `response.send_message`."""
        msg = self.response._last_message
        if msg is not None:
            await msg.edit(*args, **kwargs)

    async def original_response(self):
        """Имитация `interaction.original_response()` — последнее отправленное сообщение."""
        return self.response._last_message

    def __getattr__(self, item):
        # Любые прочие атрибуты берём из контекста (например, `bot`,
        # кастомные поля, если потребуются).
        return getattr(self.ctx, item)
