import os
import json
import sqlite3
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
)
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext,
    MessageHandler, Filters
)

# === STATIONS O‘QISH ===
with open("stations.json", "r", encoding="utf-8") as f:
    stations = json.load(f)

# === SQLITE (Sevimlilar uchun) ===
conn = sqlite3.connect("favorites.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS favorites (user_id INTEGER, station_id TEXT)")
conn.commit()

# === MENYU FUNKSIYALARI ===
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🇺🇿 O'zbekiston Radiolari", callback_data='country_uzbekistan')],
        [InlineKeyboardButton("🇷🇺 Rossiya Radiolari", callback_data='country_russia')],
        [InlineKeyboardButton("❤️ Sevimlilar", callback_data='favorites')],
        [InlineKeyboardButton("🔍 Qidiruv", callback_data='search')],
    ]
    return InlineKeyboardMarkup(keyboard)

def stations_keyboard(country: str):
    keyboard = []
    for st in stations[country]:
        keyboard.append([InlineKeyboardButton(st["name"], callback_data=f"station_{st['id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Ortga", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)

def station_menu(station, country):
    keyboard = [
        [InlineKeyboardButton("▶️ Tinglash", url=station["stream_url"])],
        [InlineKeyboardButton("❤️ Sevimliga qo'shish", callback_data=f"fav_{station['id']}")],
        [InlineKeyboardButton("⬅️ Ortga", callback_data=f"country_{country}")]
    ]
    return InlineKeyboardMarkup(keyboard)

# === HANDLERLAR ===
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Assalomu alaykum 👋\nRadiolar olamiga xush kelibsiz!",
        reply_markup=main_menu_keyboard()
    )

def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == "country_uzbekistan":
        query.edit_message_text("🇺🇿 O'zbekiston radiostansiyalari:", reply_markup=stations_keyboard("uzbekistan"))

    elif data == "country_russia":
        query.edit_message_text("🇷🇺 Rossiya radiostansiyalari:", reply_markup=stations_keyboard("russia"))

    elif data.startswith("station_"):
        st_id = data.replace("station_", "")
        for country, st_list in stations.items():
            for st in st_list:
                if st["id"] == st_id:
                    query.edit_message_media(
                        InputMediaPhoto(media=st["logo"], caption=f"Siz *{st['name']}* radiosini tanladingiz.", parse_mode="Markdown"),
                        reply_markup=station_menu(st, country)
                    )

    elif data.startswith("fav_"):
        st_id = data.replace("fav_", "")
        user_id = query.from_user.id
        cur.execute("INSERT INTO favorites (user_id, station_id) VALUES (?, ?)", (user_id, st_id))
        conn.commit()
        query.answer("✅ Sevimlilarga qo'shildi!", show_alert=True)

    elif data == "favorites":
        user_id = query.from_user.id
        cur.execute("SELECT station_id FROM favorites WHERE user_id=?", (user_id,))
        favs = [row[0] for row in cur.fetchall()]
        if not favs:
            query.edit_message_text("❌ Sizda sevimlilar yo‘q.", reply_markup=main_menu_keyboard())
        else:
            keyboard = []
            for country, st_list in stations.items():
                for st in st_list:
                    if st["id"] in favs:
                        keyboard.append([InlineKeyboardButton(st["name"], callback_data=f"station_{st['id']}")])
            keyboard.append([InlineKeyboardButton("⬅️ Ortga", callback_data="back_main")])
            query.edit_message_text("❤️ Sevimlilar ro‘yxati:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "search":
        query.edit_message_text("🔍 Qidiruv uchun radio nomini yuboring:")
        context.user_data["search_mode"] = True

    elif data == "back_main":
        query.edit_message_text("Asosiy menyu:", reply_markup=main_menu_keyboard())
        context.user_data["search_mode"] = False

def search_handler(update: Update, context: CallbackContext):
    if not context.user_data.get("search_mode"):
        return

    text = update.message.text.lower()
    results = []
    for country, st_list in stations.items():
        for st in st_list:
            if text in st["name"].lower():
                results.append(st)

    if not results:
        update.message.reply_text("❌ Hech narsa topilmadi. Qayta urinib ko‘ring.")
    else:
        keyboard = [
            [InlineKeyboardButton(st["name"], callback_data=f"station_{st['id']}")] for st in results
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Ortga", callback_data="back_main")])
        update.message.reply_text("🔎 Qidiruv natijalari:", reply_markup=InlineKeyboardMarkup(keyboard))

# === MAIN ===
def main():
    TOKEN = os.getenv("BOT_TOKEN")  # ✅ Render’da environment variable orqali olinadi
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN o‘rnatilmagan. Iltimos, Render’da environment variable sifatida qo‘shing.")

    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_callback))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, search_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
