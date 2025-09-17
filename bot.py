from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
import time
from datetime import datetime, timedelta

# API kalitlari (to'g'ridan-to'g'ri kiritilgan, .env'siz)
TELEGRAM_TOKEN = "8338692969:AAF8LfY4JLsyOgaiPodJlliBjDPgbBMerPc"
GEMINI_API_KEY = "AIzaSyAz3h--YvkF5DwT0s0jF8_65JIt25tpIvg"

# Google Gemini sozlamalari
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')  # Bepul tarifda yuqori chegaralarga ega model

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Men Google Gemini AI bilan ishlaydigan botman. Savollaringizni yozing!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    last_message_time = context.user_data.get('last_message_time', None)
    
    # 15 soniya chegarasi (quota xatolarini oldini olish uchun)
    if last_message_time and datetime.now() < last_message_time + timedelta(seconds=15):
        await update.message.reply_text("Iltimos, 15 soniya kuting!")
        return
    
    context.user_data['last_message_time'] = datetime.now()
    user_message = update.message.text
    
    try:
        time.sleep(12)  # Retry delay (quota chegaralariga rioya qilish uchun)
        response = model.generate_content(user_message)
        ai_response = response.text
    except Exception as e:
        ai_response = f"Xatolik yuz berdi: {str(e)}"
    
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

if __name__ == "__main__":
    main()