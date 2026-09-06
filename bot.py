import asyncio
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
def init_db():
    conn = sqlite3.connect('sleep_club.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        squad_name TEXT,
        is_active BOOLEAN DEFAULT 1
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sleep_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        sleep_time DATETIME,
        wake_time DATETIME,
        energy_level INTEGER,
        fall_asleep_speed TEXT,
        tags TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    conn.commit()
    conn.close()


# === НАСТРОЙКА БОТА И КЛАВИАТУРЫ ===
TOKEN = "8324939190:AAEDyMoNN9NL_gvYUuom6HNYcMhps94LDaM"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Создаем постоянные кнопки внизу экрана
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌙 Иду спать"), KeyboardButton(text="☀️ Я проснулся")]
    ],
    resize_keyboard=True
)


# === СОСТОЯНИЯ (FSM) ===
class EveningSurvey(StatesGroup):
    delay = State()


class MorningSurvey(StatesGroup):
    delay = State()
    energy = State()
    speed = State()
    tags = State()


# === ЛОГИКА БОТА ===

# 1. Регистрация (Команда /start)
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    conn = sqlite3.connect('sleep_club.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
                   (message.from_user.id, message.from_user.username))
    conn.commit()
    conn.close()

    await message.answer(
        f"Привет, {message.from_user.first_name}! 🌙\n"
        "Добро пожаловать в Ночной клуб ЦУ. Пользуйся кнопками внизу, чтобы трекать свой сон.",
        reply_markup=main_kb
    )


# 2. Вечерний чек-ин (старт)
@dp.message(F.text == "🌙 Иду спать")
async def go_to_sleep_start(message: types.Message, state: FSMContext):
    await state.set_state(EveningSurvey.delay)
    await message.answer(
        "Начинаем цифровой закат? 🌅\n"
        "Напиши число — через сколько минут ты планируешь лечь в кровать.\n\n"
        "(Напиши 0, если ложишься прямо сейчас)"
    )


# 2.1. Вечерний чек-ин (сохранение времени)
@dp.message(EveningSurvey.delay)
async def process_sleep_delay(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, напиши просто число минут (например: 30 или 0).")
        return

    delay_minutes = int(message.text)

    if delay_minutes > 180:
        await message.answer("Слишком большое время подготовки! Напиши реальное число минут (до 180).")
        return

    # Считаем время: текущее + введенные минуты
    sleep_time = datetime.now() + timedelta(minutes=delay_minutes)
    sleep_time_str = sleep_time.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect('sleep_club.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO sleep_logs (user_id, sleep_time) VALUES (?, ?)', (message.from_user.id, sleep_time_str))
    conn.commit()
    conn.close()

    await state.clear()

    if delay_minutes == 0:
        await message.answer("Принято! Спокойной ночи и качественных быстрых фаз! 💤", reply_markup=main_kb)
    else:
        await message.answer(
            f"Супер! Твое время отбоя зафиксировано с учетом {delay_minutes} минут на подготовку.\nУбирай экраны и спокойной ночи! 💤",
            reply_markup=main_kb)


# 3. Утреннее пробуждение (старт анкеты)
@dp.message(F.text == "☀️ Я проснулся")
async def wake_up_start(message: types.Message, state: FSMContext):
    await state.set_state(MorningSurvey.delay)
    await message.answer(
        "Доброе утро! ☀️\n"
        "Сколько минут назад ты проснулся?\n\n"
        "(Напиши 0, если открыл глаза прямо сейчас)"
    )


# 3.1. Утреннее пробуждение (сохранение времени)
@dp.message(MorningSurvey.delay)
async def process_wake_delay(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, напиши просто число минут (например: 15 или 0).")
        return

    delay_minutes = int(message.text)

    if delay_minutes > 180:
        await message.answer("Кажется, ты проснулся очень давно! Напиши число до 180 минут.")
        return

    # Считаем время: текущее - введенные минуты
    wake_time = datetime.now() - timedelta(minutes=delay_minutes)
    wake_time_str = wake_time.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect('sleep_club.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE sleep_logs 
        SET wake_time = ? 
        WHERE user_id = ? AND wake_time IS NULL 
        ORDER BY id DESC LIMIT 1
    ''', (wake_time_str, message.from_user.id))
    conn.commit()
    conn.close()

    await state.set_state(MorningSurvey.energy)
    await message.answer(
        "Время зафиксировано! ⏱\nТеперь оцени свой субъективный уровень бодрости от 1 до 5 (напиши цифру):")


# 4. Шаг анкеты: Энергия
@dp.message(MorningSurvey.energy)
async def process_energy(message: types.Message, state: FSMContext):
    await state.update_data(energy=message.text)
    await state.set_state(MorningSurvey.speed)
    await message.answer("Как быстро ты уснул? (напиши: быстро / средне / долго)")


# 5. Шаг анкеты: Скорость засыпания
@dp.message(MorningSurvey.speed)
async def process_speed(message: types.Message, state: FSMContext):
    await state.update_data(speed=message.text)
    await state.set_state(MorningSurvey.tags)
    await message.answer(
        "Были ли вчера триггеры? Напиши через решетку (например: #кофе_после_14 #алкоголь) или просто напиши 'нет':")


# 6. Шаг анкеты: Теги и сохранение
@dp.message(MorningSurvey.tags)
async def process_tags(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tags = message.text

    conn = sqlite3.connect('sleep_club.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE sleep_logs 
        SET energy_level = ?, fall_asleep_speed = ?, tags = ?
        WHERE user_id = ? 
        ORDER BY id DESC LIMIT 1
    ''', (data['energy'], data['speed'], tags, message.from_user.id))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("Анкета сохранена! Данные успешно загружены. Отличного продуктивного дня! 🚀",
                         reply_markup=main_kb)


# === ФОНОВЫЕ НАПОМИНАНИЯ ===
async def evening_reminder():
    conn = sqlite3.connect('sleep_club.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_active=1")
    users = cursor.fetchall()
    conn.close()

    for row in users:
        try:
            await bot.send_message(row[0],
                                   "🌙 Напоминание: скоро отбой!\nНе забудь запустить цифровой закат и нажать кнопку «Иду спать».")
        except Exception:
            pass


async def morning_reminder():
    conn = sqlite3.connect('sleep_club.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_active=1")
    users = cursor.fetchall()
    conn.close()

    for row in users:
        try:
            await bot.send_message(row[0], "☀️ Доброе утро!\nНе забудь заполнить анкету: нажми «Я проснулся».")
        except Exception:
            pass


# === ЗАПУСК ===
async def main():
    init_db()
    print("Бот успешно запущен! База данных готова.")

    # Настраиваем планировщик задач (время по Москве)
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Ставим вечернее напоминание на 22:30
    scheduler.add_job(evening_reminder, trigger='cron', hour=22, minute=0)

    # Ставим утреннее напоминание на 09:00
    scheduler.add_job(morning_reminder, trigger='cron', hour=9, minute=0)

    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())