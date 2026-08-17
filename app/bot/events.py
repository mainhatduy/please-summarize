"""Discord lifecycle and message events."""

from app.bot.commands.music import check_alone_voice_clients
from app.bot.facebook import handle_facebook_reel
from app.bot.logging import log
from app.bot.runtime import bot, facebook_service, tiktok_service
from app.bot.tiktok import handle_tiktok
from app.core.config import Config

_alone_checker_started = False


@bot.event
async def on_ready():
    global _alone_checker_started
    log.info("Đã đăng nhập: %s (ID: %s)", bot.user, bot.user.id)
    if not _alone_checker_started:
        bot.loop.create_task(check_alone_voice_clients())
        _alone_checker_started = True


@bot.event
async def on_message(message):
    if message.author.bot or message.author.id == bot.user.id:
        return
    if Config.CHANNEL_ID is not None and message.channel.id != Config.CHANNEL_ID:
        return

    content = message.content
    if tiktok_url := tiktok_service.detect_tiktok_url(content):
        await handle_tiktok(message, tiktok_url)
        return
    if facebook_url := facebook_service.detect_facebook_reel_url(content):
        await handle_facebook_reel(message, facebook_url)
        return
    prefix = bot.command_prefix
    if not content.startswith(prefix):
        return
    parts = content[len(prefix) :].split(maxsplit=1)
    if not parts:
        return
    command_name = parts[0].lower()
    command = bot.get_command(command_name)
    if command is None:
        log.warning("Lệnh '%s' không tồn tại.", command_name)
        return

    ctx = await bot.get_context(message)
    ctx.command = command
    ctx.prefix = prefix
    ctx.invoked_with = command_name
    skip_length = len(prefix) + len(command_name)
    ctx.view.index = skip_length
    ctx.view.previous = skip_length
    try:
        await command.invoke(ctx)
    except Exception as error:
        log.error("Lỗi khi invoke '%s': %s", command_name, error, exc_info=True)
        await message.channel.send(f"⚠️ Có lỗi xảy ra: {error}")


@bot.event
async def on_command_error(ctx, error):
    log.error("Lỗi lệnh '%s': %s", ctx.command, error, exc_info=True)
    await ctx.send(f"⚠️ Có lỗi xảy ra khi thực hiện lệnh: {error}")
