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

# .env yuklash
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    print("Xato: TELEGRAM_TOKEN yoki GEMINI_API_KEY topilmadi!")
    exit(1)

# Gemini sozlamalari
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

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
    "very heavy rain": "juda kuchli yomg‘ir",
    "extreme rain": "o‘ta kuchli yomg‘ir",
    "rain": "yomg‘ir",
    "freezing rain": "muzlab tushadigan yomg‘ir",
    "light snow": "yengil qor",
    "snow": "qor",
    "heavy snow": "qalin qor",
    "sleet": "yomg‘ir-qor",
    "light shower sleet": "yengil yomg‘ir-qor",
    "shower sleet": "yomg‘ir-qor yog‘ishi",
    "light rain and snow": "yengil yomg‘ir-qor",
    "rain and snow": "yomg‘ir-qor aralash",
    "light shower snow": "yengil qor yog‘ishi",
    "shower snow": "qor yog‘ishi",
    "heavy shower snow": "kuchli qor yog‘ishi",
    "thunderstorm": "momaqaldiroq",
    "thunderstorm with rain": "momaqaldiroq va yomg‘ir",
    "thunderstorm with heavy rain": "momaqaldiroq va kuchli yomg‘ir",
    "thunderstorm with light rain": "momaqaldiroq va yengil yomg‘ir",
    "thunderstorm with drizzle": "momaqaldiroq va mayda yomg‘ir",
    "thunderstorm with snow": "momaqaldiroq va qor",
    "mist": "tuman",
    "smoke": "tutun",
    "haze": "xira havo",
    "fog": "tuman",
    "sand": "qumli bo‘ron",
    "dust": "chang",
    "ash": "vulkan kul",
    "squall": "kuchli shamol",
    "tornado": "tornado"
}

# ---- Start va Help ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Men AI botman 🤖. /help buyrug‘ini yozib ko‘ring.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - Botni ishga tushirish\n"
        "/help - Yordam\n"
        "/weather - Shaharni tanlab, ob-havo olish\n"
        "/crypto - Kripto tanlab, narxini olish\n"
        "/translate - Tilni tanlab, tarjima qilish\n"
        "/currency - Bugungi valyuta kurslari (CBU)\n"
        "🤖 Boshqa xabar yuborsangiz — Gemini AI javob beradi\n"
    )
    await update.message.reply_text(text)

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
        await query.edit_message_text(f"Xatolik: {str(e)}")

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
        await query.edit_message_text(f"Xatolik: {str(e)}")

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
    if "target_lang" not in context.user_data:
        # agar translate rejimida bo‘lmasa, AI ishlaydi
        await handle_ai_message(update, context)
        return

    lang = context.user_data["target_lang"]
    text = update.message.text
    try:
        translated = GoogleTranslator(source="auto", target=lang).translate(text)
        await update.message.reply_text(f"🔤 Tarjima ({lang}): {translated}")
        del context.user_data["target_lang"]
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

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
        await update.message.reply_text(f"Xatolik: {str(e)}")

# ---- GEMINI AI ----
async def handle_ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_message_time = context.user_data.get("last_message_time", None)
    if last_message_time and datetime.now() < last_message_time + timedelta(seconds=5):
        await update.message.reply_text("⏳ Iltimos, biroz kuting!")
        return

    context.user_data["last_message_time"] = datetime.now()
    user_message = update.message.text

    try:
        response = await asyncio.to_thread(model.generate_content, user_message)
        ai_response = response.text
    except Exception as e:
        ai_response = f"Xatolik: {str(e)}"

    await update.message.reply_text(ai_response)

# ---- MAIN ----
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Buyruqlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("weather", weather_start))
    app.add_handler(CommandHandler("crypto", crypto_start))
    app.add_handler(CommandHandler("translate", translate_start))
    app.add_handler(CommandHandler("currency", currency))

    # Tugma handlerlar
    app.add_handler(CallbackQueryHandler(weather_button, pattern="^weather_"))
    app.add_handler(CallbackQueryHandler(crypto_button, pattern="^crypto_"))
    app.add_handler(CallbackQueryHandler(lang_button, pattern="^lang_"))

    # Matn handler (tarjima yoki AI)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_message))

    # Webhook (Render uchun)
    port = int(os.environ.get("PORT", 8443))
    url_path = TELEGRAM_TOKEN
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{url_path}"

    print("Bot webhook bilan ishga tushmoqda:", webhook_url)

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=url_path,
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
