import discord
from discord.ext import commands
import re
import datetime
import os
from collections import defaultdict

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_INVITE_PATTERN = re.compile(
    r"(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)\S+"
)

MARKDOWN_PATTERN = re.compile(r"(\*\*.*?\*\*|\*.*?\*|##.*|__.*?__|~~.*?~~)")

ROLE_MODERATOR = "Модератор"
ROLE_ADMIN = "Администратор"

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
    return ROLE_MODERATOR in role_names or ROLE_ADMIN in role_names

async def mute_member(member: discord.Member, minutes: int, reason: str):
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)

def parse_time(time_str: str) -> int:
    total = 0
    for value, unit in re.findall(r"(\d+)([hm])", time_str.lower()):
        total += int(value) * (60 if unit == "h" else 1)
    return total or None

def is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < CAPS_MIN_LENGTH:
        return False
    return (sum(c.isupper() for c in letters) / len(letters)) * 100 >= CAPS_PERCENT

def is_spamming(user_id: int) -> bool:
    now = datetime.datetime.utcnow().timestamp()
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if now - t < SPAM_INTERVAL]
    spam_tracker[user_id].append(now)
    return len(spam_tracker[user_id]) >= SPAM_THRESHOLD

def is_channel_spamming(channel_id: int) -> bool:
    now = datetime.datetime.utcnow().timestamp()
    channel_spam_tracker[channel_id] = [t for t in channel_spam_tracker[channel_id] if now - t < CHANNEL_SPAM_INTERVAL]
    channel_spam_tracker[channel_id].append(now)
    return len(channel_spam_tracker[channel_id]) >= CHANNEL_SPAM_THRESHOLD

async def add_warning(member: discord.Member, channel: discord.TextChannel, reason: str):
    warnings[member.id] += 1
    count = warnings[member.id]
    embed = discord.Embed(color=discord.Color.yellow())
    embed.add_field(name="⚠️ Предупреждение", value=f"{member.mention}", inline=True)
    embed.add_field(name="📝 Причина", value=reason, inline=True)
    embed.add_field(name="🔢 Варнов", value=f"{count}/3", inline=True)
    if count >= 3:
        await member.ban(reason="3 предупреждения")
        embed.add_field(name="🔨 Действие", value="Бан с сервера", inline=False)
        embed.color = discord.Color.dark_red()
        warnings[member.id] = 0
    await channel.send(embed=embed, delete_after=15)

def mod_check():
    async def predicate(ctx):
        if is_mod(ctx.author):
            return True
        await ctx.send("❌ Нет прав", delete_after=5)
        return False
    return commands.check(predicate)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if is_mod(message.author):
        await bot.process_commands(message)
        return

    content = message.content

    if "@everyone" in content or "@here" in content:
        await message.delete()
        await mute_member(message.author, 30, "Использование @everyone/@here")
        await add_warning(message.author, message.channel, "Использование @everyone/@here")
        return

    if DISCORD_INVITE_PATTERN.search(content):
        await message.delete()
        await mute_member(message.author, 60, "Реклама Discord-серверов")
        await add_warning(message.author, message.channel, "Реклама серверов")
        return

    if is_spamming(message.author.id):
        await message.channel.purge(limit=10, check=lambda m: m.author == message.author)
        await mute_member(message.author, 15, "Спам")
        await add_warning(message.author, message.channel, "Спам")
        spam_tracker[message.author.id].clear()
        return

    if is_caps(content):
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} не пиши капсом!", delete_after=5)
        return

    if MARKDOWN_PATTERN.search(content):
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} не используй форматирование!", delete_after=5)
        return

    if is_channel_spamming(message.channel.id):
        await message.delete()
        return

    await bot.process_commands(message)

@bot.command(name="мут", aliases=["mute"])
@mod_check()
async def mute(ctx, member: discord.Member, time: str = "10m", *, reason: str = "Без причины"):
    minutes = parse_time(time)
    if not minutes:
        await ctx.send("❌ Формат: `!мут @user 30m причина`", delete_after=5)
        return
    await mute_member(member, minutes, reason)
    hours, mins = divmod(minutes, 60)
    time_str = f"{hours}ч {mins}м" if hours else f"{mins}м"
    embed = discord.Embed(color=discord.Color.red())
    embed.add_field(name="🔇 Мут", value=member.mention, inline=True)
    embed.add_field(name="⏱", value=time_str, inline=True)
    embed.add_field(name="📝 Причина", value=reason, inline=False)
    embed.set_footer(text=f"Модератор: {ctx.author}")
    await ctx.send(embed=embed)

