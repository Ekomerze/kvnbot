import json
import random
import threading
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask, request
import os
from dotenv import load_dotenv

# **1️⃣ Flask aplikācija (`flask_app`), NEVIS `app`**
flask_app = Flask(__name__)

# **2️⃣ Ielādē Telegram tokenu**
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен! Проверьте .env файл.")

# Telegram bot
bot_app = Application.builder().token(TOKEN).build()

# Настраиваем webhook
WEBHOOK_URL = "https://kvnbot.onrender.com"

# Подключаемся к базе данных
conn = sqlite3.connect("kvn_quiz.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS scores (user_id INTEGER, score INTEGER)")
conn.commit()

# Загружаем вопросы
json_file_path = "kvn_quiz_questions_full.json"
with open(json_file_path, "r", encoding="utf-8") as file:
    QUESTIONS = json.load(file)

print(f"Общее количество вопросов: {len(QUESTIONS)}")
print("Бот запущен...")


@flask_app.route('/')
def index():
    return "KVN Бот работает!"

@flask_app.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Apstrādā Telegram webhook pieprasījumus"""
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    asyncio.run(bot_app.process_update(update))
    return "OK", 200

json_file_path = "kvn_quiz_questions_full.json"
print(f"Ищу JSON файл: {os.path.abspath(json_file_path)}")
print(f"Файл существует? {os.path.exists(json_file_path)}")

# Загружаем вопросы
with open("kvn_quiz_questions_full.json", "r", encoding="utf-8") as file:
    QUESTIONS = json.load(file)

# Создаем базу данных для хранения результатов игроков
conn = sqlite3.connect("kvn_quiz.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS scores (user_id INTEGER, score INTEGER)")
conn.commit()

# **1. Команда /start**
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    context.user_data["score"] = 0
    context.user_data["question_index"] = 0
    context.user_data["questions"] = random.sample(QUESTIONS, 20)  # Выбираем 20 случайных вопросов
    await update.message.reply_text("Привет! Давай начнем KVN-викторину! У тебя будет 20 вопросов. Поехали! 🎉")

    await send_question(update, context)

print("Вопросы загружены:", len(QUESTIONS))

# **8️⃣ Pievieno Telegram handlerus**
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(start))

# **2. Отправка вопроса с вариантами ответов**
async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data["question_index"]

    if index >= 20:
        await end_quiz(update, context)
        return

    question = context.user_data["questions"][index]
    options = question["options"]
    correct_answer = question["answer"]

    keyboard = [[InlineKeyboardButton(option, callback_data=option)] for option in options]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = None
    if update.message:
        message = await update.message.reply_text(f"❓ {question['question']}", reply_markup=reply_markup)
    elif update.callback_query:
        message = await update.callback_query.message.reply_text(f"❓ {question['question']}", reply_markup=reply_markup)
    
    if message is None:
        return  # Ja ziņa netiek nosūtīta, pārtrauc funkciju

    # Saglabā informāciju lietotāja datos
    context.user_data["correct_answer"] = correct_answer
    context.user_data["question_index"] += 1
    context.user_data["answered"] = False
    context.user_data["timer_active"] = True  # ✅ Pārbaudām, vai taimeris darbojas
    context.user_data["message_id"] = message.message_id

 # ✅ Dinamiskais taimeris (atjauno ik pēc 5 sekundēm)
    async def countdown():
        for i in range(15, 0, -5):  # 15 → 10 → 5 → 0
            await asyncio.sleep(5)
            if not context.user_data.get("timer_active", True):  
                return  # ✅ Ja jau atbildēts, apstājam taimeri
            await message.edit_text(f"⏳ {i}s | {question['question']}", reply_markup=reply_markup)

        # ✅ Ja laiks beidzas, parādām pareizo atbildi un pārejam uz nākamo jautājumu
        if context.user_data.get("timer_active", True):  
            context.user_data["timer_active"] = False
            await message.edit_text(f"⏳ 0s | Время вышло! Правильный ответ: {correct_answer}")
            await asyncio.sleep(2)
            await send_question(update, context)

    # ✅ Запускаем 20-секундный таймер
    async def timeout():
        await asyncio.sleep(20)
        if not context.user_data["answered"]:  # Если игрок не ответил
            await message.reply_text(f"⏳ Время вышло! Правильный ответ: {correct_answer}")
            await send_question(update, context)  # Переходим к следующему вопросу

  # ✅ Saglabājam taimeri, lai vēlāk to varētu apturēt
    context.user_data["timer_task"] = asyncio.create_task(countdown())

# **3. Обработка ответов**
async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_answer = query.data
    correct_answer = context.user_data["correct_answer"]

    # ✅ Apturam taimeri, jo lietotājs jau atbildēja
    context.user_data["answered"] = True
    context.user_data["timer_active"] = False  
    if "timer_task" in context.user_data:
        context.user_data["timer_task"].cancel()  # ✅ Apturam skaitīšanu

    # ✅ Parādām, vai atbilde bija pareiza
    if user_answer == correct_answer:
        context.user_data["score"] += 1
        await query.answer("✅ Правильно!")
        await query.message.edit_text(f"🎉 ✅ Правильный ответ: {correct_answer}")
    else:
        await query.answer("❌ Неправильно!")
        await query.message.edit_text(f"❌ Неправильно! Правильный ответ: {correct_answer}")

    # ✅ Pēc atbildes īsa pauze un nākamais jautājums
    await asyncio.sleep(2)
    await send_question(update, context)

# **4. Завершение игры и сохранение результата**
async def end_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ Pareizi iegūstam chat_id neatkarīgi no tā, vai tiek izsaukts no /start vai callback_query
    if update.message:
        chat_id = update.message.chat_id
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
    else:
        return  # Ja chat_id nevar atrast, pārtraucam funkciju

    score = context.user_data["score"]

    cursor.execute("INSERT INTO scores (user_id, score) VALUES (?, ?)", (chat_id, score))
    conn.commit()

    leaderboard = get_leaderboard()
    await update.callback_query.message.reply_text(
        f"🏁 Игра окончена! Твой результат: {score}/20\n\n🏆 Топ игроков:\n{leaderboard}"
    )

# **5. Таблица лидеров**
def get_leaderboard():
    cursor.execute("SELECT user_id, score FROM scores ORDER BY score DESC LIMIT 5")
    results = cursor.fetchall()
    return "\n".join([f"{i+1}. {res[0]} - {res[1]} очков" for i, res in enumerate(results)])

# **Добавляем обработчики команд**
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(answer))

print(f"Общее количество вопросов: {len(QUESTIONS)}")
print("Бот запущен...")

# **Запускаем бота**

app = Application.builder().token(TOKEN).build()

async def set_webhook():
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}/telegram")

if __name__ == "__main__":
    threading.Thread(target=lambda: asyncio.run(set_webhook())).start()
    
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

