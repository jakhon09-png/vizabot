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
    ConversationHandler,
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

# ---- Holatlar ----
ASK_CITY, ASK_COIN, ASK_LANG, ASK_TEXT = range(4)

# ---- Start ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Men AI botman 🤖. /help buyrug‘ini yozib ko‘ring.")

# ---- Help (inline tugmalar bilan) ----
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌤 Ob-havo", callback_data="weather")],
        [InlineKeyboardButton("💰 Kripto", callback_data="crypto")],
        [InlineKeyboardButton("🔤 Tarjima", callback_data="translate")],
        [InlineKeyboardButton("📝 Tarix", callback_data="history")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Quyidagi xizmatlardan birini tanlang:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "weather":
        await query.edit_message_text("🌤 Ob-havo uchun: /weather deb yozing.")
    elif query.data == "crypto":
        await query.edit_message_text("💰 Kripto uchun: /crypto deb yozing.")
    elif query.data == "translate":
        await query.edit_message_text("🔤 Tarjima uchun: /translate deb yozing.")
    elif query.data == "history":
        await query.edit_message_text("📝 Tarixni ko‘rish uchun: /history buyrug‘ini bosing.")

# ---- Weather ----
async def weather_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌤 Qaysi shahar ob-havosini bilmoqchisiz?")
    return ASK_CITY

async def weather_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=uz"
    try:
        res = requests.get(url).json()
        if res.get("cod") != 200:
            await update.message.reply_text(f"❌ Ob-havo topilmadi: {city}")
            return ConversationHandler.END
        temp = res["main"]["temp"]
        desc = res["weather"][0]["description"]
        await update.message.reply_text(f"🌤 {city} ob-havosi:\n{temp}°C, {desc}")
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")
    return ConversationHandler.END

# ---- Crypto ----
async def crypto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Qaysi kripto valyutani bilmoqchisiz? (masalan: bitcoin)")
    return ASK_COIN

async def crypto_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coin = update.message.text.lower()
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"
    try:
        res = requests.get(url).json()
        if coin not in res:
            await update.message.reply_text(f"❌ Kripto topilmadi: {coin}")
            return ConversationHandler.END
        price = res[coin]["usd"]
        await update.message.reply_text(f"💰 {coin.capitalize()} narxi: ${price}")
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")
    return ConversationHandler.END

# ---- Translate ----
async def translate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔤 Qaysi tilga tarjima qilmoqchisiz? (masalan: en, ru, uz)")
    return ASK_LANG

async def translate_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["target_lang"] = update.message.text
    await update.message.reply_text("✍️ Qaysi matnni tarjima qilmoqchisiz?")
    return ASK_TEXT

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("target_lang", "en")
    text = update.message.text
    try:
        translated = GoogleTranslator(source="auto", target=lang).translate(text)
        await update.message.reply_text(f"🔤 Tarjima ({lang}): {translated}")
    except Exception as e:
        await update.message.reply_text(f"Xatolik: {str(e)}")
    return ConversationHandler.END

# ---- History ----
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history_list = context.user_data.get("history", [])
    if not history_list:
        await update.message.reply_text("📭 Hali hech qanday tarix mavjud emas.")
        return
    msg = "📝 So‘nggi 5 ta savol va javob:\n\n"
    for i, (q, a) in enumerate(history_list[-5:], start=1):
        msg += f"{i}. ❓ {q}\n➡️ {a[:100]}...\n\n"
    await update.message.reply_text(msg)

# ---- AI Chat ----
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

# ---- Cancel ----
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Jarayon bekor qilindi.")
    return ConversationHandler.END

# ---- Main ----
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Conversation handlers
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("weather", weather_start)],
        states={ASK_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, weather_city)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("crypto", crypto_start)],
        states={ASK_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, crypto_coin)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("translate", translate_start)],
        states={
            ASK_LANG: [MessageHandler(filters.TEXT & ~filters.COMMAND, translate_lang)],
            ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, translate_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

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