@bot.command(name="размут", aliases=["unmute"])
@mod_check()
async def unmute(ctx, member: discord.Member, *, reason: str = "Без причины"):
    if not member.is_timed_out():
        await ctx.send(f"❌ {member.mention} не в муте", delete_after=5)
        return
    await member.timeout(None, reason=reason)
    embed = discord.Embed(color=discord.Color.green())
    embed.add_field(name="🔊 Мут снят", value=member.mention, inline=True)
    embed.add_field(name="📝 Причина", value=reason, inline=False)
    embed.set_footer(text=f"Модератор: {ctx.author}")
    await ctx.send(embed=embed)

@bot.command(name="варн", aliases=["warn"])
@mod_check()
async def warn(ctx, member: discord.Member, *, reason: str = "Без причины"):
    await add_warning(member, ctx.channel, reason)

@bot.command(name="варны", aliases=["warnings"])
@mod_check()
async def check_warns(ctx, member: discord.Member):
    count = warnings[member.id]
    embed = discord.Embed(color=discord.Color.yellow())
    embed.add_field(name="⚠️ Варны", value=f"{member.mention}: **{count}/3**", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="снятьварн", aliases=["unwarn"])
@mod_check()
async def unwarn(ctx, member: discord.Member):
    if warnings[member.id] == 0:
        await ctx.send(f"❌ У {member.mention} нет варнов", delete_after=5)
        return
    warnings[member.id] -= 1
    await ctx.send(f"✅ Варн снят. Теперь варнов: **{warnings[member.id]}/3**", delete_after=7)

@bot.command(name="clear", aliases=["очистить"])
@mod_check()
async def clear(ctx, amount: int = 10):
    if amount < 1 or amount > 100:
        await ctx.send("❌ Укажи число от 1 до 100", delete_after=5)
        return
    await ctx.message.delete()
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"🗑️ Удалено **{len(deleted)}** сообщений", delete_after=5)

@bot.command(name="мутлист", aliases=["mutelist"])
@mod_check()
async def mutelist(ctx):
    muted = [m for m in ctx.guild.members if m.is_timed_out()]
    if not muted:
        await ctx.send("✅ Нет замученных", delete_after=5)
        return
    embed = discord.Embed(title="🔇 Замученные", color=discord.Color.orange())
    for m in muted:
        embed.add_field(name=str(m), value=discord.utils.format_dt(m.timed_out_until, "R"), inline=False)
    await ctx.send(embed=embed)

@bot.command(name="помощь", aliases=["команды"])
async def help_cmd(ctx):
    embed = discord.Embed(title="📖 Команды бота", color=discord.Color.blurple())
    embed.add_field(name="🔇 `!мут @user <время> [причина]`", value="Мут. Время: `30m` `1h` `2h30m`", inline=False)
    embed.add_field(name="🔊 `!размут @user`", value="Снять мут", inline=False)
    embed.add_field(name="⚠️ `!варн @user [причина]`", value="Выдать варн\n3 варна = бан", inline=False)
    embed.add_field(name="📋 `!варны @user`", value="Посмотреть варны", inline=False)
    embed.add_field(name="✅ `!снятьварн @user`", value="Убрать 1 варн", inline=False)
    embed.add_field(name="🗑️ `!clear [1-100]`", value="Очистить чат", inline=False)
    embed.add_field(name="📋 `!мутлист`", value="Список замученных", inline=False)
    embed.add_field(
        name="🤖 Авто-модерация",
        value=(
            "• `@everyone/@here` → варн + мут 30 мин\n"
            "• Discord инвайты → варн + мут 1 час\n"
            "• Спам → варн + мут 15 мин + очистка\n"
            "• Капс → удаление\n"
            "• Форматирование → удаление\n"
            "• Бомбинг канала → удаление\n"
            "• 3 варна → бан"
        ),
        inline=False
    )
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Пользователь не найден", delete_after=5)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Укажи пользователя", delete_after=5)
        # --- НАСТРОЙКИ ---
OWNER_ID = 1234753278927962142
DATA_FILE = 'data.json'

