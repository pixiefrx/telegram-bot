import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.filters import Command

API_TOKEN = "8269631267:AAF5uqkFK10QMpY3BXIFYaG0hENZ243Stwo"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            phone TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(user_id, username, phone):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, username, phone) VALUES (?, ?, ?)",
        (user_id, username, phone)
    )
    conn.commit()
    conn.close()

# --- ХЕНДЛЕР /start ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb_builder = ReplyKeyboardBuilder()
    kb_builder.add(KeyboardButton(text="Поделиться номером 📱", request_contact=True))
    keyboard = kb_builder.as_markup(resize_keyboard=True)
    await message.answer(
        "Привет! Пожалуйста, поделись своим номером телефона, обещаем, мы не будем тебе звонить!",
        reply_markup=keyboard
    )

# --- ХЕНДЛЕР КОНТАКТА ---
@dp.message(lambda message: message.contact is not None)
async def contact_handler(message: types.Message):
    contact = message.contact
    if contact is None or contact.phone_number is None:
        await message.answer("Номер не получен! Пожалуйста, используйте кнопку 📱")
        return

    phone = contact.phone_number
    user_id = message.from_user.id
    username = message.from_user.username or "None"

    # Сохраняем данные в базу
    save_user(user_id, username, phone)
    print(f"[DEBUG] Сохранено: {phone}, ID: {user_id}, username: {username}")

    await message.answer(f"Спасибо! Ваш номер сохранён ✅")

# --- ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    dp.run_polling(bot)
