import json
import sqlite3
import os
import asyncio
import nest_asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# nest_asyncio ni qo'llash, Render muhitida event loop muammolarini hal qilish uchun
nest_asyncio.apply()

# Ma'lumotlar bazasini sozlash (sevimlilar uchun)
conn = sqlite3.connect('favorites.db')
conn.execute('''CREATE TABLE IF NOT EXISTS favorites
             (user_id INTEGER, station_id TEXT)''')
conn.commit()

# stations.json faylini yuklash
with open('stations.json', 'r', encoding='utf-8') as f:
    stations = json.load(f)

# Boshlang'ich menyu tugmalari
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🇺🇿 O'zbekiston Radiolari", callback_data='country_uzbekistan')],
        [InlineKeyboardButton("🇷🇺 Rossiya Radiolari", callback_data='country_russia')],
        [InlineKeyboardButton("❤️ Sevimlilar", callback_data='favorites')],
        [InlineKeyboardButton("🔍 Qidiruv", callback_data='search')],
    ]
    return InlineKeyboardMarkup(keyboard)

# Stansiyalar ro'yxati
def stations_keyboard(country):
    keyboard = []
    for st in stations.get(country, []):
        keyboard.append([InlineKeyboardButton(st['name'], callback_data=f"station_{st['id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Ortga", callback_data='back_main')])
    return InlineKeyboardMarkup(keyboard)

# Stansiya menyusi
def station_menu(station):
    keyboard = [
        [InlineKeyboardButton("▶️ Tinglash", url=station['stream_url'])],
        [InlineKeyboardButton("❤️ Sevimliga qo'shish", callback_data=f"fav_{station['id']}")],
        [InlineKeyboardButton("⬅️ Ortga", callback_data=f"country_{station['id'].split('_')[0]}")],
    ]
    return InlineKeyboardMarkup(keyboard)

# Sevimlilar ro'yxati
def get_favorites_keyboard(user_id):
    cur = conn.execute('SELECT station_id FROM favorites WHERE user_id=?', (user_id,))
    fav_ids = [row[0] for row in cur.fetchall()]
    
    all_st = stations.get('uzbekistan', []) + stations.get('russia', [])
    fav_st = [s for s in all_st if s['id'] in fav_ids]
    
    keyboard = [[InlineKeyboardButton(s['name'], callback_data=f"station_{s['id']}")] for s in fav_st]
    keyboard.append([InlineKeyboardButton("⬅️ Ortga", callback_data='back_main')])
    return InlineKeyboardMarkup(keyboard)

# /start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Assalomu alaykum! 👋\n\n'
        'Radiolar Olami botiga xush kelibsiz! Marhamat, mamlakatni tanlang:',
        reply_markup=main_menu_keyboard()
    )

# Tugma bosilganda
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if data == 'back_main':
        await query.edit_message_text(
            text="Asosiy menyu:",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if data == 'country_uzbekistan':
        await query.edit_message_text(
            text="🇺🇿 O'zbekiston radiolari:",
            reply_markup=stations_keyboard('uzbekistan')
        )
    
    elif data == 'country_russia':
        await query.edit_message_text(
            text="🇷🇺 Rossiya radiolari:",
            reply_markup=stations_keyboard('russia')
        )
    
    elif data.startswith('station_'):
        station_id = data.replace('station_', '')
        all_st = stations.get('uzbekistan', []) + stations.get('russia', [])
        station = next((s for s in all_st if s['id'] == station_id), None)
        if station:
            text = f"Siz '{station['name']}' radiosini tanladingiz."
            await query.edit_message_text(text=text, reply_markup=station_menu(station))
    
    elif data.startswith('fav_'):
        station_id = data.replace('fav_', '')
        conn.execute('INSERT OR IGNORE INTO favorites (user_id, station_id) VALUES (?, ?)', (user_id, station_id))
        conn.commit()
        await query.answer("✅ Sevimlilaringizga qo'shildi!", show_alert=True)
    
    elif data == 'favorites':
        await query.edit_message_text(
            text="Sevimli radiostansiyalaringiz:",
            reply_markup=get_favorites_keyboard(user_id)
        )
    
    elif data == 'search':
        context.user_data['search_mode'] = True
        await query.edit_message_text(text="Qidiruv so'zini kiriting (masalan, stansiya nomi):")

# Qidiruv uchun matn xabarlarni qayta ishlash
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('search_mode'):
        query = update.message.text.strip()
        context.user_data['search_mode'] = False
        all_st = stations.get('uzbekistan', []) + stations.get('russia', [])
        st_list = [s for s in all_st if query.lower() in s['name'].lower()]
        keyboard = [[InlineKeyboardButton(s['name'], callback_data=f"station_{s['id']}")] for s in st_list]
        keyboard.append([InlineKeyboardButton("⬅️ Ortga", callback_data='back_main')])
        await update.message.reply_text(
            text=f"Qidiruv natijalari '{query}':",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def main():
    # Bot tokenini environment variable'dan olish
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN environment variable not set")
    
    # Application yaratish
    app = Application.builder().token(TOKEN).build()
    
    # Handler'larni qo'shish
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))
    
    # Botni polling rejimida ishga tushirish
    await app.initialize()
    await app.run_polling(allowed_updates=Update.ALL_TYPES)
    await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())