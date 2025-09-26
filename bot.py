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
from pptx import Presentation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# Logging sozlamalari
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
    logger.error("TELEGRAM_TOKEN, GROK_API_KEY yoki WEATHER_API_KEY .env faylda topilmadi!")
    exit(1)

# Grok API sozlamalari
GROK_API_BASE_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "llama3-8b-8192" # Yoki boshqa mavjud model, masalan: "grok-1.5-flash"

# Grok orqali matn generatsiya qilish funksiyasi
async def grok_generate_content(prompt, max_tokens=1024, temperature=0.7):
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
        response = requests.post(GROK_API_BASE_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Grok API xatoligi: {str(e)}")
        return f"Groq API bilan bog'lanishda xatolik yuz berdi. Iltimos, keyinroq qayta urining."

# 🌤 O‘zbekiston shaharlar ro‘yxati
UZ_CITIES = [
    "Tashkent", "Samarkand", "Bukhara", "Khiva", "Andijan", "Namangan",
    "Fergana", "Kokand", "Jizzakh", "Navoiy", "Qarshi", "Termez",
    "Gulistan", "Shahrisabz", "Urgench"
]

# 💰 Mashhur kriptovalyutalar
CRYPTO_COINS = ["bitcoin", "ethereum", "tether", "binancecoin", "solana", "dogecoin"]

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
    "clear sky": "ochiq osmon", "few clouds": "biroz bulutli", "scattered clouds": "tarqoq bulutlar",
    "broken clouds": "parcha bulutlar", "overcast clouds": "to‘liq bulutli", "shower rain": "jala",
    "light rain": "yengil yomg‘ir", "moderate rain": "o‘rtacha yomg‘ir", "heavy intensity rain": "kuchli yomg‘ir",
    "rain": "yomg‘ir", "snow": "qor", "mist": "tuman", "thunderstorm": "momaqaldiroq",
    "fog": "quyuq tuman", "haze": "g'ubor", "dust": "chang", "sand": "qum", "tornado": "tornado"
}

# --- Foydalanuvchilarni saqlash ---
def add_user(user_id, context):
    users = context.bot_data.get("users", set())
    users.add(user_id)
    context.bot_data["users"] = users

# ---- Chat tarixini boshqarish ----
def get_chat_history(context, user_id, max_length=5):
    history = context.user_data.get(user_id, {}).get("chat_history", [])
    return history[-max_length:]

def update_chat_history(context, user_id, message):
    if user_id not in context.user_data:
        context.user_data[user_id] = {"chat_history": []}
    context.user_data[user_id]["chat_history"].append(message)

# ---- Ovozli xabarni matnga aylantirish ----
def speech_to_text(voice_file):
    recognizer = sr.Recognizer()
    try:
        with io.BytesIO(voice_file) as audio_stream:
            ogg_audio = AudioSegment.from_ogg(audio_stream)
            wav_io = io.BytesIO()
            ogg_audio.export(wav_io, format="wav")
            wav_io.seek(0)
            with sr.AudioFile(wav_io) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language="uz-UZ")
                return text
    except sr.UnknownValueError:
        return "Ovozli xabar tushunilmadi."
    except sr.RequestError as e:
        return f"Audioni qayta ishlashda xatolik: {str(e)}"
    except Exception as e:
        logger.error(f"Ovozni matnga o'girishda kutilmagan xato: {e}")
        return f"Ovozni matnga o'girishda xatolik."

# ---- Matnni ovozga aylantirish ----
def text_to_speech(text, lang="uz"):
    # gTTS o'zbek tilini qo'llab-quvvatlamaydi, shuning uchun eng yaqin til sifatida rus tilidan foydalanamiz
    tts_lang = lang if lang != "uz" else "ru"
    try:
        tts = gTTS(text=text, lang=tts_lang, slow=False)
        audio_file = io.BytesIO()
        tts.write_to_fp(audio_file)
        audio_file.seek(0)
        return audio_file
    except Exception as e:
        logger.error(f"Ovozga aylantirishda xatolik: {str(e)}")
        return None

# ---- Rasmlarni analiz qilish ----
async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Rasm qabul qilindi. Ushbu model rasmlarni tahlil qila olmaydi, lekin siz rasm haqida savol berishingiz mumkin.")

