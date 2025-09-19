import os
import io
import asyncio
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import google.generativeai as genai
from gtts import gTTS
import speech_recognition as sr
from apscheduler.schedulers.asyncio import AsyncIOScheduler

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Load .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# --- Helpers ---
async def generate_ai_answer(prompt: str) -> str:
    try:
        res = await asyncio.to_thread(model.generate_content, prompt)
        return getattr(res, "text", str(res))
    except Exception as e:
        logger.exception("AI error: %s", e)
        return f"❌ AI xatosi: {e}"

# Speech → Text (fallback)
def speech_to_text(voice_bytes):
    if not AudioSegment:
        return "❌ Ovoz faylini o‘qish uchun `pydub` kerak. O‘rnatilmagan."
    recognizer = sr.Recognizer()
    try:
        with io.BytesIO(voice_bytes) as f:
            audio = AudioSegment.from_file(f, format="ogg")
            audio.export("temp.wav", format="wav")
        with sr.AudioFile("temp.wav") as source:
            data = recognizer.record(source)
            text = recognizer.recognize_google(data, language="uz-UZ")
            return text
    except sr.UnknownValueError:
        return "❌ Ovoz tushunilmadi."
    except Exception as e:
        logger.exception("Speech error: %s", e)
        return f"❌ Ovoz xatosi: {e}"
    finally:
        if os.path.exists("temp.wav"):
            os.remove("temp.wav")

# Text → Speech (fallback)
def text_to_speech_bytes(text, lang="uz"):
    try:
        buf = io.BytesIO()
        gTTS(text=text, lang=lang).write_to_fp(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        logger.exception("TTS error: %s", e)
        return None

# Rasm tahlili (fallback bilan)
async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        # AI modeli agar rasmni qo‘llamasa, fallback matn qaytariladi
        try:
            prompt = "Rasmni tavsiflab bering (qisqa)."
            res = await asyncio.to_thread(model.generate_content, prompt)
            answer = getattr(res, "text", str(res))
        except Exception:
            answer = "📷 Rasm qabul qilindi, lekin AI tahlil qila olmadi."

        await update.message.reply_text(answer)
    except Exception as e:
        logger.exception("Photo error: %s", e)
        await update.message.reply_text(f"❌ Rasmni tahlil qilishda xato: {e}")

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Salom! Men yordamchi botman.\nBuyruqlar: /weather, /crypto, /translate, /currency")

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        city = " ".join(context.args) if context.args else "Tashkent"
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        res = requests.get(url, timeout=10).json()
        if res.get("cod") != 200:
            await update.message.reply_text("❌ Ob-havo topilmadi.")
            return
        temp = res["main"]["temp"]
        desc = res["weather"][0]["description"]
        await update.message.reply_text(f"🌤 {city}: {desc}, {temp}°C")
    except Exception as e:
        await update.message.reply_text(f"❌ Ob-havo xatosi: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.voice:
        file = await context.bot.get_file(update.message.voice.file_id)
        voice_bytes = await file.download_as_bytearray()
        text = speech_to_text(voice_bytes)
        await update.message.reply_text(f"🎙 Ovoz matnga: {text}")
        return
    elif update.message.photo:
        await handle_photo_message(update, context)
        return
    elif update.message.text:
        text = update.message.text
        res = await generate_ai_answer(text)
        await update.message.reply_text(res)
    else:
        await update.message.reply_text("❌ Matn, rasm yoki ovoz yuboring.")

# --- Main ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.VOICE | filters.PHOTO, handle_message))

    # Kunlik hisobot (fallback bilan)
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    async def send_report():
        try:
            await app.bot.send_message(ADMIN_ID, "📊 Kunlik hisobot: Bot ishlayapti ✅")
        except Exception as e:
            logger.exception("Report error: %s", e)
    scheduler.add_job(send_report, "cron", hour=23, minute=59)
    scheduler.start()

    logger.info("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
