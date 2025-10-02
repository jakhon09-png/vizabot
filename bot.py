from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import whisper
import os
import translators as ts
import logging

# Loglarni sozlash
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Whisper modelini yuklash (tiny modeli Render’ning 512 MB RAM uchun mos)
model = whisper.load_model("tiny")

def start(update, context):
    update.message.reply_text("Salom! Men tarjimon botman. Ovozli xabar yuboring yoki matn kiriting.")

def help_command(update, context):
    update.message.reply_text("Ovozli xabar yoki matn yuboring, men uni ingliz, rus, fransuz, italyan, xitoy va o‘zbek tillariga tarjima qilaman. Tillarni tanlash uchun /translate buyrug‘ini ishlatishingiz mumkin.")

def voice_to_text(file_path):
    try:
        result = model.transcribe(file_path)
        return result["text"]
    except Exception as e:
        logging.error(f"Ovozli xabarni matnga aylantirishda xato: {str(e)}")
        return f"Xatolik: Ovozli xabarni matnga aylantirishda muammo: {str(e)}"

def translate_text(text, dest_lang):
    try:
        return ts.translate_text(text, to_language=dest_lang)
    except Exception as e:
        logging.error(f"Tarjimada xato: {str(e)}")
        return f"Xatolik: Tarjimada muammo: {str(e)}"

def handle_voice(update, context):
    try:
        update.message.reply_text("Iltimos, aniq va ravon gapiring.")
        voice_file = update.message.voice.get_file()
        voice_file.download("voice.ogg")
        text = voice_to_text("voice.ogg")
        update.message.reply_text(f"Ovozli xabar matni: {text}")
        context.user_data['last_text'] = text
        os.remove("voice.ogg")  # Vaqtinchalik faylni o‘chirish
    except Exception as e:
        logging.error(f"Ovozli xabarni qayta ishlashda xato: {str(e)}")
        update.message.reply_text(f"Xatolik: {str(e)}")

def handle_text(update, context):
    text = update.message.text or context.user_data.get('last_text', 'Salom')
    langs = ['en', 'ru', 'fr', 'it', 'zh', 'uz']
    translations = {lang: translate_text(text, lang) for lang in langs}
    response = "\n".join([f"{lang.upper()}: {trans}" for lang, trans in translations.items()])
    update.message.reply_text(response)

def language_selection(update, context):
    keyboard = [
        [InlineKeyboardButton("Ingliz", callback_data='en'),
         InlineKeyboardButton("Rus", callback_data='ru')],
        [InlineKeyboardButton("Fransuz", callback_data='fr'),
         InlineKeyboardButton("Italya", callback_data='it')],
        [InlineKeyboardButton("Xitoy", callback_data='zh'),
         InlineKeyboardButton("O‘zbek", callback_data='uz')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Qaysi tilga tarjima qilmoqchisiz?", reply_markup=reply_markup)

def button(update, context):
    query = update.callback_query
    lang = query.data
    text = context.user_data.get('last_text', 'Salom')
    translation = translate_text(text, lang)
    query.message.reply_text(f"{lang.upper()}: {translation}")

def main():
    updater = Updater("YOUR_BOT_TOKEN", use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("translate", language_selection))
    dp.add_handler(MessageHandler(Filters.voice, handle_voice))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dp.add_handler(CallbackQueryHandler(button))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()