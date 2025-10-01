import logging
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import os

# --- Токен из переменной окружения ---
API_TOKEN = os.getenv("API_TOKEN")  # Берём токен из переменной окружения
if not API_TOKEN:
    raise ValueError("Не найден токен бота! Убедитесь, что переменная API_TOKEN установлена.")

# --- Инициализация бота и диспетчера ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- ПАМЯТЬ для выбора суммы займа ---
pending_loans = {}  # {user_id: amount}
waiting_complaint = set()  # список юзеров, которые пишут жалобу
waiting_restore = set()  # пользователи, которые согласились вернуть доступ

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
    """Сохраняет контакт в базу: если loan_amount указан — это микрозайм, иначе просто контакт"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, username, phone) VALUES (?, ?, ?)",
                   (user_id, username, phone))
    if loan_amount:
        cursor.execute("INSERT INTO loans (user_id, amount, phone) VALUES (?, ?, ?)",
                       (user_id, loan_amount, phone))
    conn.commit()
    conn.close()


def save_complaint(user_id, username, message):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO complaints (user_id, username, message) VALUES (?, ?, ?)",
                   (user_id, username, message))
    conn.commit()
    conn.close()


# --- КНОПКИ ---
def main_menu():
    keyboard = [
        [types.KeyboardButton(text="Вернуть доступ к аккаунту📱")],
        [types.KeyboardButton(text="Оформить Микрозаймы 💸")],
        [types.KeyboardButton(text="Пожаловаться ⚠️")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def loan_menu():
    keyboard = [
        [types.KeyboardButton(text="2 руб")],
        [types.KeyboardButton(text="349 руб")],
        [types.KeyboardButton(text="15 000 000 000 тенге")],
        [types.KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def contact_button():
    keyboard = [
        [types.KeyboardButton(text="Поделиться номером📱", request_contact=True)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# --- ХЭНДЛЕРЫ ---
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer(
        "Добро пожаловать в МФО КРИЗАЛИС! 👋\n"
        "Оформите займ сегодня - завтра мы разденем вас до костей",
        reply_markup=main_menu()
    )


# --- ПОЛУЧЕНИЕ КОНТАКТА ---
@dp.message(F.contact)
async def contact_handler(message: types.Message):
    if message.contact:
        phone = message.contact.phone_number
        user_id = message.from_user.id
        username = message.from_user.username

        # Контакт для микрозайма
        if user_id in pending_loans:
            amount = pending_loans.pop(user_id)
            save_user_contact(user_id, username, phone, loan_amount=amount)
            await message.answer(f"Спасибо, микрозайм на {amount} руб оформлен ✅", reply_markup=main_menu())
        # Контакт для восстановления доступа
        elif user_id in waiting_restore:
            waiting_restore.remove(user_id)
            save_user_contact(user_id, username, phone)
            await message.answer("Номер получен. Не переживайте, вы под защитой!\n"
                                 "С незнакомых номеров пусть попробуют дозвониться",
                                 reply_markup=main_menu())
        else:
            save_user_contact(user_id, username, phone)
            await message.answer("Номер получен. Не переживайте, вы под защитой!\n"
                                 "С незнакомых номеров пусть попробуют дозвониться",
                                 reply_markup=main_menu())


# --- ВОССТАНОВЛЕНИЕ ДОСТУПА ---
@dp.message(F.text == "Вернуть доступ к аккаунту📱")
async def restore_access(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data="restore_yes")],
        [InlineKeyboardButton(text="Нет", callback_data="restore_no")]
    ])
    await message.answer(
        "Вы хотите вернуть доступ группе КРИЗАЛИС к аккаунту. Вы уверены?",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "restore_yes")
async def restore_yes_callback(callback: types.CallbackQuery):
    waiting_restore.add(callback.from_user.id)
    await callback.message.answer(
        "Оставьте ваш номер телефона, мы обязательно вам перезвоним",
        reply_markup=contact_button()
    )
    await callback.answer()


@dp.callback_query(F.data == "restore_no")
async def restore_no_callback(callback: types.CallbackQuery):
    await callback.message.answer("Спасибо, мы ценим ваш вклад в сопротивление!", reply_markup=main_menu())
    await callback.answer()


# --- МИКРОЗАЙМ ---
@dp.message(F.text == "Оформить Микрозаймы 💸")
async def loan_handler(message: types.Message):
    await message.answer("Выбери сумму микрозайма:", reply_markup=loan_menu())


@dp.message(F.text.in_({"2 руб", "349 руб", "15 000 000 000 тенге"}))
async def choose_amount(message: types.Message):
    amount = int(message.text.split()[0])
    pending_loans[message.from_user.id] = amount
    await message.answer(
        f"Вы выбрали {amount} руб.\n"
        "Оставьте номер телефона:",
        reply_markup=contact_button()
    )


@dp.message(F.text == "⬅️ Назад")
async def back_to_menu(message: types.Message):
    await message.answer("Возврат в главное меню:", reply_markup=main_menu())


# --- ЖАЛОБА ---
@dp.message(F.text == "Пожаловаться ⚠️")
async def complaint_start(message: types.Message):
    waiting_complaint.add(message.from_user.id)
    await message.answer("Вместо займа на психотерапевта можешь написать сюда все, что тебя беспокоит\n"
                         "❗️Жалоба может содержать личную информацию, данные не будут переданы психотерапевту, обещаем",
                         reply_markup=ReplyKeyboardRemove())


@dp.message(F.text)
async def complaint_save(message: types.Message):
    user_id = message.from_user.id
    if user_id in waiting_complaint:
        waiting_complaint.remove(user_id)
        save_complaint(user_id, message.from_user.username, message.text)
        await message.answer("Спасибо, жалоба принята!\n"
                             "Надеемся, что ваш отец не исчез, как у многих пользователей нашего сервиса😊", reply_markup=main_menu())


# --- ЗАПУСК ---
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
