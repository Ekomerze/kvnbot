import json
import random
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask, request
import os
from dotenv import load_dotenv

# **1️⃣ Flask aplikācija**
flask_app = Flask(__name__)

# **2️⃣ Ielādē Telegram tokenu**
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен! Проверьте .env файл.")

# **3️⃣ Telegram bot inicializācija**
bot_app = Application.builder().token(TOKEN).build()

# **4️⃣ Webhook iestatīšana**
async def set_webhook():
    """Inicializē botu un iestata webhook"""
    await bot_app.initialize()
    await bot_app.bot.set_webhook(f"https://kvnbot.onrender.com/telegram")

# **5️⃣ Flask webhook route**
@flask_app.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Flask endpoint priekš Telegram webhook"""
    update = Update.de_json(request.get_json(force=True), bot_app.bot)

    # ✅ Flask neatbalsta `await`, tāpēc jāizmanto `ensure_sync()`
    return flask_app.ensure_sync(bot_app.process_update)(update), 200

# **6️⃣ Flask test route**
@flask_app.route('/')
def index():
    return "KVN Бот работает!"

# **7️⃣ Datubāzes iestatīšana**
conn = sqlite3.connect("kvn_quiz.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS scores (user_id INTEGER, score INTEGER)")
conn.commit()

# **8️⃣ Ielādē jautājumus no JSON**
json_file_path = "kvn_quiz_questions_full.json"
with open(json_file_path, "r", encoding="utf-8") as file:
    QUESTIONS = json.load(file)

print(f"Общее количество вопросов: {len(QUESTIONS)}")
print("Бот запущен...")

# **9️⃣ Funkcija spēles sākšanai**
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    context.user_data["score"] = 0
    context.user_data["question_index"] = 0
    context.user_data["questions"] = random.sample(QUESTIONS, 20)  # ✅ 20 nejauši izvēlēti jautājumi
    await update.message.reply_text("Привет! Давай начнем KVN-викторину! У тебя будет 20 вопросов. Поехали! 🎉")

    await send_question(update, context)

# **🔟 Pievieno Telegram handlerus**
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(start))

# **1️⃣1️⃣ Funkcija jautājuma nosūtīšanai**
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

    message = await update.message.reply_text(f"❓ {question['question']}", reply_markup=reply_markup)

    context.user_data["correct_answer"] = correct_answer
    context.user_data["question_index"] += 1
    context.user_data["answered"] = False
    context.user_data["timer_task"] = asyncio.create_task(countdown(message, question, context))

async def countdown(message, question, context):
    """Atjauno jautājuma ziņu ik pēc 5 sekundēm"""
    for i in range(15, 0, -5):
        await asyncio.sleep(5)
        if context.user_data["answered"]:
            return
        await message.edit_text(f"⏳ {i}s | {question['question']}")

    if not context.user_data["answered"]:
        context.user_data["answered"] = True
        await message.edit_text(f"⏳ 0s | Время вышло! Правильный ответ: {context.user_data['correct_answer']}")

# **1️⃣2️⃣ Atbildes apstrāde**
async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_answer = query.data
    correct_answer = context.user_data["correct_answer"]

    context.user_data["answered"] = True
    if "timer_task" in context.user_data:
        context.user_data["timer_task"].cancel()

    if user_answer == correct_answer:
        context.user_data["score"] += 1
        await query.answer("✅ Правильно!")
        await query.message.edit_text(f"🎉 ✅ Правильный ответ: {correct_answer}")
    else:
        await query.answer("❌ Неправильно!")
        await query.message.edit_text(f"❌ Неправильно! Правильный ответ: {correct_answer}")

    await asyncio.sleep(2)
    await send_question(update, context)

# **1️⃣3️⃣ Funkcija spēles beigšanai**
async def end_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        chat_id = update.message.chat_id
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
    else:
        return

    score = context.user_data["score"]

    cursor.execute("INSERT INTO scores (user_id, score) VALUES (?, ?)", (chat_id, score))
    conn.commit()

    leaderboard = get_leaderboard()
    await update.callback_query.message.reply_text(
        f"🏁 Игра окончена! Твой результат: {score}/20\n\n🏆 Топ игроков:\n{leaderboard}"
    )

# **1️⃣4️⃣ Līderu tabulas iegūšana**
def get_leaderboard():
    cursor.execute("SELECT user_id, score FROM scores ORDER BY score DESC LIMIT 5")
    results = cursor.fetchall()
    return "\n".join([f"{i+1}. {res[0]} - {res[1]} очков" for i, res in enumerate(results)])

# **1️⃣5️⃣ Pievieno Telegram komandu handlerus**
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(answer))

print(f"Общее количество вопросов: {len(QUESTIONS)}")
print("Бот запущен...")

# **1️⃣6️⃣ Palaist serveri**
def start_app():
    """Izsauc `set_webhook()` pirms Flask palaišanas"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(set_webhook())

    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    start_app()
