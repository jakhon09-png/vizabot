import json
import sqlite3
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes
from telegram.ext import filters  # Yangi filters moduli

# Ma'lumotlar bazasini sozlash
conn = sqlite3.connect('favorites.db')
conn.execute('''CREATE TABLE IF NOT EXISTS favorites
             (user_id INTEGER, station_id TEXT)''')
conn.commit()

# stations.json faylini yuklash
with open('stations.json', 'r') as f:
    stations = json.load(f)

# Boshlang'ich menyu tugmalari
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🇺🇿 O'zbekiston Radiolari", callback_data='country_uzbekistan_page_0')],
        [InlineKeyboardButton("🇷🇺 Rossiya Radiolari", callback_data='country_russia_page_0')],
        [InlineKeyboardButton("❤️ Sevimlilar", callback_data='favorites')],
        [InlineKeyboardButton("🔍 Qidiruv", callback_data='search')],
    ]
    return InlineKeyboardMarkup(keyboard)

# Stansiyalar ro'yxatini sahifalab chiqarish
def get_stations_keyboard(country, page=0, query=None):
    if query:
        all_st = stations.get('uzbekistan', []) + stations.get('russia', [])
        st_list = [s for s in all_st if query.lower() in s['name'].lower()]
    else:
        st_list = stations.get(country, [])
    
    per_page = 5
    start = page * per_page
    end = start + per_page
    keyboard = [[InlineKeyboardButton(s['name'], callback_data=f"station_{s['id']}")] for s in st_list[start:end]]
    
    nav = []
    if page > 0:
        prev_data = f"search_page_{page-1}_{query}" if query else f"country_{country}_page_{page-1}"
        nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=prev_data))
    if end < len(st_list):
        next_data = f"search_page_{page+1}_{query}" if query else f"country_{country}_page_{page+1}"
        nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=next_data))
    
    if nav:
        keyboard.append(nav)
    
    back_data = 'main_menu' if not query else 'main_menu'
    keyboard.append([InlineKeyboardButton("⬅️ Asosiy menyuga", callback_data=back_data)])
    
    return InlineKeyboardMarkup(keyboard)

# Sevimlilar ro'yxati
def get_favorites_keyboard(user_id, page=0):
    cur = conn.execute('SELECT station_id FROM favorites WHERE user_id=?', (user_id,))
    fav_ids = [row[0] for row in cur.fetchall()]
    
    all_st = stations.get('uzbekistan', []) + stations.get('russia', [])
    fav_st = [s for s in all_st if s['id'] in fav_ids]
    
    per_page = 5
    start = page * per_page
    end = start + per_page
    keyboard = [[InlineKeyboardButton(s['name'], callback_data=f"station_{s['id']}")] for s in fav_st[start:end]]
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"favorites_page_{page-1}"))
    if end < len(fav_st):
        nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"favorites_page_{page+1}"))
    
    if nav:
        keyboard.append(nav)
    
    keyboard.append([InlineKeyboardButton("⬅️ Asosiy menyuga", callback_data='main_menu')])
    
    return InlineKeyboardMarkup(keyboard)

# Stansiya haqida ma'lumot chiqarish
def get_station_menu(station, country):
    keyboard = [
        [InlineKeyboardButton("▶️ Tinglash", url=station['stream_url'])],
        [InlineKeyboardButton("❤️ Sevimliga qo'shish", callback_data=f"add_fav_{station['id']}")],
        [InlineKeyboardButton("⬅️ Ortga", callback_data=f"country_{country}_page_0")],
    ]
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
    
    if data == 'main_menu':
        await query.edit_message_text(
            text="Asosiy menyu:",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if data.startswith('country_'):
        parts = data.split('_')
        country = parts[1]
        page = int(parts[3]) if len(parts) > 3 else 0
        await query.edit_message_text(
            text=f"{country.capitalize()} radiostansiyalari:",
            reply_markup=get_stations_keyboard(country, page)
        )
    
    elif data.startswith('station_'):
        station_id = data.split('_')[1]
        all_st = stations.get('uzbekistan', []) + stations.get('russia', [])
        station = next((s for s in all_st if s['id'] == station_id), None)
        if station:
            country = 'uzbekistan' if station_id.startswith('uz_') else 'russia'
            text = f"Siz '{station['name']}' radiosini tanladingiz."
            if station['logo']:
                media = InputMediaPhoto(media=station['logo'], caption=text)
                await query.edit_message_media(media=media, reply_markup=get_station_menu(station, country))
            else:
                await query.edit_message_text(text=text, reply_markup=get_station_menu(station, country))
    
    elif data.startswith('add_fav_'):
        station_id = data.split('_')[2]
        conn.execute('INSERT OR IGNORE INTO favorites (user_id, station_id) VALUES (?, ?)', (user_id, station_id))
        conn.commit()
        await query.answer("✅ Sevimlilaringizga qo'shildi!", show_alert=True)
    
    elif data == 'favorites':
        await query.edit_message_text(
            text="Sevimli radiostansiyalaringiz:",
            reply_markup=get_favorites_keyboard(user_id)
        )
    
    elif data.startswith('favorites_page_'):
        page = int(data.split('_')[2])
        await query.edit_message_text(
            text="Sevimli radiostansiyalaringiz:",
            reply_markup=get_favorites_keyboard(user_id, page)
        )
    
    elif data == 'search':
        context.user_data['search_mode'] = True
        await query.edit_message_text(text="Qidiruv so'zini kiriting (masalan, stansiya nomi):")

    elif data.startswith('search_page_'):
        parts = data.split('_')
        page = int(parts[2])
        query_str = '_'.join(parts[3:])
        await query.edit_message_text(
            text=f"Qidiruv natijalari '{query_str}':",
            reply_markup=get_stations_keyboard(None, page, query_str)
        )

# Qidiruv uchun matn xabarlarni qayta ishlash
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('search_mode'):
        query = update.message.text.strip()
        context.user_data['search_mode'] = False
        await update.message.reply_text(
            text=f"Qidiruv natijalari '{query}':",
            reply_markup=get_stations_keyboard(None, 0, query)
        )

async def main() -> None:
    # Bot tokenini environment variable'dan olish
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
    
    # Application yaratish
    application = Application.builder().token(TOKEN).build()
    
    # Handler'larni qo'shish
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))  # Filters o'rniga filters.TEXT
    
    # Botni ishga tushirish
    await application.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())