# --- ЛОГИРОВАНИЕ ---
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='logs.txt', encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# --- РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ---
# Защита от ссылок-инвайтов, включая транслит и пробелы (d i s c o r d . g g)
INVITE_REGEX = re.compile(r'(?:d\s*i\s*s\s*c\s*o\s*r\s*d\s*(?:\.\s*g\s*g|a\s*p\s*p\s*\.\s*c\s*o\s*m\s*/\s*i\s*n\s*v\s*i\s*t\s*e)|d\s*i\s*s\s*c\s*o\s*r\s*d\s*.\s*m\s*e)', re.IGNORECASE)
# Защита от Zalgo (комбинируемые символы Unicode)
ZALGO_REGEX = re.compile(r'[\u0300-\u036F\u0483-\u0489\u1DC0-\u1DFF\u20D0-\u20FF\u2DE0-\u2DFF\uA640-\uA69F\uFE20-\uFE2F]')

# --- ИНИЦИАЛИЗАЦИЯ ДАННЫХ ---
default_data = {
    "trusted": [OWNER_ID],
    "banwords": [],
    "backups": {},
    "stats": {
        "preventive_bans": 0,
        "total_bans": 0,
        "deleted_channels": 0,
        "deleted_messages": 0,
        "total_raids": 0
    },
    "raid_mode": False
}

def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(default_data)
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return default_data

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

db = load_data()

# --- КЛАСС БОТА ---
class RoflAntiRaid(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="?", intents=intents, help_command=None)
        self.start_time = time.time()
        self.owner_id = OWNER_ID

    async def setup_hook(self):
        await self.tree.sync()
        print("Слеш-команды синхронизированы.")

bot = RoflAntiRaid()

# --- ПРОВЕРКИ ---
def is_owner_or_trusted():
    async def predicate(ctx):
        if ctx.author.id == OWNER_ID or ctx.author.id in db["trusted"]:
            return True
        await ctx.send("У вас нет прав для использования этой команды.", ephemeral=True)
        return False
    return commands.check(predicate)

# --- ИВЕНТЫ (АВТОМОДЕРАЦИЯ И АНТИРЕЙД) ---
@bot.event
async def on_ready():
    print(f'Бот {bot.user} (ROFL ANTIRAID) успешно запущен!')
    logger.info("Бот запущен.")

@bot.event
async def on_message(message):
    if message.author.bot and message.author.id not in db["trusted"]:
        # Подозрительная активность от других ботов
        pass 

    if message.author.id not in db["trusted"] and not message.author.guild_permissions.administrator:
        content = message.content.lower()
        
        # 1. Проверка на инвайты
        if INVITE_REGEX.search(content):
            await message.delete()
            db["stats"]["deleted_messages"] += 1
            save_data(db)
            await message.channel.send(f"{message.author.mention}, отправка ссылок-инвайтов запрещена!", delete_after=5)
            logger.info(f"Удален инвайт от {message.author}.")
            return

        # 2. Проверка на Zalgo
        if ZALGO_REGEX.search(content):
            await message.delete()
            db["stats"]["deleted_messages"] += 1
            save_data(db)
            logger.info(f"Удален Zalgo-текст от {message.author}.")
            return

        # 3. Проверка на банворды
        for word in db["banwords"]:
            if word in content:
                await message.delete()
                db["stats"]["deleted_messages"] += 1
                try:
                    await message.author.ban(reason="Использование запрещенного слова")
                    db["stats"]["total_bans"] += 1
                    save_data(db)
                except discord.Forbidden:
                    pass
                logger.info(f"Пользователь {message.author} забанен за банворд.")
                return

    await bot.process_commands(message)

@bot.event
async def on_guild_channel_create(channel):
    # Простейшая защита от масс-создания каналов (рейда)
    # Если за короткое время создается много каналов - бот удаляет их параллельно
    if db["raid_mode"]:
        try:
            await channel.delete(reason="Антирейд: удаление спам-канала")
            db["stats"]["deleted_channels"] += 1
            save_data(db)
        except:
            pass

@bot.event
async def on_member_join(member):
    # Превентивный бан подозрительных ботов
    if member.bot and member.id not in db["trusted"]:
        try:
            await member.ban(reason="Антирейд: Превентивный бан незарегистрированного бота")
            db["stats"]["preventive_bans"] += 1
            db["stats"]["total_bans"] += 1
            save_data(db)
            
            # Уведомление владельцу
            owner = await bot.fetch_user(OWNER_ID)
            if owner:
                await owner.send(f"🚨 **ПРЕДУПРЕЖДЕНИЕ О РЕЙДЕ** 🚨\nПопытка захода незарегистрированного бота: {member.name}. Бот был автоматически заблокирован.")
        except:
            pass

# --- ГИБРИДНЫЕ КОМАНДЫ ---

