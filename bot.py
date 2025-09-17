from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
import os
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta

# .env faylini yuklash
load_dotenv()

# Environment Variables dan o'qish
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    print("Xato: TELEGRAM_TOKEN yoki GEMINI_API_KEY topilmadi!")
    exit(1)

# Google Gemini sozlamalari
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Men Google Gemini AI bilan ishlaydigan botman. Savollaringizni yozing!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    last_message_time = context.user_data.get('last_message_time', None)
    
    if last_message_time and datetime.now() < last_message_time + timedelta(seconds=20):
        await update.message.reply_text("Iltimos, 20 soniya kuting!")
        return
    
    context.user_data['last_message_time'] = datetime.now()
    user_message = update.message.text
    
    try:
        time.sleep(15)
        response = model.generate_content(user_message)
        ai_response = response.text
    except Exception as e:
        ai_response = f"Xatolik: {str(e)}"
    
    await update.message.reply_text(ai_response)

def main():
    try:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        print("Bot ishga tushdi...")
        app.run_polling()
    except Exception as e:
        print(f"Botni ishga tushirishda xato: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()