import os
import json
import logging
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
from fastapi import FastAPI, Request
import uvicorn

# ====== Налаштування ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # без /webhook
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

MODEL = "llama3-8b-8192"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DATA_FILE = "history.json"

user_languages = {}
user_histories = {}

# ====== FastAPI сервер ======
app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ====== Клавіатура ======
language_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("🇺🇦 Українська"), KeyboardButton("🇷🇺 Русский"), KeyboardButton("🇬🇧 English")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Статистика"), KeyboardButton("📁 Історія")],
        [KeyboardButton("🌐 Обрати мову")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

def get_prompt(user_input, lang):
    return {
        "uk": f"Відповідай українською: {user_input}",
        "ru": f"Отвечай по-русски: {user_input}",
        "en": user_input
    }.get(lang, user_input)

def save_history(user_id, message):
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append(message)
    with open(DATA_FILE, "w") as f:
        json.dump(user_histories, f, ensure_ascii=False)

def load_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

user_histories = load_history()

# ====== Обробники ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_languages[user_id] = "uk"
    await update.message.reply_text("Привіт! Обери мову для спілкування:", reply_markup=language_keyboard)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🇺🇦 Українська":
        user_languages[user_id] = "uk"
        await update.message.reply_text("✅ Мову змінено на українську.")
        return
    elif text == "🇷🇺 Русский":
        user_languages[user_id] = "ru"
        await update.message.reply_text("✅ Язык переключен на русский.")
        return
    elif text == "🇬🇧 English":
        user_languages[user_id] = "en"
        await update.message.reply_text("✅ Language changed to English.")
        return
    elif text == "🌐 Обрати мову":
        await update.message.reply_text("Обери мову:", reply_markup=language_keyboard)
        return

    if user_id == ADMIN_ID:
        if text == "📊 Статистика":
            total_users = len(user_languages)
            await update.message.reply_text(f"👥 Користувачів: {total_users}")
            return
        elif text == "📁 Історія":
            history = user_histories.get(str(user_id), [])
            response = "\n\n".join(history[-10:]) if history else "Історія порожня."
            await update.message.reply_text(response)
            return
        reply_markup = admin_keyboard
    else:
        reply_markup = None

    lang = user_languages.get(user_id, "uk")
    prompt = get_prompt(text, lang)

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        res = requests.post(GROQ_URL, headers=headers, json=data)
        res.raise_for_status()
        answer = res.json()['choices'][0]['message']['content']
    except Exception as e:
        answer = f"❌ Помилка: {e}"

    save_history(str(user_id), f"🟢 {text}\n🔵 {answer}")
    await update.message.reply_text(answer, reply_markup=reply_markup)

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ====== FastAPI webhook ======
@app.post("/webhook")
async def process_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    await telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    print("🚀 Вебхук встановлено.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
