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
from dotenv import load_dotenv
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment
import io
import logging
from PIL import Image
from pptx import Presentation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# .env yuklash
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not TELEGRAM_TOKEN or not GROK_API_KEY or not WEATHER_API_KEY:
    logger.error("TELEGRAM_TOKEN, GROK_API_KEY yoki WEATHER_API_KEY topilmadi!")
    exit(1)

# Grok API sozlamalari
GROK_API_BASE_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-beta"

# Grok orqali matn generatsiya qilish funksiyasi
def grok_generate_content(prompt, max_tokens=500, temperature=0.7):
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": GROK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    try:
        resp = requests.post(GROK_API_BASE_URL, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        j = resp.json()
        # Defensive access
        choice = j.get("choices")
        if choice and isinstance(choice, list):
            message = choice[0].get("message")
            if message:
                return message.get("content", "")
        # Fallback to raw text if present
        return j.get("text", str(j))
    except Exception as e:
        logger.error(f"Grok API xatoligi: {e}")
        return f"Xatolik: {e}"

# --- Helper functions (unchanged lists) ---
UZ_CITIES = [
    "Tashkent", "Samarkand", "Bukhara", "Khiva", "Andijan", "Namangan",
    "Fergana", "Kokand", "Jizzakh", "Navoiy", "Qarshi", "Termez",
    "Gulistan", "Shahrisabz", "Urgench"
]
CRYPTO_COINS = ["bitcoin", "ethereum", "tether", "bnb", "solana", "dogecoin"]
LANG_CODES = {
    "🇺🇸 Ingliz": "en",
    "🇷🇺 Rus": "ru",
    "🇺🇿 O‘zbek": "uz",
    "🇹🇷 Turk": "tr",
    "🇩🇪 Nemis": "de",
    "🇫🇷 Fransuz": "fr"
}
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

# --- Simple user storage ---
def add_user(user_id, context):
    users = context.bot_data.get("users", set())
    users.add(user_id)
    context.bot_data["users"] = users

# Chat history: use per-user context.user_data (PTB provides per-user dict)
def get_chat_history(context, max_length=5):
    history = context.user_data.get("chat_history", [])
    return history[-max_length:]

def update_chat_history(context, message):
    if "chat_history" not in context.user_data:
        context.user_data["chat_history"] = []
    context.user_data["chat_history"].append(message)

# ---- Ovozli xabarni matnga aylantirish ----
def speech_to_text(voice_file_bytes):
    recognizer = sr.Recognizer()
    try:
        with io.BytesIO(voice_file_bytes) as audio_file:
            audio = AudioSegment.from_file(audio_file, format="ogg")
            audio.export("temp.wav", format="wav")
            with sr.AudioFile("temp.wav") as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language="uz-UZ")
                return text
    except sr.UnknownValueError:
        return "Ovozli xabar tushunilmadi."
    except sr.RequestError as e:
        return f"Audioni qayta ishlashda xatolik: {e}"
    except Exception as e:
        return f"Xatolik: {e}"
    finally:
        if os.path.exists("temp.wav"):
            try:
                os.remove("temp.wav")
            except:
                pass

# ---- Matnni ovozga aylantirish ----
def text_to_speech(text, lang="uz"):
    if lang == "uz":
        lang = "ru"  # gTTS uchun O'zbek yo'q, rus tiliga o'tish
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        audio_buf = io.BytesIO()
        tts.write_to_fp(audio_buf)
        audio_buf.seek(0)
        return audio_buf
    except Exception as e:
        logger.error(f"Ovozga aylantirishda xatolik: {e}")
        return None

# ---- Tilni o'zgartirish ----
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(name, callback_data=f"set_lang_{code}")]
                for name, code in LANG_CODES.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔤 Qaysi tilni tanlaysiz?", reply_markup=reply_markup)

async def set_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("set_lang_", "")
    context.user_data["language"] = lang
    await query.edit_message_text(f"Til o'zgartirildi: {lang}")

# ---- Rasmlarni analiz qilish (soddaroq) ----
async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_data = await file.download_as_bytearray()
    logger.info("Rasm yuklab olindi.")

    # Grok ko'pincha faqat matnli ChatCompletion qabul qiladi; shu sababli biz rasm mavjudligini
    # xabar qilamiz va foydalanuvchidan rasmni ta'riflash uchun so'rov olamiz.
    await update.message.reply_text("Rasm olindi. Agar rasm haqida ta'rif yoki savolingiz bo'lsa, yozing — men Grok orqali javob beraman.")
    # Chat history-ga rasm haqida xabar yozamiz
    update_chat_history(context, {"user": "[PHOTO]", "bot": ""})

