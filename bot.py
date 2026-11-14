
import os
import re
import asyncio
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.account import CheckUsernameRequest

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["TELETHON_SESSION"]
OWNER_ID = int(os.environ["OWNER_ID"])

client = TelegramClient(
    StringSession(SESSION), API_ID, API_HASH,
    flood_sleep_threshold=60
)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def allowed(update):
    return update.effective_user and update.effective_user.id == OWNER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Username Checker готов!\n\n"
        "Отправь username или TXT-файл со списком.\n"
        "Команда /id покажет твой Telegram ID."
    )


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Твой Telegram ID: {update.effective_user.id}"
    )


async def check_name(username):
    if not USERNAME_RE.fullmatch(username):
        return "INVALID"

    try:
        result = await client(CheckUsernameRequest(username=username))
        return "FREE" if result else "TAKEN"

    except errors.FloodWaitError as e:
        await asyncio.sleep(e.seconds + 1)
        return await check_name(username)

    except Exception as e:
        error = str(e).upper()
        if "USERNAME_OCCUPIED" in error:
            return "TAKEN"
        if "USERNAME_PURCHASE_AVAILABLE" in error:
            return "COLLECTIBLE"
        if "USERNAME_INVALID" in error:
            return "INVALID"
        return "UNKNOWN"


async def process_names(update, names):
    if not allowed(update):
        return

    names = list(dict.fromkeys(
        n.strip().lstrip("@")
        for n in names if n.strip()
    ))

    if not names:
        await update.message.reply_text("Список пуст.")
        return

    if len(names) > 500:
        await update.message.reply_text(
            "Максимум 500 имён за один файл в этой версии."
        )
        return

    msg = await update.message.reply_text(
        f"Начинаю проверку: {len(names)} имён."
    )

    results = []
    for i, name in enumerate(names, 1):
        status = await check_name(name)
        results.append(f"@{name} — {status}")

        if i % 10 == 0:
            await msg.edit_text(f"Проверено {i}/{len(names)}")

        await asyncio.sleep(1.5)

    output = "\n".join(results)
    free = sum(" — FREE" in r for r in results)

    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(output)

    await msg.edit_text(
        f"Готово!\nВсего: {len(names)}\nСвободных по проверке: {free}"
    )

    with open("results.txt", "rb") as f:
        await update.message.reply_document(
            document=f, filename="results.txt"
        )


async def text_handler(update, context):
    if not allowed(update):
        return
    names = update.message.text.split()
    await process_names(update, names)


async def file_handler(update, context):
    if not allowed(update):
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("Пришли TXT-файл.")
        return

    if doc.file_size > 500_000:
        await update.message.reply_text("Файл слишком большой.")
        return

    file = await context.bot.get_file(doc.file_id)
    data = await file.download_as_bytearray()

    try:
        names = data.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        await update.message.reply_text("Файл должен быть в UTF-8.")
        return

    await process_names(update, names)


async def post_init(app):
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon session is not authorized")
    log.info("MTProto connected")


async def post_shutdown(app):
    await client.disconnect()


def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(MessageHandler(
        filters.Document.ALL, file_handler
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, text_handler
    ))

    app.run_polling()


if __name__ == "__main__":
    main()
