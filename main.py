import discord
from discord.ext import commands
import re
import datetime
import os
from collections import defaultdict

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Убираем дефолтный help, так как есть свой !помощь
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

MARKDOWN_PATTERN = re.compile(r"(\*\*.*?\*\*|\*.*?\*|##.*|__.*?__|~~.*?~~)")

ROLE_MODERATOR = "Модератор"
ROLE_ADMIN = "Администратор"

# ID канала, куда будут приходить отчеты о нарушениях
LOG_CHANNEL_ID = 1488165415090655333

SPAM_THRESHOLD = 5
SPAM_INTERVAL = 5
CAPS_PERCENT = 70
CAPS_MIN_LENGTH = 8

channel_spam_tracker = defaultdict(list)
CHANNEL_SPAM_THRESHOLD = 10
CHANNEL_SPAM_INTERVAL = 5

warnings = defaultdict(int)
spam_tracker = defaultdict(list)

def is_mod(member: discord.Member) -> bool:
    role_names = [r.name for r in member.roles]
    return ROLE_MODERATOR in role_names or ROLE_ADMIN in role_names or member.guild_permissions.administrator

async def send_dm(member: discord.Member, embed: discord.Embed):
    """Безопасная отправка сообщения в ЛС нарушителю"""
    try:
        await member.send(embed=embed)
    except discord.Forbidden:
        pass 

async def log_violation(bot: commands.Bot, member: discord.Member, rule: str, details: str, channel: discord.TextChannel):
    """Отправка отчета о нарушении в админ-канал"""
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title=f"🚨 Зафиксировано нарушение: {rule}", color=discord.Color.brand_red())
        embed.add_field(name="👤 Нарушитель", value=f"{member.mention} ({member.id})", inline=True)
        embed.add_field(name="📍 Канал", value=channel.mention, inline=True)
        embed.add_field(name="📝 Оригинальное сообщение", value=f"
