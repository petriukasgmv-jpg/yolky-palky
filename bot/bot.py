import os
from groq import Groq
import telebot

# Получаем токены из переменных окружения Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Необходимо задать TELEGRAM_TOKEN и GROQ_API_KEY в переменной окружения!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Ипользуем актуальную модель Groq
MODEL_NAME = "llama-3.3-70b-versatile"  # Можно заменить на "llama-3.1-8b-instant" для высокой скорости

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я ИИ-ассистент на базе Groq. Напиши мне что-нибудь!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        # Отправляем запрос в Groq API
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": message.text,
                }
            ],
            model=MODEL_NAME,
        )
        
        # Получаем ответ
        response_text = chat_completion.choices[0].message.content
        bot.reply_to(message, response_text)

    except Exception as e:
        error_msg = f"❌ Ошибка при обращении к Groq:\n{str(e)}"
        bot.reply_to(message, error_msg)

if __name__ == "__main__":
    # Запуск бота в режиме Polling (для постоянной работы на Render Web Service / Background Worker)
    print("Бот успешно запущен...")
    bot.infinity_polling(skip_pending=True)
