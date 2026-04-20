import discord
from discord.ext import commands
import re
import datetime
import os
import asyncio
from collections import defaultdict

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

# Убираем дефолтный help
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

MARKDOWN_PATTERN = re.compile(r"(\*\*.*?\*\*|\*.*?\*|##.*|__.*?__|~~.*?~~)")

# --- НАСТРОЙКИ ---
ROLE_MODERATOR = "Модератор"
ROLE_ADMIN = "Администратор"
LOG_CHANNEL_ID = 1491087160433184862
YOUR_USER_ID = 123456789012345678  # <--- ВСТАВЬ СВОЙ ID ЦИФРАМИ
MIN_ACCOUNT_AGE_DAYS = 7 

SPAM_THRESHOLD = 5
SPAM_INTERVAL = 5
CAPS_PERCENT = 70
CAPS_MIN_LENGTH = 8
CHANNEL_SPAM_THRESHOLD = 10
CHANNEL_SPAM_INTERVAL = 5

# Хранилища
warnings = defaultdict(int)
spam_tracker = defaultdict(list)
channel_spam_tracker = defaultdict(list)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def is_mod(member: discord.Member) -> bool:
    role_names = [r.name for r in member.roles]
    return ROLE_MODERATOR in role_names or ROLE_ADMIN in role_names or member.guild_permissions.administrator

async def send_dm(member: discord.Member, embed: discord.Embed):
    try: await member.send(embed=embed)
    except: pass 

async def log_violation(bot, member, rule, details, channel=None):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title=f"🚨 Нарушение: {rule}", color=discord.Color.red())
        embed.add_field(name="👤 Нарушитель", value=f"{member.mention} ({member.id})", inline=True)
        if channel:
            embed.add_field(name="📍 Канал", value=channel.mention, inline=True)
        msg_text = details[:1000] if details else "Пустое сообщение"
        embed.add_field(name="📝 Детали", value=f"```\n{msg_text}\n```", inline=False)
        embed.timestamp = discord.utils.utcnow()
        await log_channel.send(embed=embed)

async def mute_member(member: discord.Member, minutes: int, reason: str):
    try:
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        dm_embed = discord.Embed(title="🔇 Вам выдан мут", color=discord.Color.red())
        dm_embed.add_field(name="Сервер", value=member.guild.name, inline=False)
        dm_embed.add_field(name="⏱ Время", value=f"{minutes} мин.", inline=True)
        dm_embed.add_field(name="📝 Причина", value=reason, inline=True)
        await send_dm(member, dm_embed)
    except: pass

def parse_time(time_str: str) -> int:
    total = 0
    for value, unit in re.findall(r"(\d+)([hm])", time_str.lower()):
        total += int(value) * (60 if unit == "h" else 1)
    return total or None

def is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < CAPS_MIN_LENGTH: return False
    return (sum(c.isupper() for c in letters) / len(letters)) * 100 >= CAPS_PERCENT

async def add_warning(member: discord.Member, channel: discord.TextChannel, reason: str):
    warnings[member.id] += 1
    count = warnings[member.id]
    embed = discord.Embed(color=discord.Color.yellow())
    embed.add_field(name="⚠️ Предупреждение", value=member.mention, inline=True)
    embed.add_field(name="📝 Причина", value=reason, inline=True)
    embed.add_field(name="🔢 Варнов", value=f"{count}/3", inline=True)
    if count >= 3:
        await member.ban(reason="3 предупреждения")
        embed.add_field(name="🔨 Действие", value="Бан", inline=False)
        embed.color = discord.Color.dark_red()
        warnings[member.id] = 0
    await channel.send(embed=embed, delete_after=15)

