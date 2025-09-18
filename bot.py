import os
import asyncio
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

# --- Log sozlamalari ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- .env yuklash ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not WEATHER_API_KEY:
    logging.error("Xato: TELEGRAM_TOKEN, GEMINI_API_KEY yoki WEATHER_API_KEY topilmadi!")
    exit(1)

# --- Gemini sozlamalari ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "gemini-1.5-flash",
    generation_config=genai.types.GenerationConfig(max_output_tokens=500, temperature=0.7)
)

# --- Shaharlar, kripto va tillar ---
UZ_CITIES = ["Tashkent", "Samarkand", "Bukhara", "Khiva", "Andijan", "Namangan",
             "Fergana", "Kokand", "Jizzakh", "Navoiy", "Qarshi", "Termez",
             "Gulistan", "Shahrisabz", "Urgench"]

CRYPTO_COINS = ["bitcoin", "ethereum", "tether", "bnb", "solana", "dogecoin"]

LANG_CODES = {"🇺🇸 Ingliz": "en", "🇷🇺 Rus": "ru", "🇺🇿 O‘zbek": "uz", "🇹🇷 Turk": "tr",
              "🇩🇪 Nemis": "de", "🇫🇷 Fransuz": "fr"}

WEATHER_CONDITIONS = {
    "clear sky": "ochiq osmon", "few clouds": "biroz bulutli", "scattered clouds": "sochma bulutlar",
    "broken clouds": "qisman bulutli", "overcast clouds": "to‘liq bulutli", "shower rain": "jala",
    "light rain": "yengil yomg‘ir", "moderate rain": "o‘rtacha yomg‘ir", "heavy intensity rain": "kuchli yomg‘ir",
    "rain": "yomg‘ir", "snow": "qor", "mist": "tuman", "thunderstorm": "momaqaldiroq",
    "fog": "tuman", "haze": "xira havo", "dust": "chang", "sand": "qumli bo‘ron", "tornado": "tornado"
}

# --- Foydalanuvchilar ---
def add_user(user_id, context):
    users = context.bot_data.get("users", set())
    users.add(user_id)
    context.bot_data["users"] = users

# --- Visa / AI ---
async def handle_visa_query(update: Update, context: ContextTypes.DEFAULT_TYPE, text):
    prompt = f"Visa bilan bog'liq yoki umumiy savol: {text}"
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

# --- Start va Help ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id, context)
    await update.message.reply_text("Salom! Men Vizabotman 🤖. /help ni yozing.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - Botni ishga tushirish\n"
        "/help - Yordam\n"
        "/weather - Shaharni tanlab, ob-havo olish\n"
        "/crypto - Kripto narxini bilish\n"
        "/translate - Tarjima\n"
        "/currency - Valyuta kurslari (CBU)\n"
        "🤖 Visa yoki boshqa savol: xabar yuboring\n"
    )
    if update.effective_user.id == ADMIN_ID:
        text += "\n--- 🛠 Admin komandalar ---\n/broadcast - Hammaga xabar\n/report - Hisobot\n/myid - ID'ingiz"
    await update.message.reply_text(text)

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning ID: {update.effective_user.id}")

# --- WEATHER ---
async def weather_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard, row = [], []
    for i, city in enumerate(UZ_CITIES, start=1):
        row.append(InlineKeyboardButton(city, callback_data=f"weather_{city}"))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await update.message.reply_text("🌤 Qaysi shahar ob-havo?", reply_markup=InlineKeyboardMarkup(keyboard))

async def weather_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    city = query.data.replace("weather_", "")
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=en"
    try:
        res = requests.get(url).json()
        if res.get("cod") != 200:
            await query.edit_message_text(f"❌ Ob-havo topilmadi: {city}")
            return
        temp = res["main"]["temp"]
        desc = res["weather"][0]["description"].lower()
        uz_desc = WEATHER_CONDITIONS.get(desc, desc)
        await query.edit_message_text(f"🌤 {city} ob-havosi:\n{temp}°C, {uz_desc}")
    except Exception as e:
        await query.edit_message_text(f"Xatolik: {str(e)}")