# ---- Umumiy xabar handleri (matn va ovoz) ----
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id, context)

    # Antispam
    last_message_time = context.user_data.get("last_message_time", None)
    if last_message_time and datetime.now() < last_message_time + timedelta(seconds=3):
        await update.message.reply_text("⏳ Iltimos, biroz sekinroq yozing.")
        return
    context.user_data["last_message_time"] = datetime.now()

    text = ""
    is_voice = False

    # Matnli xabar
    if update.message.text:
        text = update.message.text
        logger.info(f"Foydalanuvchi {user_id} dan matnli xabar: {text}")

    # Ovozli xabar
    elif update.message.voice:
        is_voice = True
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        voice_data = await file.download_as_bytearray()
        logger.info(f"Foydalanuvchi {user_id} dan ovozli xabar qabul qilindi.")
        text = speech_to_text(voice_data)
        await update.message.reply_text(f"🗣️ Sizning so'rovingiz: \"{text}\"")
    
    else:
        return

    # Kiritilgan matn bo'sh emasligini tekshirish
    if not text or not text.strip():
        await update.message.reply_text("Iltimos, biror ma'lumot kiriting.")
        return

    # Tarjima rejimini tekshirish
    if context.user_data.get("awaiting_translation"):
        await translate_message(update, context, text)
        return

    # Prezentatsiya rejimini tekshirish
    if context.user_data.get("awaiting_presentation_topic"):
        await handle_presentation_topic(update, context, text)
        return
    
    await update.message.chat.send_action(action='typing')

    # AI javobini olish
    history = get_chat_history(context, user_id)
    prompt = "\n".join([f"User: {h['user']}\nBot: {h['bot']}" for h in history])
    prompt += f"\nUser: {text}\nBot:"
    
    response_text = await grok_generate_content(prompt)
    
    update_chat_history(context, user_id, {"user": text, "bot": response_text})

    # Javob turi
    if is_voice:
        audio_file = text_to_speech(response_text, lang="uz")
        if audio_file:
            await update.message.reply_voice(audio_file)
    else:
        await update.message.reply_text(response_text)

# ---- Start va Help ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id, context)
    context.user_data.clear() # Bot qayta ishga tushganda eski holatlarni tozalash
    await update.message.reply_text("Salom! Men Grok asosida ishlovchi yordamchi botman 🤖.\nSavollaringizni bering yoki yordam uchun /help buyrug'ini bosing.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Mavjud buyruqlar:\n"
        "/start - Botni ishga tushirish\n"
        "/help - Yordam menyusini ko'rsatish\n"
        "/weather - O'zbekiston shaharlaridagi ob-havo\n"
        "/crypto - Kriptovalyutalar narxlari\n"
        "/translate - Matnni boshqa tilga tarjima qilish\n"
        "/currency - Markaziy Bank valyuta kurslari\n"
        "/presentation - Mavzu bo'yicha prezentatsiya yaratish\n\n"
        "🤖 Shunchaki matn yoki ovozli xabar yuborib men bilan suhbatlashishingiz mumkin!"
    )
    if update.effective_user.id == ADMIN_ID:
        text += (
            "\n--- 🛠 Admin buyruqlari ---\n"
            "/broadcast <xabar> - Barcha foydalanuvchilarga xabar yuborish\n"
            "/report - Kunlik hisobotni olish\n"
            "/myid - O'z Telegram ID raqamingizni bilish"
        )
    await update.message.reply_text(text)

# ---- My ID ----
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning ID: `{update.effective_user.id}`", parse_mode='MarkdownV2')

# ---- WEATHER ----
async def weather_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    row = []
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
            await query.edit_message_text(f"❌ Kechirasiz, {city} uchun ob-havo ma'lumoti topilmadi.")
            return
        temp = res["main"]["temp"]
        desc = res["weather"][0]["description"].lower()
        uz_desc = WEATHER_CONDITIONS.get(desc, desc)
        await query.edit_message_text(f"📍 {city}\n\n🌡️ Harorat: {temp}°C\n🌤 Holat: {uz_desc.capitalize()}")
    except Exception as e:
        logger.error(f"Ob-havo olishda xatolik: {e}")
        await query.edit_message_text(f"Ob-havo ma'lumotlarini olishda xatolik yuz berdi.")

# ---- CRYPTO ----
async def crypto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(coin.capitalize(), callback_data=f"crypto_{coin}")] for coin in CRYPTO_COINS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💰 Qaysi kriptovalyuta narxini bilmoqchisiz?", reply_markup=reply_markup)

