import os
import json
import sqlite3
import threading
import telebot
from telebot import types
from flask import Flask

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("BOT_TOKEN", "")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан! Добавь переменную в Railway.")

with open(os.path.join(BASE_DIR, "prayers.json"), "r", encoding="utf-8") as f:
    PRAYERS = json.load(f)

with open(os.path.join(BASE_DIR, "categories.json"), "r", encoding="utf-8") as f:
    CATEGORIES = json.load(f)

DB_PATH = os.path.join(BASE_DIR, "prayer_bot.db")
bot = telebot.TeleBot(TOKEN)
user_search = {}

# === БАЗА ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS favorites (
        user_id INTEGER, prayer_id TEXT, PRIMARY KEY (user_id, prayer_id))""")
    conn.commit()
    conn.close()

def add_fav(u, p):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO favorites VALUES (?, ?)", (u, p))
    conn.commit()
    conn.close()

def del_fav(u, p):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM favorites WHERE user_id=? AND prayer_id=?", (u, p))
    conn.commit()
    conn.close()

def get_favs(u):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT prayer_id FROM favorites WHERE user_id=?", (u,)).fetchall()
    conn.close()
    return [r[0] for r in rows]

def is_fav(u, p):
    return p in get_favs(u)

# === МЕНЮ ===
def main_menu():
    m = types.InlineKeyboardMarkup()
    for c in CATEGORIES:
        m.add(types.InlineKeyboardButton(text=c["name"], callback_data=f"cat_{c['id']}"))
    m.add(types.InlineKeyboardButton(text="🔍 Поиск", callback_data="search"))
    return m

def prayers_kb(cat, uid, page=0, per=8):
    if cat == "favorites":
        items = [p for p in PRAYERS if p["id"] in get_favs(uid)]
    elif cat == "all":
        items = PRAYERS
    else:
        items = [p for p in PRAYERS if p["category"] == cat]

    m = types.InlineKeyboardMarkup(row_width=1)
    start, end = page * per, page * per + per
    for p in items[start:end]:
        star = "⭐ " if is_fav(uid, p["id"]) else ""
        m.add(types.InlineKeyboardButton(text=f"{star}{p['title']}", callback_data=f"pr_{p['id']}"))

    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(text="◀️", callback_data=f"page_{cat}_{page-1}"))
    if end < len(items):
        nav.append(types.InlineKeyboardButton(text="▶️", callback_data=f"page_{cat}_{page+1}"))
    if nav:
        m.row(*nav)
    m.add(types.InlineKeyboardButton(text="🏠 Меню", callback_data="main"))
    return m

def prayer_detail(pid, uid):
    p = next((x for x in PRAYERS if x["id"] == pid), None)
    if not p:
        return None, None
    text = f"🙏 *{p['title']}*\n\n"
    if p.get("note"):
        text += f"_{p['note']}_\n\n"
    text += f"{p['text']}"
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton(text="⭐ Убрать" if is_fav(uid, pid) else "☆ В избранное", callback_data=f"fav_{pid}"),
        types.InlineKeyboardButton(text="📋 Копировать", callback_data=f"copy_{pid}"))
    m.add(
        types.InlineKeyboardButton(text="◀️ К списку", callback_data=f"cat_{p['category']}"),
        types.InlineKeyboardButton(text="🏠 Меню", callback_data="main"))
    return text, m

# === ХЕНДЛЕРЫ ===
@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        "☦️ *Православный Молитвослов*\n\nВыберите категорию:",
        parse_mode="Markdown", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "main")
def cb_main(call):
    bot.edit_message_text("☦️ *Православный Молитвослов*\n\nВыберите категорию:",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=main_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cb_cat(call):
    cid = call.data[4:]
    cat = next((c for c in CATEGORIES if c["id"] == cid), None)
    if not cat:
        bot.answer_callback_query(call.id, "Не найдено")
        return
    if cid == "favorites" and not get_favs(call.from_user.id):
        bot.edit_message_text("⭐ Избранное пусто.", call.message.chat.id, call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton(text="🏠 Меню", callback_data="main")))
        bot.answer_callback_query(call.id)
        return
    bot.edit_message_text(f"{cat['name']}\n\nВыберите молитву:",
        call.message.chat.id, call.message.message_id,
        reply_markup=prayers_kb(cid, call.from_user.id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("page_"))
def cb_page(call):
    _, cid, pg = call.data.split("_")
    cat = next((c for c in CATEGORIES if c["id"] == cid), None)
    bot.edit_message_text(f"{cat['name'] if cat else 'Молитвы'}\n\nВыберите:",
        call.message.chat.id, call.message.message_id,
        reply_markup=prayers_kb(cid, call.from_user.id, int(pg)))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("pr_"))
def cb_pr(call):
    pid = call.data[3:]
    t, m = prayer_detail(pid, call.from_user.id)
    if not t:
        bot.answer_callback_query(call.id, "Не найдено")
        return
    bot.edit_message_text(t, call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=m)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("fav_"))
def cb_fav(call):
    pid = call.data[4:]
    uid = call.from_user.id
    if is_fav(uid, pid):
        del_fav(uid, pid)
        bot.answer_callback_query(call.id, "Убрано")
    else:
        add_fav(uid, pid)
        bot.answer_callback_query(call.id, "Добавлено ⭐")
    t, m = prayer_detail(pid, uid)
    if t:
        bot.edit_message_text(t, call.message.chat.id, call.message.message_id,
            parse_mode="Markdown", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith("copy_"))
def cb_copy(call):
    pid = call.data[5:]
    p = next((x for x in PRAYERS if x["id"] == pid), None)
    if p:
        bot.send_message(call.message.chat.id, f"{p['title']}\n\n{p['text']}")
    bot.answer_callback_query(call.id, "Отправлено")

@bot.callback_query_handler(func=lambda c: c.data == "search")
def cb_search(call):
    user_search[call.from_user.id] = True
    bot.edit_message_text("🔍 Введите слово для поиска:",
        call.message.chat.id, call.message.message_id,
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(text="🏠 Меню", callback_data="main")))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: user_search.get(m.from_user.id, False))
def do_search(msg):
    q = msg.text.lower().strip()
    user_search[msg.from_user.id] = False
    res = [p for p in PRAYERS if q in p["title"].lower() or q in p["text"].lower()]
    if not res:
        bot.send_message(msg.chat.id, "Ничего не найдено.",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton(text="🏠 Меню", callback_data="main")))
        return
    m = types.InlineKeyboardMarkup(row_width=1)
    for p in res[:20]:
        star = "⭐ " if is_fav(msg.from_user.id, p["id"]) else ""
        m.add(types.InlineKeyboardButton(text=f"{star}{p['title']}", callback_data=f"pr_{p['id']}"))
    m.add(types.InlineKeyboardButton(text="🏠 Меню", callback_data="main"))
    bot.send_message(msg.chat.id, f"🔍 Найдено: {len(res)}", reply_markup=m)

# === FLASK ДЛЯ RAILWAY ===
app = Flask(__name__)

@app.route("/")
def health():
    return "OK"

def run_bot():
    print("☦️ Бот запущен")
    bot.infinity_polling()

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ Порт {port}")
    app.run(host="0.0.0.0", port=port)