# ---- Umumiy xabar handleri (matn va ovoz) ----
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id, context)

    # Antispam
    last_message_time = context.user_data.get("last_message_time", None)
    if last_message_time and datetime.now() < last_message_time + timedelta(seconds=2):
        await update.message.reply_text("⏳ Iltimos, biroz kuting!")
        return
    context.user_data["last_message_time"] = datetime.now()

    # Chat tarixini olish
    history = get_chat_history(context)

    text = None
    # Matnli xabar
    if update.message.text:
        text = update.message.text
        logger.info(f"Matnli xabar: {text}")
        update_chat_history(context, {"user": text, "bot": ""})

    # Ovozli xabar
    elif update.message.voice:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        voice_data = await file.download_as_bytearray()
        logger.info("Ovozli xabar yuklab olindi.")
        text = speech_to_text(voice_data)
        await update.message.reply_text(f"Sizning ovozli xabaringiz: {text}")
        update_chat_history(context, {"user": text, "bot": ""})

    # Rasmlar
    elif update.message.photo:
        await handle_photo_message(update, context)
        return

    else:
        await update.message.reply_text("Noma'lum xabar. Matn, ovoz yoki rasm yuboring.")
        return

    # AI javobini olish (Grok)
    prompt = f"Foydalanuvchi: {text}\nQisqacha, foydali javob bering:" 
    # Grok so'rovini tarmoqqa bloklamaslik uchun asyncio.to_thread bilan chaqiramiz
    response_text = await asyncio.to_thread(grok_generate_content, prompt)
    if not response_text:
        response_text = "Grok javobi bo'sh yoki xato yuz berdi."

    update_chat_history(context, {"user": text, "bot": response_text})

    # Javob turi
    if update.message.voice:
        audio_file = text_to_speech(response_text, lang=context.user_data.get("language", "uz"))
        if audio_file:
            await update.message.reply_voice(audio_file)
        else:
            await update.message.reply_text(response_text)
    else:
        await update.message.reply_text(response_text)