# --- СОБЫТИЯ ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    # 1. ЗАЩИТА ОТ ЧУЖИХ БОТОВ (АНТИ-КРАШ)
    if member.bot:
        await asyncio.sleep(2)
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=1):
            if entry.target.id == member.id and entry.user.id != YOUR_USER_ID:
                await log_violation(bot, member, "АНТИ-КРАШ", f"Добавил: {entry.user.name}", member.guild.system_channel)
                try:
                    await entry.user.ban(reason="Добавление бота без разрешения")
                    await member.ban(reason="Сторонний бот")
                except: pass
        return

    # 2. АВТО-БАН НОВЫХ АККАУНТОВ
    age = discord.utils.utcnow() - member.created_at
    if age.days < MIN_ACCOUNT_AGE_DAYS:
        await log_violation(bot, member, "АВТО-БАН", f"Возраст аккаунта: {age.days} дн.", member.guild.system_channel)
        try: await member.ban(reason=f"Аккаунту меньше {MIN_ACCOUNT_AGE_DAYS} дней")
        except: pass

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild: return
    if is_mod(message.author):
        await bot.process_commands(message)
        return

    content = message.content
    user_id = message.author.id
    now = datetime.datetime.utcnow().timestamp()

    # Everyone/Here
    if "@everyone" in content or "@here" in content:
        await log_violation(bot, message.author, "Everyone/Here", content, message.channel)
        await message.delete()
        await mute_member(message.author, 30, "Упоминание everyone/here")
        await add_warning(message.author, message.channel, "Everyone/Here")
        return

    # Инвайты
    cleaned = re.sub(r'\s+', '', content.lower())
    if any(x in cleaned for x in ["discord.gg/", "discord.com/invite/", "discordapp.com/invite/"]):
        await log_violation(bot, message.author, "Инвайт", content, message.channel)
        await message.delete()
        await mute_member(message.author, 60, "Реклама инвайтом")
        await add_warning(message.author, message.channel, "Реклама")
        return

    # Спам пользователя
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if now - t < SPAM_INTERVAL]
    spam_tracker[user_id].append(now)
    if len(spam_tracker[user_id]) >= SPAM_THRESHOLD:
        await log_violation(bot, message.author, "Спам", "Массовая отправка", message.channel)
        await message.channel.purge(limit=7, check=lambda m: m.author == message.author)
        await mute_member(message.author, 10, "Спам")
        await add_warning(message.author, message.channel, "Спам")
        return

    # Капс
    if is_caps(content):
        await message.delete()
        return

    # Маркдаун
    if MARKDOWN_PATTERN.search(content):
        await message.delete()
        return

    # Общий спам в канале
    channel_spam_tracker[message.channel.id] = [t for t in channel_spam_tracker[message.channel.id] if now - t < CHANNEL_SPAM_INTERVAL]
    channel_spam_tracker[message.channel.id].append(now)
    if len(channel_spam_tracker[message.channel.id]) >= CHANNEL_SPAM_THRESHOLD:
        await message.delete()
        return

    await bot.process_commands(message)

# --- КОМАНДЫ ---

@bot.command(name="мут")
async def mute(ctx, member: discord.Member, time: str = "10m", *, reason="Без причины"):
    if not is_mod(ctx.author): return
    mins = parse_time(time)
    if not mins: return await ctx.send("❌ Ошибка времени")
    await mute_member(member, mins, reason)
    await ctx.send(f"✅ {member.mention} замучен на {time}")

@bot.command(name="размут")
async def unmute(ctx, member: discord.Member):
    if not is_mod(ctx.author): return
    await member.timeout(None)
    await ctx.send(f"✅ Мут снят с {member.mention}")

@bot.command(name="clear")
async def clear(ctx, amount: int = 10):
    if not is_mod(ctx.author): return
    await ctx.channel.purge(limit=amount + 1)

@bot.command(name="помощь")
async def help_cmd(ctx):
    embed = discord.Embed(title="Помощь по командам", color=discord.Color.blue())
    embed.add_field(name="Модерация", value="`!мут @user время причина`, `!размут @user`, `!clear число`", inline=False)
    embed.add_field(name="Защита", value="Авто-бан аккаунтов < 7 дней, Анти-краш ботов, Анти-спам.", inline=False)
    await ctx.send(embed=embed)

bot.run(os.getenv("TOKEN"))
