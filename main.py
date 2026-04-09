embed.timestamp = discord.utils.utcnow()
        await log_channel.send(embed=embed)

async def mute_member(member: discord.Member, minutes: int, reason: str):
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    
    dm_embed = discord.Embed(title="🔇 Вам выдан мут", color=discord.Color.red())
    dm_embed.add_field(name="Сервер", value=member.guild.name, inline=False)
    dm_embed.add_field(name="⏱ Время", value=f"{minutes} минут", inline=True)
    dm_embed.add_field(name="📝 Причина", value=reason, inline=True)
    await send_dm(member, dm_embed)

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
    
    dm_embed = discord.Embed(title="⚠️ Вы получили предупреждение", color=discord.Color.yellow())
    dm_embed.add_field(name="Сервер", value=channel.guild.name, inline=False)
    dm_embed.add_field(name="📝 Причина", value=reason, inline=True)
    dm_embed.add_field(name="🔢 Варнов", value=f"{count}/3", inline=True)

    embed = discord.Embed(color=discord.Color.yellow())
    embed.add_field(name="⚠️ Предупреждение", value=f"{member.mention}", inline=True)
    embed.add_field(name="📝 Причина", value=reason, inline=True)
    embed.add_field(name="🔢 Варнов", value=f"{count}/3", inline=True)
    
    if count >= 3:
        dm_embed.add_field(name="🔨 Действие", value="Вы были забанены", inline=False)
        dm_embed.color = discord.Color.dark_red()
        await send_dm(member, dm_embed)
        
        await member.ban(reason="3 предупреждения")
        embed.add_field(name="🔨 Действие", value="Бан с сервера", inline=False)
        embed.color = discord.Color.dark_red()
        warnings[member.id] = 0
    else:
        await send_dm(member, dm_embed)

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
        await log_violation(bot, message.author, "Массовое упоминание (@everyone/@here)", content, message.channel)
        await message.delete()
        await mute_member(message.author, 30, "Использование @everyone/@here")
        await add_warning(message.author, message.channel, "Использование @everyone/@here")
        return

    cleaned_content = re.sub(r'\s+', '', content.lower())
    if "discord.gg/" in cleaned_content or "discord.com/invite/" in cleaned_content or "discordapp.com/invite/" in cleaned_content:
        await log_violation(bot, message.author, "Реклама Discord-сервера", content, message.channel)
        await message.delete()
        await mute_member(message.author, 60, "Реклама Discord-серверов")
        await add_warning(message.author, message.channel, "Реклама серверов")
        return

    if is_spamming(message.author.id):
        await log_violation(bot, message.author, "Спам сообщениями", "Пользователь отправил слишком много сообщений за короткое время.", message.channel)
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
    
    dm_embed = discord.Embed(title="🔊 Ваш мут снят", color=discord.Color.green())
    dm_embed.add_field(name="Сервер", value=ctx.guild.name, inline=False)
    dm_embed.add_field(name="📝 Причина", value=reason, inline=False)
    await send_dm(member, dm_embed)

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
    
    dm_embed = discord.Embed(title="✅ С вас снято предупреждение", color=discord.Color.green())
    dm_embed.add_field(name="Сервер", value=ctx.guild.name, inline=False)
    dm_embed.add_field(name="🔢 Осталось варнов", value=f"{warnings[member.id]}/3", inline=True)
    await send_dm(member, dm_embed)

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
        await ctx.send("❌ Укажи пользователя/аргументы", delete_after=5)
    elif isinstance(error, commands.CommandNotFound):
        pass

bot.run(os.getenv("TOKEN"))
