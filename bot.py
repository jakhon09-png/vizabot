import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import google.generativeai as genai
import os
import tempfile

logging.basicConfig(level=logging.INFO)

# Render.com Environment Variables
API_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

genai.configure(api_key=GEMINI_API_KEY)

# Gemini modeli
model = genai.GenerativeModel("gemini-1.5-pro")

# Ovozdan matnga o‘tkazish
async def speech_to_text(file_path):
    with open(file_path, "rb") as f:
        response = model.generate_content([f, "Ushbu audio faylni matnga aylantir."])
    return response.text

# Tarjima qilish
def translate_text(text, target_lang):
    prompt = f"Quyidagi matnni {target_lang} tiliga tarjima qil: \n\n{text}"
    response = model.generate_content(prompt)
    return response.text

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    file_id = message.voice.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    downloaded = await bot.download_file(file_path)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio:
        temp_audio.write(downloaded.read())
        temp_path = temp_audio.name

    text = await speech_to_text(temp_path)
    await message.reply(f"📄 Matn: {text}")

    languages = {
        "Inglizcha": "ingliz",
        "Ruscha": "rus",
        "Fransuzcha": "fransuz",
        "Italyancha": "italyan",
        "Xitoycha": "xitoy"
    }

    for name, lang in languages.items():
        translated = translate_text(text, lang)
        await message.reply(f"🌍 {name}:\n{translated}")

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text(message: types.Message):
    text = message.text
    translated = translate_text(text, "o‘zbek")
    await message.reply(f"🇺🇿 O‘zbekcha:\n{translated}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
