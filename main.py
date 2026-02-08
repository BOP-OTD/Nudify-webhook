import os
import asyncio
from datetime import datetime

import httpx
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse

from telegram import Update, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, PreCheckoutQueryHandler, filters

USER_CREDITS = {}  # user_id -> credits

# Pack definitions (change prices/credits whenever you want)
PACKS = {
    "pack_30": {"credits": 30, "stars": 100},
    "pack_75": {"credits": 75, "stars": 220},
    "pack_250": {"credits": 250, "stars": 600},
}
async def buy_30(update, context):
    pack_id = "pack_30"
    pack = PACKS[pack_id]

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"{pack['credits']} Credits",
        description="Credits for undress jobs",
        payload=pack_id,           # tells us which pack was bought
        provider_token="",         # IMPORTANT: Stars uses empty provider_token
        currency="XTR",            # IMPORTANT: Stars currency
        prices=[LabeledPrice(label="Credits", amount=pack["stars"])],
    )

async def precheckout_handler(update, context):
    # REQUIRED: without this, payment fails
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update, context):
    sp = update.message.successful_payment
    pack_id = sp.invoice_payload
    pack = PACKS.get(pack_id)

    if not pack:
        await update.message.reply_text("Payment received but pack not recognized. Contact support.")
        return

    user_id = update.effective_user.id
    USER_CREDITS[user_id] = USER_CREDITS.get(user_id, 0) + pack["credits"]

    await update.message.reply_text(
        f"✅ Payment successful!\nAdded {pack['credits']} credits.\nNew balance: {USER_CREDITS[user_id]}"
    )

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
    user_id = update.effective_user.id
    if USER_CREDITS.get(user_id, 0) <= 0:
        await update.message.reply_text("You have 0 credits. Type /buy30 to buy credits with Stars.")
        return

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
        
    USER_CREDITS[user_id] -= 1

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a photo to undress.")


tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(CommandHandler("buy30", buy_30))
tg_app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
tg_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
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
