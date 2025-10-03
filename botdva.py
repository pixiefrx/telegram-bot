import logging
import sqlite3
import asyncio
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# --- Токен ---
API_TOKEN = os.getenv("API_TOKEN")  # Токен будет храниться в Railway Variables
if not API_TOKEN:
    raise ValueError("❌ Не найден API_TOKEN. Установите переменную окружения в Railway!")

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Инициализация бота ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Временные списки ---
pending_loans = {}       # {user_id: amount}
waiting_complaint = set()
waiting_restore = set()

# --- Инициализация базы ---
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        username TEXT,
        phone TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        phone TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        message TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_user_contact(user_id, username, phone, loan_amount=None):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, phone)
        VALUES (?, ?, ?)
    """, (user_id, username, phone))
    if loan_amount:
        cursor.execute("""
            INSERT INTO loans (user_id, amount, phone) VALUES (?, ?, ?)
        """, (user_id, loan_amount, phone))
    conn.commit()
    conn.close()


def save_complaint(user_id, username, message):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO complaints (user_id, username, message) VALUES (?, ?, ?)
    """, (user_id, username, message))
    conn.commit()
    conn.close()


# --- Кнопки ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Вернуть доступ к аккаунту📱")],
            [types.KeyboardButton(text="Оформить Микрозаймы 💸")],
            [types.KeyboardButton(text="Пожаловаться ⚠️")]
        ],
        resize_keyboard=True
    )


def loan_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="2 руб")],
            [types.KeyboardButton(text="349 руб")],
            [types.KeyboardButton(text="15000000 руб")],
            [types.KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )


def contact_button():
    return ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Поделиться номером📱", request_contact=True)]
        ],
        resize_keyboard=True
    )


# --- Хэндлеры ---
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer(
        "Добро пожаловать в МФО КРИЗАЛИС! 👋\n"
        "Оформите займ сегодня - завтра мы разденем вас до костей",
        reply_markup=main_menu()
    )


# --- Контакт ---
@dp.message(F.contact)
async def contact_handler(message: types.Message):
    phone = message.contact.phone_number
    user_id = message.from_user.id
    username = message.from_user.username

    if user_id in pending_loans:
        amount = pending_loans.pop(user_id)
        save_user_contact(user_id, username, phone, loan_amount=amount)
        await message.answer(f"✅ Микрозайм на {amount} руб оформлен!", reply_markup=main_menu())
    elif user_id in waiting_restore:
        waiting_restore.remove(user_id)
        save_user_contact(user_id, username, phone)
        await message.answer("Доступ восстановлен. Вы под защитой!", reply_markup=main_menu())
    else:
        save_user_contact(user_id, username, phone)
        await message.answer("Номер сохранён!", reply_markup=main_menu())


# --- Восстановление доступа ---
@dp.message(F.text == "Вернуть доступ к аккаунту📱")
async def restore_access(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data="restore_yes")],
        [InlineKeyboardButton(text="Нет", callback_data="restore_no")]
    ])
    await message.answer("Вернуть доступ? Вы уверены?", reply_markup=keyboard)


@dp.callback_query(F.data == "restore_yes")
async def restore_yes_callback(callback: types.CallbackQuery):
    waiting_restore.add(callback.from_user.id)
    await callback.message.answer("Оставьте номер телефона:", reply_markup=contact_button())
    await callback.answer()


@dp.callback_query(F.data == "restore_no")
async def restore_no_callback(callback: types.CallbackQuery):
    await callback.message.answer("Отмена. Спасибо!", reply_markup=main_menu())
    await callback.answer()


# --- Микрозайм ---
@dp.message(F.text == "Оформить Микрозаймы 💸")
async def loan_handler(message: types.Message):
    await message.answer("Выберите сумму:", reply_markup=loan_menu())


@dp.message(F.text.in_({"2 руб", "349 руб", "15000000 руб"}))
async def choose_amount(message: types.Message):
    try:
        amount = int(message.text.split()[0])
    except ValueError:
        await message.answer("Ошибка: неверная сумма")
        return
    pending_loans[message.from_user.id] = amount
    await message.answer(f"Вы выбрали {amount} руб.\nОставьте номер телефона:", reply_markup=contact_button())


@dp.message(F.text == "⬅️ Назад")
async def back_to_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu())


# --- Жалобы ---
@dp.message(F.text == "Пожаловаться ⚠️")
async def complaint_start(message: types.Message):
    waiting_complaint.add(message.from_user.id)
    await message.answer("Опишите жалобу:", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text)
async def complaint_save(message: types.Message):
    user_id = message.from_user.id
    if user_id in waiting_complaint:
        waiting_complaint.remove(user_id)
        save_complaint(user_id, message.from_user.username, message.text)
        await message.answer("Жалоба сохранена ✅", reply_markup=main_menu())


# --- Запуск ---
async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
