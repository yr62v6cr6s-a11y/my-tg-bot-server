import os
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

# ================= НАСТРОЙКИ БОТА =================
TOKEN = "8717591655:AAFzxqCn6DqANGtkxMYdY_5o1zFOFppTvCg"
ADMIN_IDS = [6794601138, 6689244394, 816417707]
# ==================================================

bot = Bot(token=TOKEN)
dp = Dispatcher()

def init_db():
    conn = sqlite3.connect("giveaway.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            registered_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            joined_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_config(key):
    conn = sqlite3.connect("giveaway.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_config(key, value):
    conn = sqlite3.connect("giveaway.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.username
    display_name = f"@{user_name}" if user_name else message.from_user.full_name
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    conn = sqlite3.connect("giveaway.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, registered_at) VALUES (?, ?, ?)", (user_id, display_name, now_str))
    conn.commit()
    conn.close()

    if is_admin(user_id):
        await message.answer("👋 Привет, Администратор/Модератор!\n\nУправляйте розыгрышами и рассылкой через кнопку 'Розыгрыш 🎁' в углу чата.")
        return

    current_prize = get_config("prize")
    if current_prize is None:
        await message.answer("🎁 В данный момент активных розыгрышений нет. Ждите команду на стриме!")
    else:
        builder = InlineKeyboardBuilder()
        builder.button(text="🙋‍♂️ Участвовать!", callback_data="join_giveaway")
        text = f"🎉 **НОВЫЙ РОЗЫГРЫШ!**\n\n🎁 **Приз:** {current_prize}\n"
        end_time = get_config("time")
        if end_time:
            text += f"⏳ **Осталось:** {end_time}\n"
        text += "\nНажмите на кнопку ниже, чтобы записаться!"
        
        image_url = get_config("image")
        if image_url:
            try:
                await message.answer_photo(photo=image_url, caption=text, reply_markup=builder.as_markup(), parse_mode="Markdown")
                return
            except Exception:
                pass
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "join_giveaway")
async def process_join(callback: types.CallbackQuery):
    if get_config("prize") is None:
        await callback.answer("⚠️ Розыгрыш уже завершен!", show_alert=True)
        return
    user_id = callback.from_user.id
    user_name = callback.from_user.username
    display_name = f"@{user_name}" if user_name else callback.from_user.full_name
    now_str = datetime.now().strftime("%H:%M:%S")
    
    conn = sqlite3.connect("giveaway.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM participants WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO participants (user_id, username, joined_at) VALUES (?, ?, ?)", (user_id, display_name, now_str))
        conn.commit()
        await callback.answer("✅ Вы успешно записались!", show_alert=True)
    else:
        await callback.answer("ℹ️ Вы уже участвуете.", show_alert=True)
    conn.close()

async def handle_get_participants(request):
    headers = {
        "Access-Control-Allow-Origin": "*", 
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }
    request_user_id = int(request.rel_url.query.get("user_id", 0))
    conn = sqlite3.connect("giveaway.db")
    cursor = conn.cursor()
    
    if is_admin(request_user_id):
        cursor.execute("SELECT p.username, p.joined_at, u.registered_at FROM participants p LEFT JOIN users u ON p.user_id = u.user_id")
        users_data = [{"name": r[0], "joined_at": r[1], "reg_at": r[2]} for r in cursor.fetchall()]
    else:
        cursor.execute("SELECT username FROM participants")
        users_data = [{"name": r[0], "joined_at": None, "reg_at": None} for r in cursor.fetchall()]
        
    data = {"prize": get_config("prize"), "image": get_config("image"), "time": get_config("time"), "users": users_data}
    conn.close()
    return web.json_response(data, headers=headers)

async def handle_create_giveaway(request):
    headers = {
        "Access-Control-Allow-Origin": "*", 
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }
    try:
        body = await request.json()
        if not is_admin(int(body.get("user_id", 0))):
            return web.json_response({"success": False, "error": "Нет прав"}, headers=headers)
            
        set_config("prize", body.get("prize"))
        set_config("image", body.get("image"))
        set_config("time", body.get("time"))
        
        conn = sqlite3.connect("giveaway.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM participants")
        conn.commit()
        conn.close()
        return web.json_response({"success": True}, headers=headers)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, headers=headers)

async def run_broadcast(text):
    conn = sqlite3.connect("giveaway.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    user_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
            await asyncio.sleep(0.05)
        except Exception:
            pass

async def handle_broadcast(request):
    headers = {
        "Access-Control-Allow-Origin": "*", 
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }
    try:
        body = await request.json()
        if not is_admin(int(body.get("user_id", 0))):
            return web.json_response({"success": False, "error": "Нет прав"}, headers=headers)
        text = body.get("text", "").strip()
        if not text:
            return web.json_response({"success": False, "error": "Текст пуст"}, headers=headers)
        asyncio.create_task(run_broadcast(text))
        return web.json_response({"success": True}, headers=headers)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, headers=headers)

async def handle_options(request):
    headers = {
        "Access-Control-Allow-Origin": "*", 
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS", 
        "Access-Control-Allow-Headers": "Content-Type"
    }
    return web.Response(headers=headers)

async def main():
    app = web.Application()
    app.router.add_get('/get_participants', handle_get_participants)
    app.router.add_post('/create_giveaway', handle_create_giveaway)
    app.router.add_post('/broadcast', handle_broadcast)
    app.router.add_options('/get_participants', handle_options)
    app.router.add_options('/create_giveaway', handle_options)
    app.router.add_options('/broadcast', handle_options)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