async def crypto_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    coin = query.data.replace("crypto_", "")
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"
    try:
        res = requests.get(url).json()
        if coin not in res:
            await query.edit_message_text(f"❌ Kechirasiz, {coin} uchun narx topilmadi.")
            return
        price = res[coin]["usd"]
        await query.edit_message_text(f"💰 {coin.capitalize()} narxi: ${price:,.2f}")
    except Exception as e:
        logger.error(f"Kripto narxini olishda xatolik: {e}")
        await query.edit_message_text("Kriptovalyuta narxini olishda xatolik yuz berdi.")

# ---- TRANSLATE ----
async def translate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(name, callback_data=f"lang_{code}")] for name, code in LANG_CODES.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔤 Qaysi tilga tarjima qilmoqchisiz?", reply_markup=reply_markup)

async def lang_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang_code = query.data.replace("lang_", "")
    context.user_data["target_lang"] = lang_code
    context.user_data["awaiting_translation"] = True
    lang_name = next((name for name, code in LANG_CODES.items() if code == lang_code), lang_code)
    await query.edit_message_text(f"✍️ Endi matn yuboring, men uni {lang_name} tiliga tarjima qilaman.")

async def translate_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text_to_translate):
    target_lang = context.user_data.get("target_lang")
    if not target_lang:
        await update.message.reply_text("Tarjima uchun til tanlanmagan. /translate buyrug'ini qayta bosing.")
        return

    lang_name = next((name for name, code in LANG_CODES.items() if code == target_lang), target_lang)
    await update.message.reply_text(f"Tarjima qilinmoqda...")
    await update.message.chat.send_action(action='typing')

    try:
        # Grok orqali tarjima qilish
        prompt = f"Translate the following text to {lang_name} language. Return only the translated text, without any extra explanations or introductions. The text to translate is: \"{text_to_translate}\""
        translated_text = await grok_generate_content(prompt, max_tokens=len(text_to_translate) * 2)
        await update.message.reply_text(f"🔤 Tarjima ({lang_name}):\n\n{translated_text}")
    except Exception as e:
        logger.error(f"Grok tarjima xatoligi: {str(e)}")
        # Fallback: deep-translator
        try:
            translated_fallback = GoogleTranslator(source="auto", target=target_lang).translate(text_to_translate)
            await update.message.reply_text(f"🔤 Tarjima (fallback):\n\n{translated_fallback}")
        except Exception as e2:
            await update.message.reply_text(f"❌ Tarjima qilishda xatolik yuz berdi: {str(e2)}")
    finally:
        # Tarjima holatini tozalash
        if "target_lang" in context.user_data: del context.user_data["target_lang"]
        if "awaiting_translation" in context.user_data: del context.user_data["awaiting_translation"]


# ---- CURRENCY ----
async def currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = "https://cbu.uz/oz/arkhiv-kursov-valyut/json/"
    try:
        res = requests.get(url).json()
        if not res:
            await update.message.reply_text("❌ Valyuta kurslari topilmadi.")
            return
        selected = [c for c in res if c["Ccy"] in ["USD", "EUR", "RUB"]]
        text = f"💱 {datetime.now().strftime('%d.%m.%Y')} uchun valyuta kurslari (O'zbekiston MB):\n\n"
        for c in selected:
            text += f"🇺🇸 1 {c['Ccy']} = {c['Rate']} so'm\n" if c['Ccy'] == 'USD' else \
                    f"🇪🇺 1 {c['Ccy']} = {c['Rate']} so'm\n" if c['Ccy'] == 'EUR' else \
                    f"🇷🇺 1 {c['Ccy']} = {c['Rate']} so'm\n"
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Valyuta kursini olishda xatolik: {e}")
        await update.message.reply_text("Valyuta kurslarini olishda xatolik yuz berdi.")

# ---- ADMIN funksiyalari ----
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /broadcast <Xabar matni>")
        return
    text = " ".join(context.args)
    users = context.bot_data.get("users", set())
    if not users:
        await update.message.reply_text("📭 Hali foydalanuvchilar yo'q.")
        return
    sent, failed = 0, 0
    for uid in users:
        try:
            await context.bot.send_message(uid, f"📢 Admindan xabar:\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Yuborildi: {sent} ta\n❌ Xatolik: {failed} ta")

async def report(context: ContextTypes.DEFAULT_TYPE):
    users_count = len(context.bot_data.get("users", set()))
    report_text = f"📊 Kunlik hisobot\n\n👥 Jami foydalanuvchilar soni: {users_count}"
    await context.bot.send_message(ADMIN_ID, report_text)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    await report(context)

