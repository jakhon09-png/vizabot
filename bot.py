import os
import json
from flask import Flask, request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

# === Config ===
TOKEN = os.environ.get("BOT_TOKEN")
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")  # Render avtomatik beradi
PORT = int(os.environ.get("PORT", 5000))

# === Flask app ===
app = Flask(__name__)

# === Telegram Application ===
application = Application.builder().token(TOKEN).build()

# Radiostations JSON yuklash
with open("stations.json", "r", encoding="utf-8") as f:
    stations = json.load(f)

# === Keyboardlar ===
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇿 O'zbekiston Radiolari", callback_data="country_uzbekistan")],
        [InlineKeyboardButton("🇷🇺 Rossiya Radiolari", callback_data="country_russia")],
        [InlineKeyboardButton("❤️ Sevimlilar", callback_data="favorites")],
        [InlineKeyboardButton("🔍 Qidiruv", callback_data="search")]
    ])

def stations_keyboard(country):
    keyboard = []
    for st in stations.get(country, []):
        keyboard.append([InlineKeyboardButton(st["name"], callback_data=f"station_{st['id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Ortga", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)

def station_menu(station):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Tinglash", url=station["stream_url"])],
        [InlineKeyboardButton("❤️ Sevimliga qo'shish", callback_data=f"fav_{station['id']}")],
        [InlineKeyboardButton("⬅️ Ortga", callback_data=f"country_{station['id'].split('_')[0]}")]
    ])

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Assalomu alaykum!\nRadiolar Olamiga xush kelibsiz!",
        reply_markup=main_menu_keyboard()
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "country_uzbekistan":
        await query.edit_message_text("🇺🇿 O'zbekiston radiolari:", reply_markup=stations_keyboard("uzbekistan"))

    elif data == "country_russia":
        await query.edit_message_text("🇷🇺 Rossiya radiolari:", reply_markup=stations_keyboard("russia"))

    elif data.startswith("station_"):
        st_id = data.replace("station_", "")
        for country, lst in stations.items():
            for st in lst:
                if st["id"] == st_id:
                    await query.edit_message_media(
                        media=InputMediaPhoto(media=st["logo"], caption=f"Siz '{st['name']}' radiosini tanladingiz."),
                        reply_markup=station_menu(st)
                    )

    elif data == "back_main":
        await query.edit_message_text("🏠 Asosiy menyu:", reply_markup=main_menu_keyboard())

    elif data.startswith("fav_"):
        st_id = data.replace("fav_", "")
        for country, lst in stations.items():
            for st in lst:
                if st["id"] == st_id:
                    await query.answer(f"✅ '{st['name']}' sevimlilarga qo'shildi!", show_alert=True)

# === Handlerlarni ro'yxatdan o'tkazish ===
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_callback))

# === Flask route for webhook ===
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "OK", 200

if __name__ == "__main__":
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{APP_URL}/{TOKEN}"
    )
