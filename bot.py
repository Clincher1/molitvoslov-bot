"""
Православный молитвослов — Telegram-бот
"""

import os
import json
import sqlite3
import threading
import telebot
from telebot import types
from flask import Flask

# === НАСТРОЙКА ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("BOT_TOKEN", "8612724407:AAEPdnywtqz6SZ4ghVWx4VWA2UnXnHxflg0")

with open(os.path.join(BASE_DIR, "prayers.json"), "r", encoding="utf-8") as f:
    PRAYERS = json.load(f)

with open(os.path.join(BASE_DIR, "categories.json"), "r", encoding="utf-8") as f:
    CATEGORIES = json.load(f)

DB_PATH = os.path.join(BASE_DIR, "prayer_bot.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            prayer_id TEXT,
            PRIMARY KEY (user_id, prayer_id)
        )
    """)
    conn.commit()
    conn.close()


def add_favorite(user_id, prayer_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO favorites (user_id, prayer_id) VALUES (?, ?)", (user_id, prayer_id))
    conn.commit()
    conn.close()


def remove_favorite(user_id, prayer_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorites WHERE user_id = ? AND prayer_id = ?", (user_id, prayer_id))
    conn.commit()
    conn.close()


def get_favorites(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prayer_id FROM favorites WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def is_favorite(user_id, prayer_id):
    return prayer_id in get_favorites(user_id)


# === БОТ ===
bot = telebot.TeleBot(TOKEN)
user_search = {}


def get_main_menu():
    markup = types.InlineKeyboardMarkup()
    for cat in CATEGORIES:
        markup.add(types.InlineKeyboardButton(text=cat["name"], callback_data=f"cat_{cat['id']}"))
    markup.add(types.InlineKeyboardButton(text="🔍 Поиск молитв", callback_data="search"))
    return markup


def get_prayers_keyboard(category_id, user_id, page=0, per_page=8):
    if category_id == "favorites":
        fav_ids = get_favorites(user_id)
        items = [p for p in PRAYERS if p["id"] in fav_ids]
    elif category_id == "all":
        items = PRAYERS
    else:
        items = [p for p in PRAYERS if p["category"] == category_id]

    markup = types.InlineKeyboardMarkup(row_width=1)
    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    for prayer in page_items:
        star = "⭐ " if is_favorite(user_id, prayer["id"]) else ""
        markup.add(types.InlineKeyboardButton(text=f"{star}{prayer['title']}", callback_data=f"pr_{prayer['id']}"))

    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"page_{category_id}_{page - 1}"))
    if end < len(items):
        nav_buttons.append(types.InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"page_{category_id}_{page + 1}"))
    if nav_buttons:
        markup.row(*nav_buttons)

    markup.add(types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="main"))
    return markup


def get_prayer_detail(prayer_id, user_id):
    prayer = next((p for p in PRAYERS if p["id"] == prayer_id), None)
    if not prayer:
        return None, None

    fav = is_favorite(user_id, prayer_id)
    text = f"🙏 *{prayer['title']}*\n\n"
    if prayer.get("note"):
        text += f"_{prayer['note']}_\n\n"
    text += f"```\n{prayer['text']}\n```"

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(text="⭐ В избранном" if fav else "☆ Добавить в избранное", callback_data=f"fav_{prayer_id}"),
        types.InlineKeyboardButton(text="📋 Копировать", callback_data=f"copy_{prayer_id}"),
    )
    markup.add(
        types.InlineKeyboardButton(text="◀️ К списку", callback_data=f"cat_{prayer['category']}"),
        types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="main"),
    )
    return text, markup


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    text = (
        "☦️ *Православный Молитвослов*\n\n"
        "Здесь вы найдёте православные русские молитвы,\n"
        "разделённые по категориям.\n\n"
        "• Выбирайте категорию из меню ниже\n"
        "• Нажимайте на молитву, чтобы прочитать\n"
        "• Добавляйте молитвы в ⭐ Избранное\n"
        "• Используйте 🔍 Поиск для быстрого поиска\n\n"
        "_«Непрестанно молитесь»_ — 1 Фес. 5:17"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=get_main_menu())


@bot.callback_query_handler(func=lambda c: c.data == "main")
def cb_main(call):
    bot.edit_message_text("☦️ *Православный Молитвослов*\n\nВыберите категорию:", call.message.chat.id,
                          call.message.message_id, parse_mode="Markdown", reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cb_category(call):
    cat_id = call.data.replace("cat_", "")
    cat = next((c for c in CATEGORIES if c["id"] == cat_id), None)
    if not cat:
        bot.answer_callback_query(call.id, "Категория не найдена")
        return
    if cat_id == "favorites":
        if len(get_favorites(call.from_user.id)) == 0:
            bot.edit_message_text("⭐ *Избранное*\n\nУ вас пока нет избранных молитв.",
                                  call.message.chat.id, call.message.message_id, parse_mode="Markdown",
                                  reply_markup=types.InlineKeyboardMarkup().add(
                                      types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="main")))
            bot.answer_callback_query(call.id)
            return
    bot.edit_message_text(f"{cat['name']}\n\nВыберите молитву:", call.message.chat.id,
                          call.message.message_id, reply_markup=get_prayers_keyboard(cat_id, call.from_user.id))
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("page_"))
def cb_page(call):
    parts = call.data.split("_")
    cat_id, page = parts[1], int(parts[2])
    cat = next((c for c in CATEGORIES if c["id"] == cat_id), None)
    bot.edit_message_text(f"{cat['name'] if cat else 'Молитвы'}\n\nВыберите молитву:", call.message.chat.id,
                          call.message.message_id, reply_markup=get_prayers_keyboard(cat_id, call.from_user.id, page))
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("pr_"))
def cb_prayer(call):
    prayer_id = call.data.replace("pr_", "")
    text, markup = get_prayer_detail(prayer_id, call.from_user.id)
    if not text:
        bot.answer_callback_query(call.id, "Молитва не найдена")
        return
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("fav_"))
def cb_favorite(call):
    prayer_id = call.data.replace("fav_", "")
    user_id = call.from_user.id
    if is_favorite(user_id, prayer_id):
        remove_favorite(user_id, prayer_id)
        bot.answer_callback_query(call.id, "Убрано из избранного")
    else:
        add_favorite(user_id, prayer_id)
        bot.answer_callback_query(call.id, "Добавлено в избранное ⭐")
    text, markup = get_prayer_detail(prayer_id, user_id)
    if text:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("copy_"))
def cb_copy(call):
    prayer_id = call.data.replace("copy_", "")
    prayer = next((p for p in PRAYERS if p["id"] == prayer_id), None)
    if prayer:
        bot.send_message(call.message.chat.id, f"{prayer['title']}\n\n{prayer['text']}")
    bot.answer_callback_query(call.id, "Текст отправлен")


@bot.callback_query_handler(func=lambda c: c.data == "search")
def cb_search(call):
    user_search[call.from_user.id] = True
    bot.edit_message_text("🔍 *Поиск молитв*\n\nВведите слово или фразу для поиска:", call.message.chat.id,
                          call.message.message_id, parse_mode="Markdown",
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="main")))
    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: user_search.get(m.from_user.id, False))
def handle_search(message):
    query = message.text.lower().strip()
    user_search[message.from_user.id] = False
    results = [p for p in PRAYERS if query in p["title"].lower() or query in p["text"].lower()]
    if not results:
        bot.send_message(message.chat.id, "Ничего не найдено.",
                         reply_markup=types.InlineKeyboardMarkup().add(
                             types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="main")))
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for prayer in results[:20]:
        star = "⭐ " if is_favorite(message.from_user.id, prayer["id"]) else ""
        markup.add(types.InlineKeyboardButton(text=f"{star}{prayer['title']}", callback_data=f"pr_{prayer['id']}"))
    markup.add(types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="main"))
    bot.send_message(message.chat.id, f"🔍 Найдено: {len(results)}\n\nВыберите молитву:", reply_markup=markup)


# === ЗАПУСК ===
app = Flask(__name__)


@app.route('/')
def health():
    return "Bot is running!"


def run_bot():
    print("☦️ Православный молитвослов — бот запущен")
    bot.infinity_polling()


if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ Health-check сервер на порту {port}")
    app.run(host="0.0.0.0", port=port)