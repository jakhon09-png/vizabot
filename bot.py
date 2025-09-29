import os
import asyncio
import nest_asyncio
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# nest_asyncio ni qo'llash
nest_asyncio.apply()

# API kalitlari
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Spotify token olish
def get_spotify_token():
    url = "https://accounts.spotify.com/api/token"
    headers = {"Authorization": f"Basic {requests.auth._basic_auth_str(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)}"}
    data = {"grant_type": "client_credentials"}
    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json()["access_token"]
    return None

# Spotify qidirish
async def search_spotify(query):
    token = get_spotify_token()
    if not token:
        return "Spotify API kaliti noto'g'ri. Iltimos, sozlang."
    url = f"https://api.spotify.com/v1/search?q={query}&type=track&limit=5"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        tracks = data.get('tracks', {}).get('items', [])
        if tracks:
            text = "🎵 **Natijalar**:\n"
            for track in tracks:
                artist = track['artists'][0]['name']
                name = track['name']
                preview = track['preview_url'] or "Preview yo'q"
                text += f"**{name}** - {artist}\n[Preview]({preview})\n\n"
            return text
        return "Hech narsa topilmadi."
    return "Qidirishda xato yuz berdi."

# Boshlang'ich menyu
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎵 Nom bo'yicha qidirish", callback_data='search_music')],
    ]
    return InlineKeyboardMarkup(keyboard)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Assalomu alaykum! 👋\n\n'
        'Spotify orqali musiqa qidirish botiga xush kelibsiz! Musiqa nomini kiriting:',
        reply_markup=main_menu_keyboard()
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'search_music':
        context.user_data['spotify_search'] = True
        await query.edit_message_text("Musiqa nomini kiriting (masalan, 'Xamdam Sobirov - Malohat'):")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    
    if text and context.user_data.get('spotify_search'):
        context.user_data['spotify_search'] = False
        result = await search_spotify(text)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text("Yana qidirish uchun /start", reply_markup=main_menu_keyboard())

async def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN sozlanmagan")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    await app.initialize()
    await app.run_polling(allowed_updates=Update.ALL_TYPES)
    await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())