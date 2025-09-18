import os
import asyncio
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import google.generativeai as genai

# ======= Muhit o'zgaruvchilarini yuklash =======
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, WEATHER_API_KEY]):
    raise RuntimeError("Xato: TELEGRAM_TOKEN, GEMINI_API_KEY yoki WEATHER_API_KEY topilmadi!")

# ======= Gemini AI sozlamalari =======
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ======= Shaharlar va kripto =======
UZ_CITIES = ["Tashkent","Samarkand","Bukhara","Khiva","Andijan","Namangan",
             "Fergana","Kokand","Jizzakh","Navoiy","Qarshi","Termez",
             "Gulistan","Shahrisabz","Urgench"]

CRYPTO_COINS = ["bitcoin","ethereum","tether","bnb","solana","dogecoin"]

LANG_CODES = {
    "🇺🇸 Ingliz": "en",
    "🇷🇺 Rus": "ru",
    "🇺🇿 O‘zbek": "uz",
    "🇹🇷 Turk": "tr",
    "🇩🇪 Nemis": "de",
    "🇫🇷 Fransuz": "fr"
}

WEATHER_CONDITIONS = {
    "clear sky": "ochiq osmon", "few clouds": "biroz bulutli", "scattered clouds": "sochma bulutlar",
    "broken clouds": "qisman bulutli", "overcast clouds": "to‘liq bulutli", "shower rain": "jala",
    "light rain": "yengil yomg‘ir", "moderate rain": "o‘rtacha yomg‘ir", "heavy intensity rain": "kuchli yomg‘ir",
    "rain": "yomg‘ir", "snow": "qor", "mist": "tuman", "thunderstorm": "momaqaldiroq",
    "fog": "tuman", "haze": "xira havo", "dust": "chang", "sand": "qumli bo‘ron",
    "tornado": "tornado"
}

# ======= Foydalanuvchilarni saqlash =======
def add_user(user_id, context):
    users = context.bot_data.get("users", set())
    users.add(user_id)
    context.bot_data["users"] = users

# ======= Gemini AI javob =======
async def handle_ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id, context)

    last_time = context.user_data.get("last_message_time")
    if last_time and datetime.now() < last_time + timedelta(seconds=5):
        await update.message.reply_text("⏳ Iltimos, biroz kuting!")
        return
    context.user_data["last_message_time"] = datetime.now()

    try:
        response = await asyncio.to_thread(model.generate_content, update.message.text)
        ai_text = response.text
    except Exception as e:
        ai_text = f"Xatolik: {str(e)}"

    # Log saqlash
    logs = context.bot_data.get("logs", [])
    logs.append((datetime.now().strftime("%Y-%m-%d %H:%M"), user_id, update.message.text))
    context.bot_data["logs"] = logs[-1000:]

    await update.message.reply_text(ai_text)

# ======= Telegram komandalar =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id, context)
    await update.message.reply_text("Salom! Men AI botman 🤖 /help buyrug‘ini yozing.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - Botni ishga tushirish\n"
        "/help - Yordam\n"
        "/weather - Shaharni tanlab, ob-havo olish\n"
        "/crypto - Kripto narxini olish\n"
        "/translate - Tilni tanlab, tarjima qilish\n"
        "/currency - Valyuta kurslari\n"
        "🤖 Savolingizni yuboring — AI javob beradi"
    )
    if update.effective_user.id == ADMIN_ID:
        text += "\n--- Admin komandalar ---\n/broadcast\n/report\n/myid"
    await update.message.reply_text(text)

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning ID: {update.effective_user.id}")

# ======= Weather =======
async def weather_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard, row = [], []
    for i, city in enumerate(UZ_CITIES, start=1):
        row.append(InlineKeyboardButton(city, callback_data=f"weather_{city}"))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await update.message.reply_text("🌤 Qaysi shahar ob-havosini bilmoqchisiz?",
                                    reply_markup=InlineKeyboardMarkup(keyboard))

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

# ======= Crypto =======
async def crypto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(coin.capitalize(), callback_data=f"crypto_{coin}")]
                for coin in CRYPTO_COINS]
    await update.message.reply_text("💰 Qaysi kripto narxini bilmoqchisiz?", reply_markup=InlineKeyboardMarkup(keyboard))

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

# ======= Translate =======
async def translate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(name, callback_data=f"lang_{code}")]
                for name, code in LANG_CODES.items()]
    await update.message.reply_text("🔤 Qaysi tilga tarjima qilmoqchisiz?", reply_markup=InlineKeyboardMarkup(keyboard))

async def lang_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_", "")
    context.user_data["target_lang"] = lang
    await query.edit_message_text(f"✍️ Endi matn yuboring, men uni `{lang}` tiliga tarjima qilaman.")

async def translate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "target_lang" in context.user_data:
        lang = context.user_data["target_lang"]
        try:
            translated = GoogleTranslator(source="auto", target=lang).translate(update.message.text)
            await update.message.reply_text(f"🔤 Tarjima ({lang}): {translated}")
        except Exception as e:
            await update.message.reply_text(f"Xatolik: {str(e)}")
        del context.user_data["target_lang"]
    else:
        await handle_ai_message(update, context)

# ======= Scheduler =======
async def send_report(context: ContextTypes.DEFAULT_TYPE):
    logs = context.bot_data.get("logs", [])
    users = context.bot_data.get("users", set())
    if not logs:
        await context.bot.send_message(ADMIN_ID, "📊 Bugun hech qanday so‘rov bo‘lmadi.")
        return
    msg = f"📊 Kunlik hisobot\n\n👥 Foydalanuvchilar soni: {len(users)}\n💬 So‘rovlar soni: {len(logs)}\n\n📝 Oxirgi 5 ta so‘rov:\n"
    for time, uid, text in logs[-5:]:
        msg += f"🕒 {time} | 👤 {uid}\n💬 {text}\n\n"
    await context.bot.send_message(ADMIN_ID, msg)

# ======= MAIN =======
async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("weather", weather_start))
    application.add_handler(CommandHandler("crypto", crypto_start))
    application.add_handler(CommandHandler("translate", translate_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_message))
    application.add_handler(CallbackQueryHandler(weather_button, pattern="^weather_"))
    application.add_handler(CallbackQueryHandler(crypto_button, pattern="^crypto_"))
    application.add_handler(CallbackQueryHandler(lang_button, pattern="^lang_"))

    # Scheduler
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(send_report, "cron", hour=23, minute=59, args=[application])
    scheduler.start()

    # Webhook
    if not RENDER_EXTERNAL_HOSTNAME:
        print("Xato: RENDER_EXTERNAL_HOSTNAME aniqlanmadi, polling ishlayapti")
        await application.run_polling()
    else:
        webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/{TELEGRAM_TOKEN}"
        print(f"Webhook bilan ishga tushmoqda: {webhook_url}")
        await application.bot.set_webhook(webhook_url)
        await application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 8443)),
            url_path=TELEGRAM_TOKEN,
            webhook_url=webhook_url
        )

if __name__ == "__main__":
    asyncio.run(main())
