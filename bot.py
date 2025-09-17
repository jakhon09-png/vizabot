import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio

# .env faylini yuklash
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    print("Xato: TELEGRAM_TOKEN yoki GEMINI_API_KEY topilmadi!")
    exit(1)

# Google Gemini sozlamalari
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Handlerlar
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Men webhook orqali ishlayapman 🚀")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_message_time = context.user_data.get('last_message_time', None)
    if last_message_time and datetime.now() < last_message_time + timedelta(seconds=5):
        await update.message.reply_text("Iltimos, biroz kuting!")
        return

    context.user_data['last_message_time'] = datetime.now()
    user_message = update.message.text

    try:
        response = await asyncio.to_thread(model.generate_content, user_message)
        ai_response = response.text
    except Exception as e:
        ai_response = f"Xatolik: {str(e)}"

    await update.message.reply_text(ai_response)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Render webhook sozlamalari
    port = int(os.environ.get("PORT", 8443))
    url_path = TELEGRAM_TOKEN  # xavfsizlik uchun token bilan
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{url_path}"

    print("Bot webhook bilan ishga tushmoqda:", webhook_url)

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=url_path,
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    main()