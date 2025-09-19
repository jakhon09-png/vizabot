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
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment
import io
import logging
import json

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# .env yuklash
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not WEATHER_API_KEY:
    logger.error("Xato: TELEGRAM_TOKEN, GEMINI_API_KEY yoki WEATHER_API_KEY topilmadi!")
    exit(1)

# Gemini sozlamalari
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "gemini-1.5-flash",
    generation_config=genai.types.GenerationConfig(
        max_output_tokens=500,
        temperature=0.7,
    )
)

# 🌤 O‘zbekiston shaharlar ro‘yxati
UZ_CITIES = [
    "Tashkent", "Samarkand", "Bukhara", "Khiva", "Andijan", "Namangan",
    "Fergana", "Kokand", "Jizzakh", "Navoiy", "Qarshi", "Termez",
    "Gulistan", "Shahrisabz", "Urgench"
]

# 💰 Mashhur kriptovalyutalar
CRYPTO_COINS = ["bitcoin", "ethereum", "tether", "bnb", "solana", "dogecoin"]

# 🔤 Tarjima tillari
LANG_CODES = {
    "🇺🇸 Ingliz": "en",
    "🇷🇺 Rus": "ru",
    "🇺🇿 O‘zbek": "uz",
    "🇹🇷 Turk": "tr",
    "🇩🇪 Nemis": "de",
    "🇫🇷 Fransuz": "fr"
}

# 🌤 Inglizcha → O‘zbekcha ob-havo tarjimalari
WEATHER_CONDITIONS = {
    "clear sky": "ochiq osmon",
    "few clouds": "biroz bulutli",
    "scattered clouds": "sochma bulutlar",
    "broken clouds": "qisman bulutli",
    "overcast clouds": "to‘liq bulutli",
    "shower rain": "jala",
    "light rain": "yengil yomg‘ir",
    "moderate rain": "o‘rtacha yomg‘ir",
    "heavy intensity rain": "kuchli yomg‘ir",
    "rain": "yomg‘ir",
    "snow": "qor",
    "mist": "tuman",
    "thunderstorm": "momaqaldiroq",
    "fog": "tuman",
    "haze": "xira havo",
    "dust": "chang",
    "sand": "qumli bo‘ron",
    "tornado": "tornado"
}

# --- Foydalanuvchilarni saqlash ---
def add_user(user_id, context):
    users = context.bot_data.get("users", set())
    users.add(user_id)
    context.bot_data["users"] = users
    logger.info(f"Yangi foydalanuvchi qo‘shildi: {user_id}")

# --- Loglarni saqlash ---
def add_log(context, user_id, text):
    logs = context.bot_data.get("logs", [])
    logs.append((datetime.now().strftime("%H:%M"), user_id, text))
    if len(logs) > 100:  # Maksimum 100 ta log saqlash
        logs = logs[-100:]
    context.bot_data["logs"] = logs
    logger.info(f"Yangi log qo‘shildi: {user_id}, {text}")

# ---- Ovozli xabarni matnga aylantirish ----
def speech_to_text(voice_file):
    recognizer = sr.Recognizer()
    try:
        with io.BytesIO(voice_file) as audio_file:
            audio = AudioSegment.from_file(audio_file, format="ogg")
            audio.export("temp.wav", format="wav")
            with sr.AudioFile("temp.wav") as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language="uz-UZ")
                logger.info(f"Matnni ovozga aylantirish muvaffaqiyatli: {text}")
                return text
    except sr.UnknownValueError:
        logger.error("Ovozli xabar tushunilmadi.")
        return "Ovozli xabar tushunilmadi."
    except sr.RequestError as e:
        logger.error(f"Audioni qayta ishlashda xatolik: {str(e)}")
        return "Audioni qayta ishlashda xatolik."
    except Exception as e:
        logger.error(f"Xatolik ovozli qayta ishlashda: {str(e)}")
        return "Xatolik yuz berdi."
    finally:
        if os.path.exists("temp.wav"):
            os.remove("temp.wav")

