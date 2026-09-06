import os
import threading
from flask import Flask
from groq import Groq
import telebot

# Получаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Необходимо задать TELEGRAM_TOKEN и GROQ_API_KEY в переменной окружения!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Актуальная рабочая модель (старые llama-3.3 и llama-3.1 больше не работают)
MODEL_NAME = "openai/gpt-oss-20b"   # быстрая и дешёвая
# MODEL_NAME = "openai/gpt-oss-120b"  # более умная (можно попробовать потом)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я ИИ-ассистент на базе Groq. Напиши мне что-нибудь!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": message.text,
                }
            ],
            model=MODEL_NAME,
        )
        response_text = chat_completion.choices[0].message.content
        bot.reply_to(message, response_text)

    except Exception as e:
        error_msg = f"❌ Ошибка при обращении к Groq:\n{str(e)}"
        bot.reply_to(message, error_msg)


# === Заглушка порта для Render Web Service ===
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =============================================

if __name__ == "__main__":
    # Удаляем возможный старый webhook (на всякий случай)
    try:
        bot.delete_webhook()
        print("Webhook удалён")
    except Exception as e:
        print(f"Не удалось удалить webhook: {e}")

    # Запускаем Flask в фоне, чтобы Render видел открытый порт
    threading.Thread(target=run_flask, daemon=True).start()

    print("Бот успешно запущен...")
    bot.infinity_polling(skip_pending=True)
