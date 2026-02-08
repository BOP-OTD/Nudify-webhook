import os
import asyncio
from datetime import datetime

import httpx
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

app = FastAPI()

# =========================
# ENV VARS (set in Render)
# =========================
BOT_TOKEN = os.environ["BOT_TOKEN"]

# This must be your Render base URL, e.g. https://your-service.onrender.com
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"]

# This is the API endpoint you POST to to START the undress job
# Example pattern: https://public-api.yoursite.fun/api/v1/photos/undress
undress_START_URL = os.environ["undress_START_URL"]

# Auth header settings (match your API docs)
# Examples:
#   API_KEY_HEADER=Authorization
#   API_KEY_VALUE=Bearer YOUR_KEY
# or
#   API_KEY_HEADER=x-api-key
#   API_KEY_VALUE=YOUR_KEY
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "")
API_KEY_VALUE = os.getenv("API_KEY_VALUE", "")

# Input field name for the START endpoint (your earlier screenshot showed "photo")
START_FILE_FIELD_NAME = os.getenv("START_FILE_FIELD_NAME", "photo")

# Webhook sends back: keys included ['webhook','id_gen','image'] and file field is "image"
WEBHOOK_RESULT_FILE_FIELD_NAME = os.getenv("WEBHOOK_RESULT_FILE_FIELD_NAME", "image")

# =========================
# In-memory job map:
# id_gen -> telegram_chat_id
# (Simple starter. If Render restarts, this map resets.)
# =========================
JOB_MAP: dict[str, int] = {}

# Telegram application
tg_app = Application.builder().token(BOT_TOKEN).build()


# =========================
# Telegram handlers
# =========================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me a photo and I’ll undress it."
    )

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Get the highest-res photo
    photo = update.message.photo[-1]
    file_obj = await context.bot.get_file(photo.file_id)
    photo_bytes = await file_obj.download_as_bytearray()

    # Create an id_gen we can use to route the webhook result back to this chat
    id_gen = f"tg_{chat_id}_{int(datetime.utcnow().timestamp())}"
    JOB_MAP[id_gen] = chat_id

    webhook_url = f"{PUBLIC_BASE_URL}/undress-photo-webhook"

    await update.message.reply_text("Queued. I’ll send the nude when it’s ready…")

    # Submit job to the undress API (START endpoint)
    headers = {}
    if API_KEY_HEADER and API_KEY_VALUE:
        headers[API_KEY_HEADER] = API_KEY_VALUE

    files = {
        START_FILE_FIELD_NAME: ("photo.jpg", bytes(photo_bytes), "image/jpeg")
    }
    data = {
        "id_gen": id_gen,
        "webhook": webhook_url
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            undress_START_URL,
            headers=headers,
            data=data,
            files=files
        )

    if r.status_code >= 300:
        # Remove mapping if start failed
        JOB_MAP.pop(id_gen, None)
        await update.message.reply_text(f"API start error: {r.status_code} {r.text[:300]}")
        return

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a photo to undress.")


tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(MessageHandler(filters.PHOTO, on_photo))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))


# =========================
# FastAPI routes
# =========================
@app.get("/")
def root():
    return {
        "ok": True,
        "bot": "running",
        "webhook_endpoint": "/undress-photo-webhook"
    }

@app.post("/undress-photo-webhook")
async def undress_webhook(request: Request):
    """
    Provider sends form-data keys: ['webhook','id_gen','image']
    We need: id_gen (form field) and image (file).
    """
    form = await request.form()
    id_gen = form.get("id_gen")
    if not id_gen:
        return JSONResponse({"ok": False, "error": "missing id_gen"}, status_code=400)

    file_obj = form.get(WEBHOOK_RESULT_FILE_FIELD_NAME)
    if not file_obj or not hasattr(file_obj, "read"):
        return JSONResponse(
            {"ok": False, "error": f"missing file field '{WEBHOOK_RESULT_FILE_FIELD_NAME}'"},
            status_code=400
        )

    chat_id = JOB_MAP.get(id_gen)
    if not chat_id:
        # If we don't recognize id_gen, just acknowledge so provider stops retrying
        return JSONResponse({"ok": True, "ignored": True, "reason": "unknown id_gen"})

    img_bytes = await file_obj.read()

    # Send result back to Telegram
    await tg_app.bot.send_photo(chat_id=chat_id, photo=img_bytes, caption="✅ undress complete")

    # Clean up mapping
    JOB_MAP.pop(id_gen, None)

    return JSONResponse({"ok": True})


# =========================
# Start telegram polling in background when FastAPI starts
# =========================
@app.on_event("startup")
async def on_startup():
    # Start telegram polling in the background
    async def runner():
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()
    asyncio.create_task(runner())