@bot.hybrid_command(name="help", description="Справочник по функционалу бота")
async def help_cmd(ctx):
    embed = discord.Embed(title="Справочник ROFL ANTIRAID", color=discord.Color.red())
    embed.add_field(name="?status", value="Статус бота и статистика", inline=False)
    embed.add_field(name="?scan", value="Поиск плохих ботов", inline=False)
    embed.add_field(name="?backup / ?restore <ID>", value="Создание и восстановление бекапов", inline=False)
    embed.add_field(name="?purge", value="Очистка канала", inline=False)
    embed.add_field(name="?lockdown / ?unlock", value="Блокировка/Разблокировка сервера", inline=False)
    embed.add_field(name="?trust / ?untrust @user", value="Управление доверенными лицами", inline=False)
    embed.add_field(name="?reset", value="Сброс до заводских настроек", inline=False)
    embed.add_field(name="?addbanword / ?delbanword / ?banwords", value="Управление банвордами", inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="status", description="Выводит статус и статистику бота")
async def status_cmd(ctx):
    uptime = int(time.time() - bot.start_time)
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    lockdown = "Включен 🔴" if not ctx.guild.default_role.permissions.send_messages else "Выключен 🟢"
    raid_mode = "Включен 🔴" if db.get("raid_mode", False) else "Выключен 🟢"
    
    webhooks = len(await ctx.guild.webhooks())
    trusted_count = len(db["trusted"])
    
    embed = discord.Embed(title="📊 Статус ROFL ANTIRAID", color=discord.Color.blue())
    embed.add_field(name="Аптайм", value=f"{hours}ч {minutes}м {seconds}с", inline=True)
    embed.add_field(name="Локдаун", value=lockdown, inline=True)
    embed.add_field(name="Рейд-мод", value=raid_mode, inline=True)
    embed.add_field(name="Людей на сервере", value=str(ctx.guild.member_count), inline=True)
    embed.add_field(name="Вебхуков", value=str(webhooks), inline=True)
    embed.add_field(name="В белом списке", value=str(trusted_count), inline=True)
    
    stats = db["stats"]
    embed.add_field(name="Превентивных банов", value=str(stats["preventive_bans"]), inline=True)
    embed.add_field(name="Всего банов", value=str(stats["total_bans"]), inline=True)
    embed.add_field(name="Удалено каналов", value=str(stats["deleted_channels"]), inline=True)
    embed.add_field(name="Удалено сообщений", value=str(stats["deleted_messages"]), inline=True)
    embed.add_field(name="Пережито рейдов", value=str(stats["total_raids"]), inline=True)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="scan", description="Сканирование сервера на поиск опасных ботов")
@is_owner_or_trusted()
async def scan_cmd(ctx):
    suspicious = []
    for member in ctx.guild.members:
        if member.bot and member.id not in db["trusted"]:
            suspicious.append(member.mention)
    
    if suspicious:
        await ctx.send(f"⚠️ Найдены подозрительные боты не из белого списка:\n{', '.join(suspicious)}\nРекомендуется выдать им бан.")
    else:
        await ctx.send("✅ Сервер чист, подозрительных ботов не найдено.")

@bot.hybrid_command(name="backup", description="Делает бекап сервера")
@is_owner_or_trusted()
async def backup_cmd(ctx):
    await ctx.send("⏳ Создаю бекап каналов и ролей...")
    backup_id = str(uuid.uuid4())[:8]
    
    backup_data = {
        "roles": [{"name": r.name, "color": r.color.value, "hoist": r.hoist, "mentionable": r.mentionable} for r in ctx.guild.roles if not r.is_default() and not r.is_bot_managed()],
        "channels": [{"name": c.name, "type": str(c.type), "category": c.category.name if c.category else None} for c in ctx.guild.channels]
    }
    
    db["backups"][backup_id] = backup_data
    save_data(db)
    await ctx.send(f"✅ Бекап успешно создан! ID: `{backup_id}`")