# --- CRYPTO ---
async def crypto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(coin.capitalize(), callback_data=f"crypto_{coin}")] for coin in CRYPTO_COINS]
    await update.message.reply_text("💰 Qaysi kripto?", reply_markup=InlineKeyboardMarkup(keyboard))

async def crypto_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    coin = query.data.replace("crypto_", "")
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"
    try:
        res = requests.get(url).json()
        if coin not in res:
            await query.edit_message_text(f"❌ Kripto topilmadi: {coin}")
            return
        price = res[coin]["usd"]
        await query.edit_message_text(f"💰 {coin.capitalize()} narxi: ${price}")
    except Exception as e:
        await query.edit_message_text(f"Xatolik: {str(e)}")

# --- TRANSLATE ---
async def translate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(name, callback_data=f"lang_{code}")] for name, code in LANG_CODES.items()]
    await update.message.reply_text("🔤 Qaysi tilga?", reply_markup=InlineKeyboardMarkup(keyboard))

async def lang_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_", "")
    context.user_data["target_lang"] = lang
    await query.edit_message_text(f"✍️ Matn yuboring, tarjima {lang} ga qilinadi.")

async def translate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "target_lang" not in context.user_data:
        await handle_visa_query(update, context, update.message.text)
        return
    lang = context.user_data["target_lang"]
    text = update.message.text
    try:
        translated = GoogleTranslator(source="auto", target=lang).translate(text)
        await update.message.reply_text(f"🔤 Tarjima ({lang}): {translated}")
        del context.user_data["target_lang"]
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

# --- CURRENCY ---
async def currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = "https://cbu.uz/oz/arkhiv-kursov-valyut/json/"
    try:
        res = requests.get(url).json()
        selected = [c for c in res if c["Ccy"] in ["USD", "EUR", "RUB"]]
        text = "💱 Bugungi valyuta kurslari:\n"
        for c in selected:
            text += f"1 {c['Ccy']} = {c['Rate']} so‘m\n"
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

# --- ADMIN ---
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /broadcast Xabar")
        return
    text = " ".join(context.args)
    users = context.bot_data.get("users", set())
    sent, failed = 0, 0
    for uid in users:
        try:
            await context.bot.send_message(uid, f"📢 Admin: {text}")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Yuborildi: {sent}, ❌ Xato: {failed}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Siz admin emassiz.")
        return
    await send_report(context)

async def send_report(context: ContextTypes.DEFAULT_TYPE):
    logs = context.bot_data.get("logs", [])
    users = context.bot_data.get("users", set())
    if not logs:
        await context.bot.send_message(ADMIN_ID, "📊 Bugun hech qanday so‘rov bo‘lmadi.")
        return
    msg = f"📊 Kunlik hisobot\n👥 Foydalanuvchilar: {len(users)}\n💬 So‘rovlar: {len(logs)}\n📝 Oxirgi 5:\n"
    for t, uid, text in logs[-5:]:
        msg += f"{t} | {uid} | {text}\n"
    await context.bot.send_message(ADMIN_ID, msg)

# --- MAIN ---
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_start))
    application.add_handler(CommandHandler("crypto", crypto_start))
    application.add_handler(CommandHandler("translate", translate_start))
    application.add_handler(CommandHandler("currency", currency))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CallbackQueryHandler(weather_button, pattern="^weather_"))
    application.add_handler(CallbackQueryHandler(crypto_button, pattern="^crypto_"))
    application.add_handler(CallbackQueryHandler(lang_button, pattern="^lang_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_message))

    # Scheduler
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    async def report_job():
        await send_report(application)
    scheduler.add_job(lambda: asyncio.create_task(report_job()), "cron", hour=23, minute=59)
    scheduler.start()

    # Polling / Webhook
    port = int(os.environ.get("PORT", 8443))
    url_path = TELEGRAM_TOKEN
    webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/{url_path}" if RENDER_EXTERNAL_HOSTNAME else None

    if not webhook_url:
        logging.info("Polling rejimida ishga tushmoqda...")
        application.run_polling()
    else:
        logging.info(f"Webhook bilan ishga tushmoqda: {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=url_path,
            webhook_url=webhook_url,
            allowed_updates=None
        )

if __name__ == "__main__":
    main()