# ---- Prezentatsiya tayyorlash ----
async def presentation_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎥 Prezentatsiya uchun mavzuni kiriting (masalan, 'Koinot sirlari' yoki 'Sun'iy intellekt kelajagi').")
    context.user_data["awaiting_presentation_topic"] = True

async def handle_presentation_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic):
    await update.message.reply_text(f"📝 \"{topic}\" mavzusida prezentatsiya tayyorlanmoqda... Bu bir necha daqiqa vaqt olishi mumkin, iltimos, kuting.")
    await update.message.chat.send_action(action='upload_document')

    prompt = f"""Create a concise presentation outline for the topic: "{topic}".
Provide the content in a simple, structured format.
Follow this structure exactly:
SLIDE 1: Title
[Title of the presentation]
SLIDE 2: Introduction
[A brief 2-3 sentence introduction to the topic.]
SLIDE 3: Key Point 1
[Title for the first main point]
[A few bullet points or a short paragraph explaining the first point.]
SLIDE 4: Key Point 2
[Title for the second main point]
[A few bullet points or a short paragraph explaining the second point.]
SLIDE 5: Key Point 3
[Title for the third main point]
[A few bullet points or a short paragraph explaining the third point.]
SLIDE 6: Conclusion
[A brief 1-2 sentence conclusion summarizing the presentation.]
SLIDE 7: Q&A
[A slide for questions, simply titled 'Questions & Answers']

Do not add any extra comments or text outside of this structure."""
    
    try:
        response_text = await grok_generate_content(prompt, max_tokens=2048)
        
        # Prezentatsiya fayllarini yaratish
        ppt_io = create_ppt(response_text, topic)
        pdf_io = create_pdf(response_text)

        await update.message.reply_document(document=ppt_io, filename=f"{topic}_presentation.pptx")
        await update.message.reply_document(document=pdf_io, filename=f"{topic}_presentation.pdf")
        await update.message.reply_text("🎉 Prezentatsiya PowerPoint (.pptx) va PDF formatida tayyor!")
    except Exception as e:
        logger.error(f"Prezentatsiya yaratishda xatolik: {str(e)}")
        await update.message.reply_text(f"❌ Kechirasiz, prezentatsiya yaratishda xatolik yuz berdi.")
    finally:
        del context.user_data["awaiting_presentation_topic"]

def create_ppt(text_content, topic):
    prs = Presentation()
    # Title Slide
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    title = slide.shapes.title
    subtitle = slide.placeholders.get(1)
    title.text = topic
    if subtitle:
        subtitle.text = f"Tayyorlandi: {datetime.now().strftime('%Y-%m-%d')}"

    # Content Slides
    content_slide_layout = prs.slide_layouts[1]
    slides_data = text_content.split('SLIDE ')[1:]
    
    for slide_text in slides_data:
        if not slide_text.strip():
            continue
        
        lines = slide_text.strip().split('\n')
        slide_title = lines[0].split(':', 1)[1].strip()
        slide_content = "\n".join(lines[1:]).strip()

        slide = prs.slides.add_slide(content_slide_layout)
        title_shape = slide.shapes.title
        body_shape = slide.placeholders[1]
        
        title_shape.text = slide_title
        body_shape.text = slide_content

    ppt_io = io.BytesIO()
    prs.save(ppt_io)
    ppt_io.seek(0)
    return ppt_io

def create_pdf(text_content):
    pdf_io = io.BytesIO()
    doc = SimpleDocTemplate(pdf_io, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    slides_data = text_content.split('SLIDE ')[1:]
    for slide_text in slides_data:
        if not slide_text.strip():
            continue
            
        lines = slide_text.strip().split('\n')
        slide_title = lines[0].split(':', 1)[1].strip()
        slide_content = "\n".join(lines[1:]).strip().replace('\n', '<br/>')

        story.append(Paragraph(slide_title, styles['h1']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(slide_content, styles['BodyText']))
        story.append(Spacer(1, 24))

    doc.build(story)
    pdf_io.seek(0)
    return pdf_io


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
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("presentation", presentation_start))

    # Tugma handlerlar
    application.add_handler(CallbackQueryHandler(weather_button, pattern="^weather_"))
    application.add_handler(CallbackQueryHandler(crypto_button, pattern="^crypto_"))
    application.add_handler(CallbackQueryHandler(lang_button, pattern="^lang_"))

    # Umumiy xabar handleri
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    # Scheduler
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    # Kunlik hisobotni yuborish (har kuni 23:59 da)
    scheduler.add_job(report, "cron", hour=23, minute=59, args=[context])
    scheduler.start()
    
    logger.info("Bot ishga tushmoqda...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()