# ---- Matnni ovozga aylantirish ----
def text_to_speech(text, lang="uz"):
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        with io.BytesIO() as audio_file:
            tts.write_to_fp(audio_file)
            audio_file.seek(0)
            logger.info("Ovozli javob tayyorlandi.")
            return audio_file
    except Exception as e:
        logger.error(f"Ovozga aylantirishda xatolik: {str(e)}")
        return None

# ---- Visa yordami uchun maxsus funksiya ----
async def handle_visa_query(update: Update, context: ContextTypes.DEFAULT_TYPE, text):
    add_log(context, update.effective_user.id, text)
    prompt = f"Berilgan savol visa bilan bog'liq bo'lsa, maxsus visa yordami sifatida javob bering. Agar mavzu boshqa bo'lsa, umumiy javob bering: {text}"
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini javobida xatolik: {str(e)}")
        return f"Xatolik: {str(e)}"

# ---- Ovozli xabar handler ----
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    if not voice:
        await update.message.reply_text("Iltimos, ovozli xabar yuboring!")
        return

    file = await context.bot.get_file(voice.file_id)
    voice_data = await file.download_as_bytearray()
    logger.info("Ovozli xabar yuklab olindi.")

    text = speech_to_text(voice_data)
    await update.message.reply_text(f"Sizning ovozli xabaringiz: {text}")

    response_text = await handle_visa_query(update, context, text)
    await update.message.reply_text(f"Javob: {response_text}")

    audio_file = text_to_speech(response_text, lang="uz")
    if audio_file:
        await update.message.reply_voice(audio_file)
    else:
        await update.message.reply_text("Ovozli javob tayyorlanmadi, faqat matn bilan javob beraman.")

