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

# .env faylini yuklash
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")  # OpenWeather API key

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    print("Xato: TELEGRAM_TOKEN yoki GEMINI_API_KEY topilmadi!")
    exit(1)

# Google Gemini sozlamalari
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ---- Komandalar ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Men AI botman 🤖. /help buyrug‘ini yozib ko‘ring.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌤 Ob-havo", callback_data="weather")],
        [InlineKeyboardButton("💰 Kripto", callback_data="crypto")],
        [InlineKeyboardButton("🔤 Tarjima", callback_data="translate")],
        [InlineKeyboardButton("📝 Tarix", callback_data="history")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Quyidagi xizmatlardan birini tanlang:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "weather":
        await query.edit_message_text("🌤 Ob-havo uchun: `/weather <shahar>` yozing.")
    elif query.data == "crypto":
        await query.edit_message_text("💰 Kripto uchun: `/crypto <coin>` yozing.")
    elif query.data == "translate":
        await query.edit_message_text("🔤 Tarjima uchun: `/translate <til_kodi> <matn>` yozing.")
    elif query.data == "history":
        await query.edit_message_text("📝 Tarixni ko‘rish uchun: `/history` buyrug‘ini bosing.")

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not WEATHER_API_KEY:
        await update.message.reply_text("Xatolik: WEATHER_API_KEY topilmadi!")
        return

    if not context.args:
        await update.message.reply_text("Iltimos, shahar nomini kiriting. Masalan: /weather Tashkent")
        return

    city = " ".join(context.args)
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=uz"

    try:
        res = requests.get(url).json()
        if res.get("cod") != 200:
            await update.message.reply_text(f"Ob-havo topilmadi: {city}")
            return

        temp = res["main"]["temp"]
        desc = res["weather"][0]["description"]
        await update.message.reply_text(f"🌤 {city} ob-havosi:\n{temp}°C, {desc}")
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

async def crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Iltimos, coin nomini kiriting. Masalan: /crypto bitcoin")
        return

    coin = context.args[0].lower()
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"

    try:
        res = requests.get(url).json()
        if coin not in res:
            await update.message.reply_text(f"❌ Kripto topilmadi: {coin}")
            return

        price = res[coin]["usd"]
        await update.message.reply_text(f"💰 {coin.capitalize()} narxi: ${price}")
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Iltimos, til kodini va matnni kiriting. Masalan: /translate en Salom")
        return

    lang = context.args[0]
    text = " ".join(context.args[1:])

    try:
        translated = GoogleTranslator(source="auto", target=lang).translate(text)
        await update.message.reply_text(f"🔤 Tarjima: {translated}")
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history_list = context.user_data.get("history", [])
    if not history_list:
        await update.message.reply_text("📭 Hali hech qanday tarix mavjud emas.")
        return

    msg = "📝 So‘nggi 5 ta savol va javob:\n\n"
    for i, (q, a) in enumerate(history_list[-5:], start=1):
        msg += f"{i}. ❓ {q}\n➡️ {a[:100]}...\n\n"
    await update.message.reply_text(msg)

# ---- Asosiy AI chat handler ----
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_message_time = context.user_data.get("last_message_time", None)
    if last_message_time and datetime.now() < last_message_time + timedelta(seconds=5):
        await update.message.reply_text("Iltimos, biroz kuting!")
        return

    context.user_data["last_message_time"] = datetime.now()
    user_message = update.message.text

    try:
        response = await asyncio.to_thread(model.generate_content, user_message)
        ai_response = response.text
    except Exception as e:
        ai_response = f"Xatolik: {str(e)}"

    history_list = context.user_data.get("history", [])
    history_list.append((user_message, ai_response))
    context.user_data["history"] = history_list[-10:]

    await update.message.reply_text(ai_response)

# ---- Asosiy funksiya ----
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("crypto", crypto))
    app.add_handler(CommandHandler("translate", translate))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

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