@bot.hybrid_command(name="restore", description="Восстанавливает состояние сервера из бекапа")
@is_owner_or_trusted()
async def restore_cmd(ctx, backup_id: str):
    if backup_id not in db["backups"]:
        return await ctx.send("❌ Бекап с таким ID не найден.")
    
    await ctx.send("⚠️ Начинаю процесс восстановления (это может занять время из-за лимитов Discord)...")
    data = db["backups"][backup_id]
    
    # Асинхронное удаление текущих каналов (максимально быстро)
    tasks = [channel.delete() for channel in ctx.guild.channels]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Создание новых каналов из бекапа
    categories = {}
    for c in data["channels"]:
        if c["type"] == "category":
            cat = await ctx.guild.create_category(name=c["name"])
            categories[c["name"]] = cat
            
    for c in data["channels"]:
        cat = categories.get(c["category"])
        if c["type"] == "text":
            await ctx.guild.create_text_channel(name=c["name"], category=cat)
        elif c["type"] == "voice":
            await ctx.guild.create_voice_channel(name=c["name"], category=cat)
            
    # Запасной канал, чтобы не потерять сервер
    if not ctx.guild.text_channels:
        await ctx.guild.create_text_channel(name="system-restored")

@bot.hybrid_command(name="purge", description="Очищает канал от сообщений")
@is_owner_or_trusted()
async def purge_cmd(ctx, limit: int = 100):
    await ctx.channel.purge(limit=limit)
    await ctx.send(f"✅ Очищено {limit} сообщений.", delete_after=3)

@bot.hybrid_command(name="lockdown", description="Запрещает всем писать на сервере")
@is_owner_or_trusted()
async def lockdown_cmd(ctx):
    default_role = ctx.guild.default_role
    perms = default_role.permissions
    perms.send_messages = False
    await default_role.edit(permissions=perms, reason="Включен режим ЛОКДАУНА")
    
    db["raid_mode"] = True
    save_data(db)
    await ctx.send("🔒 **Режим ЛОКДАУНА активирован.** Обычные пользователи больше не могут отправлять сообщения.")

@bot.hybrid_command(name="unlock", description="Снимает режим локдауна")
@is_owner_or_trusted()
async def unlock_cmd(ctx):
    default_role = ctx.guild.default_role
    perms = default_role.permissions
    perms.send_messages = True
    await default_role.edit(permissions=perms, reason="Выключен режим ЛОКДАУНА")
    
    db["raid_mode"] = False
    save_data(db)
    await ctx.send("🔓 **Режим ЛОКДАУНА отключен.**")

@bot.hybrid_command(name="trust", description="Добавляет в белый список")
@is_owner_or_trusted()
async def trust_cmd(ctx, user: discord.User):
    if user.id not in db["trusted"]:
        db["trusted"].append(user.id)
        save_data(db)
        await ctx.send(f"✅ {user.mention} добавлен в доверенный список.")
    else:
        await ctx.send("Этот пользователь уже в списке.")

@bot.hybrid_command(name="untrust", description="Удаляет из белого списка")
@is_owner_or_trusted()
async def untrust_cmd(ctx, user: discord.User):
    if user.id == OWNER_ID:
        return await ctx.send("❌ Нельзя удалить владельца из белого списка!")
    if user.id in db["trusted"]:
        db["trusted"].remove(user.id)
        save_data(db)
        await ctx.send(f"✅ {user.mention} удален из доверенного списка.")
    else:
        await ctx.send("Этого пользователя нет в списке.")

@bot.hybrid_command(name="reset", description="Сброс настроек бота")
@is_owner_or_trusted()
async def reset_cmd(ctx):
    global db
    db = {
        "trusted": [OWNER_ID],
        "banwords": [],
        "backups": {},
        "stats": default_data["stats"],
        "raid_mode": False
    }
    save_data(db)
    await ctx.send("🔄 Настройки бота успешно сброшены к заводским.")

@bot.hybrid_command(name="addbanword", description="Добавляет банворд")
@is_owner_or_trusted()
async def addbanword_cmd(ctx, word: str):
    word = word.lower()
    if word not in db["banwords"]:
        db["banwords"].append(word)
        save_data(db)
        await ctx.send(f"✅ Слово `{word}` добавлено в черный список.")
    else:
        await ctx.send("Это слово уже есть в списке.")

@bot.hybrid_command(name="delbanword", description="Удаляет банворд")
@is_owner_or_trusted()
async def delbanword_cmd(ctx, word: str):
    word = word.lower()
    if word in db["banwords"]:
        db["banwords"].remove(word)
        save_data(db)
        await ctx.send(f"✅ Слово `{word}` удалено из черного списка.")
    else:
        await ctx.send("Этого слова нет в списке.")

@bot.hybrid_command(name="banwords", description="Список банвордов")
@is_owner_or_trusted()
async def banwords_cmd(ctx):
    if not db["banwords"]:
        await ctx.send("Список банвордов пуст.")
    else:
        await ctx.send(f"📜 Список банвордов: {', '.join(db['banwords'])}")

bot.run(os.getenv("TOKEN"))

