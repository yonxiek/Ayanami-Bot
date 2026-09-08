import discord
from datetime import datetime

class Icons:
    KICK = "https://cdn.discordapp.com/emojis/1540036508793311332.webp?size=96"
    BAN = "https://cdn.discordapp.com/emojis/1540036480414519416.webp?size=96"
    MUTE = "https://cdn.discordapp.com/emojis/1540036445421699167.webp?size=96"
    UNMUTE = "https://cdn.discordapp.com/emojis/1540395015900241960.webp?size=96"
    WARN = "https://cdn.discordapp.com/emojis/1540036546214887595.webp?size=96"
    LOCK = "https://cdn.discordapp.com/emojis/1540037336761368676.webp?size=96"
    UNLOCK = "https://cdn.discordapp.com/emojis/1540036416313229312.webp?size=96"
    UNBAN = "https://cdn.discordapp.com/emojis/1540369646975328316.webp?size=96"
    BLACKLIST = "https://cdn.discordapp.com/emojis/1541156233996800040.webp?size=96"
    INFO = "https://cdn.discordapp.com/emojis/1540036382091649136.webp?size=96"
    MOD = "https://cdn.discordapp.com/emojis/1540036382091649136.webp?size=96"
    CLAN_LOGO = "https://cdn.discordapp.com/emojis/1540036382091649136.webp?size=96"

class Colors:
    MAIN = 0x2b2d31
    ERROR = 0xed4245
    SUCCESS = 0x2ecc71
    WARNING = 0xf39c12
    LEVEL_UP = 0xf1c40f

class AyanamiUI:
    E_RP = "⚡"
    INFO = 0x2b2d31

    @staticmethod
    def get_plural(number: int, one: str, two: str, five: str) -> str:
        n = abs(number) % 100
        n1 = n % 10
        if 10 < n < 20: return five
        if 1 < n1 < 5: return two
        if n1 == 1: return one
        return five

    @staticmethod
    def format_duration_ru(duration_str: str) -> str:
        if not duration_str: return None
        import re
        match = re.match(r"(\d+)([smhd])", duration_str.lower())
        if not match: return duration_str
        amount, unit = int(match.group(1)), match.group(2)
        units_map = {
            's': ('Секунда', 'Секунды', 'Секунд'),
            'm': ('Минута', 'Минуты', 'Минут'),
            'h': ('Час', 'Часа', 'Часов'),
            'd': ('День', 'Дня', 'Дней')
        }
        words = units_map.get(unit)
        if not words: return duration_str
        return f"{amount} {AyanamiUI.get_plural(amount, *words)}"