# ---- Start va Help ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id, context)
    await update.message.reply_text("Salom! Men Vizabotman 🤖. Visa yordami uchun savollaringizni bering yoki /help ni ishlat.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - Botni ishga tushirish\n"
        "/help - Yordam\n"
        "/weather - Shaharni tanlab, ob-havo olish\n"
        "/crypto - Kripto tanlab, narxini olish\n"
        "/translate - Tilni tanlab, tarjima qilish\n"
        "/currency - Bugungi valyuta kurslari (CBU)\n"
        "🤖 Visa yordami uchun matn, ovoz yoki rasm yuboring – ketma-ket suhbatda javob beraman!\n"
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
    await update.message.reply_text(f"Sizning ID: {update.effective_user.id}")

# ---- WEATHER ----
async def weather_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.edit_message_text(f"Xatolik: {e}")

# ---- CRYPTO ----
async def crypto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.edit_message_text(f"Xatolik: {e}")

# ---- TRANSLATE ----
async def translate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if "target_lang" in context.user_data:
        lang = context.user_data["target_lang"]
        text = update.message.text
        try:
            prompt = f"Translate the following text into {lang}: {text}"
            # Grok dan tarjima so'raymiz
            translated = await asyncio.to_thread(grok_generate_content, prompt)
            if translated and not translated.startswith("Xatolik"):
                await update.message.reply_text(f"🔤 Tarjima ({lang}): {translated}")
            else:
                # Fallback to GoogleTranslator
                translated2 = GoogleTranslator(source="auto", target=lang).translate(text)
                await update.message.reply_text(f"🔤 Tarjima ({lang}): {translated2}")
            del context.user_data["target_lang"]
        except Exception as e:
            await update.message.reply_text(f"❌ Tarjima xatoligi: {e}")
            if "target_lang" in context.user_data:
                del context.user_data["target_lang"]

# ---- CURRENCY ----
async def currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(f"Xatolik: {e}")

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
    if not users:
        await update.message.reply_text("📭 Hali foydalanuvchi yo‘q.")
        return
    sent = failed = 0
    for uid in users:
        try:
            await context.bot.send_message(uid, f"📢 Admin xabari:\n\n{text}")
            sent += 1
        except Exception:
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

# ---- Prezentatsiya tayyorlash ----
async def presentation_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎥 Prezentatsiya mavzusini kiriting (masalan, 'O‘zbekiston tarixi' yoki 'AI texnologiyalari').")
    context.user_data["awaiting_presentation_topic"] = True

async def handle_presentation_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_presentation_topic"):
        topic = update.message.text
        await update.message.reply_text(f"📝 '{topic}' bo'yicha prezentatsiya tayyorlanmoqda...")
        prompt = (
            f"Siz AI yordamchisiz. Quyidagi mavzu bo'yicha qisqa prezentatsiya matni yarating: {topic}. Strukturani quyidagi tarzda saqlang:\n"
            "- Sarlavha\n- Kirish (2-3 jumlali)\n- Asosiy qism (3 ta asosiy nuqta bilan)\n- Xulosa (1-2 jumlali)\nNatijani faqat matn sifatida qaytaring, hech qanday qo'shimcha izohsiz."
        )
        try:
            response_text = await asyncio.to_thread(grok_generate_content, prompt)
            if not response_text:
                raise Exception("Grok javobi bo'sh")

            lines = [ln for ln in response_text.split('\n') if ln.strip()]

            ppt = Presentation()
            title_slide_layout = ppt.slide_layouts[0]
            slide = ppt.slides.add_slide(title_slide_layout)
            title = slide.shapes.title
            subtitle = slide.placeholders[1]
            title.text = lines[0] if lines else topic
            subtitle.text = "Tayyorlandi: " + datetime.now().strftime("%Y-%m-%d %H:%M")

            body_slide_layout = ppt.slide_layouts[1]
            for line in lines[1:]:
                slide = ppt.slides.add_slide(body_slide_layout)
                title = slide.shapes.title
                body = slide.placeholders[1]
                title.text = line[:40]
                body.text = line

            ppt_io = io.BytesIO()
            ppt.save(ppt_io)
            ppt_io.seek(0)

            pdf_io = io.BytesIO()
            doc = SimpleDocTemplate(pdf_io, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            for line in lines:
                story.append(Paragraph(line, styles['Heading1']))
                story.append(Spacer(1, 12))
            doc.build(story)
            pdf_io.seek(0)

            await update.message.reply_document(document=ppt_io, filename=f"{topic}_presentation.pptx")
            await update.message.reply_document(document=pdf_io, filename=f"{topic}_presentation.pdf")
            await update.message.reply_text("🎉 Prezentatsiya PowerPoint (.pptx) va PDF formatida yuborildi!")
        except Exception as e:
            logger.error(f"Prezentatsiya yaratishda xatolik: {e}")
            await update.message.reply_text(f"❌ Prezentatsiya yaratishda xatolik: {e}")
        finally:
            context.user_data.pop("awaiting_presentation_topic", None)

# ---- MAIN ----
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_start))
    application.add_handler(CommandHandler("crypto", crypto_start))
    application.add_handler(CommandHandler("translate", translate_start))
    application.add_handler(CommandHandler("currency", currency))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("presentation", presentation_start))

    # Callback handlers
    application.add_handler(CallbackQueryHandler(weather_button, pattern="^weather_"))
    application.add_handler(CallbackQueryHandler(crypto_button, pattern="^crypto_"))
    application.add_handler(CallbackQueryHandler(lang_button, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(set_language_button, pattern="^set_lang_"))

    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND | filters.VOICE | filters.PHOTO, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_message))

    scheduler = AsyncIOScheduler()
    # schedule daily report (uses application as context) -- adapt if needed
    scheduler.add_job(lambda: asyncio.create_task(send_report(application)), 'cron', hour=23, minute=59)
    scheduler.start()

    port = int(os.environ.get("PORT", 8443))
    url_path = TELEGRAM_TOKEN
    webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/{url_path}" if RENDER_EXTERNAL_HOSTNAME else None

    if not webhook_url:
        logger.info("Polling rejimida ishlayapman.")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    else:
        logger.info(f"Bot webhook bilan ishga tushmoqda: {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=url_path,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES
        )

if __name__ == "__main__":
    main()