# ---- Start va Help ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id, context)
    add_log(context, update.effective_user.id, "/start")
    await update.message.reply_text("Salom! Men Vizabotman 🤖. Ovozli yoki matnli visa yordami uchun savollaringizni bering yoki /help ni ishlat.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_log(context, update.effective_user.id, "/help")
    text = (
        "/start - Botni ishga tushirish\n"
        "/help - Yordam\n"
        "/weather - Shaharni tanlab, ob-havo olish\n"
        "/crypto - Kripto tanlab, narxini olish\n"
        "/translate - Tilni tanlab, tarjima qilish\n"
        "/currency - Bugungi valyuta kurslari (CBU)\n"
        "🤖 Visa yoki boshqa savollar uchun ovozli yoki matnli xabar yuboring – Gemini AI javob beradi\n"
    )
    if update.effective_user.id == ADMIN_ID:
        text += (
            "\n--- 🛠 Admin komandalar ---\n"
            "/broadcast - Hammaga xabar yuborish\n"
            "/report - So‘rovlar haqida hisobot\n"
            "/myid - O‘z ID’ingizni bilish\n"
        )
    await update.message.reply_text(text)

# ---- My ID ----
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_log(context, update.effective_user.id, "/myid")
    await update.message.reply_text(f"Sizning ID: {update.effective_user.id}")

# ---- WEATHER ----
async def weather_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_log(context, update.effective_user.id, "/weather")
    keyboard, row = [], []
    for i, city in enumerate(UZ_CITIES, start=1):
        row.append(InlineKeyboardButton(city, callback_data=f"weather_{city}"))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🌤 Qaysi shahar ob-havosini bilmoqchisiz?", reply_markup=reply_markup)

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

# ---- CRYPTO ----
async def crypto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_log(context, update.effective_user.id, "/crypto")
    keyboard = [[InlineKeyboardButton(coin.capitalize(), callback_data=f"crypto_{coin}")]
                for coin in CRYPTO_COINS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💰 Qaysi kripto narxini bilmoqchisiz?", reply_markup=reply_markup)

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

# ---- TRANSLATE ----
async def translate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_log(context, update.effective_user.id, "/translate")
    keyboard = [[InlineKeyboardButton(name, callback_data=f"lang_{code}")]
                for name, code in LANG_CODES.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔤 Qaysi tilga tarjima qilmoqchisiz?", reply_markup=reply_markup)

async def lang_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_", "")
    context.user_data["target_lang"] = lang
    await query.edit_message_text(f"✍️ Endi matn yuboring, men uni `{lang}` tiliga tarjima qilaman.")

async def translate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "target_lang" not in context.user_data:
        await handle_voice_message(update, context)
        return
    lang = context.user_data["target_lang"]
    text = update.message.text
    add_log(context, update.effective_user.id, text)
    try:
        translated = GoogleTranslator(source="auto", target=lang).translate(text)
        await update.message.reply_text(f"🔤 Tarjima ({lang}): {translated}")
        del context.user_data["target_lang"]
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

# ---- CURRENCY ----
async def currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_log(context, update.effective_user.id, "/currency")
    url = "https://cbu.uz/oz/arkhiv-kursov-valyut/json/"
    try:
        res = requests.get(url).json()
        if not res:
            await update.message.reply_text("❌ Valyuta kurslari topilmadi.")
            return
        selected = [c for c in res if c["Ccy"] in ["USD", "EUR", "RUB"]]
        text = "💱 Bugungi valyuta kurslari (CBU):\n\n"
        for c in selected:
            text += f"1 {c['Ccy']} = {c['Rate']} so‘m\n"
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

# ---- ADMIN funksiyalari ----
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /broadcast Xabar matni")
        return
    text = " ".join(context.args)
    users = context.bot_data.get("users", set())
    logger.info(f"Broadcast boshlanmoqda. Foydalanuvchilar soni: {len(users)}")
    if not users:
        await update.message.reply_text("📭 Hali foydalanuvchi yo‘q.")
        return
    sent, failed = 0, 0
    for uid in users:
        try:
            await context.bot.send_message(uid, f"📢 Admin xabari:\n\n{text}")
            sent += 1
        except Exception as e:
            logger.error(f"Xabar yuborishda xatolik ({uid}): {str(e)}")
            failed += 1
    await update.message.reply_text(f"✅ Yuborildi: {sent} ta\n❌ Xato: {failed} ta")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Siz admin emassiz.")
        return
    await send_report(context)

async def send_report(context: ContextTypes.DEFAULT_TYPE):
    logs = context.bot_data.get("logs", [])
    users = context.bot_data.get("users", set())
    logger.info(f"Hisobot tayyorlanmoqda. Foydalanuvchilar: {len(users)}, Loglar: {len(logs)}")
    if not logs:
        await context.bot.send_message(ADMIN_ID, "📊 Bugun hech qanday so‘rov bo‘lmadi.")
        return
    msg = (
        f"📊 Kunlik hisobot\n\n"
        f"👥 Foydalanuvchilar soni: {len(users)}\n"
        f"💬 So‘rovlar soni: {len(logs)}\n\n"
        "📝 Oxirgi 5 ta so‘rov:\n"
    )
    for time, uid, text in logs[-5:]:
        msg += f"🕒 {time} | 👤 {uid}\n💬 {text}\n\n"
    await context.bot.send_message(ADMIN_ID, msg)

# ---- MAIN ----
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Buyruqlar
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_start))
    application.add_handler(CommandHandler("crypto", crypto_start))
    application.add_handler(CommandHandler("translate", translate_start))
    application.add_handler(CommandHandler("currency", currency))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("myid", myid))

    # Tugma handlerlar
    application.add_handler(CallbackQueryHandler(weather_button, pattern="^weather_"))
    application.add_handler(CallbackQueryHandler(crypto_button, pattern="^crypto_"))
    application.add_handler(CallbackQueryHandler(lang_button, pattern="^lang_"))

    # Ovozli va matnli handlerlar
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_message))

    # Scheduler (23:59 da hisobot yuboradi)
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(send_report, "cron", hour=23, minute=59, args=[application])

    # Webhook yoki polling
    port = int(os.environ.get("PORT", 8443))
    url_path = TELEGRAM_TOKEN
    webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/{url_path}" if RENDER_EXTERNAL_HOSTNAME else None

    if not webhook_url:
        logger.info("Xato: RENDER_EXTERNAL_HOSTNAME aniqlanmadi! Polling rejimida ishlayapman.")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        scheduler.start()
    else:
        logger.info(f"Bot webhook bilan ishga tushmoqda: {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=url_path,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES
        )
        scheduler.start()

if __name__ == "__main__":
    main()