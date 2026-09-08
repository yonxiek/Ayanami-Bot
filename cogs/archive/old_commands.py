"""
АРХИВ: Старые версии команд с Training/Tryout.
Если нужно вернуть — скопируйте нужные команды обратно в utils.py.
"""
import discord
from discord import app_commands


# ==========================================
#   СТАРАЯ /host (с Training/Tryout)
# ==========================================
OLD_HOST_CHOICES = [
    app_commands.Choice(name="Training (Тренировка)", value="Training"),
    app_commands.Choice(name="Tryout (Набор)", value="Tryout"),
    app_commands.Choice(name="Game Night (Игры)", value="Game Night")
]

OLD_HOST_ROLE_MAP = {
    "Training": "training-ping",
    "Tryout": "tryout-ping",
    "Game Night": "gamenight-ping"
}


# ==========================================
#   СТАРАЯ /applications (с Training/Tryout)
# ==========================================
OLD_APPLICATION_CHOICES = [
    app_commands.Choice(name="Helper", value="Helper"),
    app_commands.Choice(name="Training Hoster", value="Training"),
    app_commands.Choice(name="Tryout Hoster", value="Tryout")
]


# ==========================================
#   СТАРАЯ /roblox_verify (простая верификация)
# ==========================================
# Была в utils.py до добавления /verify
# Просто меняла ник без выдачи роли


# ==========================================
#   СТАРАЯ /verifyall (без настроек verify)
# ==========================================
# Была в utils.py до добавления конфига verify
# Меняла ник без опции выдачи роли
