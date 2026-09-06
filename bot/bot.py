import os
import telebot
from groq import Groq
from flask import Flask, request

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("TELEBOT_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN or not GROQ_KEY:
    exit("Ошибка: Переменные окружения TELEBOT_BOT_TOKEN и GROQ_API_KEY не заданы!")

bot = telebot.TeleBot(TOKEN)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

# --- МАРШРУТ ДЛЯ TELEGRAM (WEBHOOK) ---
@app.route('/webhook', methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    
    # Проверяем, есть ли в апдейте текст сообщения
    if update.message and update.message.text:
        user_text = update.message.text
        chat_id = update.message.chat.id
        
        try:
            # Запрос к Groq (используем доступную модель)
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": user_text}]
            )
            reply_text = completion.choices[0].message.content
        except Exception as e:
            reply_text = f"❌ Ошибка при обращении к Groq: {e}"
        
        # Отправляем ответ через telebot
        bot.send_message(chat_id, reply_text)
    
    return '', 200

# --- ГЛАВНАЯ СТРАНИЦА (ДЛЯ ПРОВЕРКИ) ---
@app.route('/')
def index():
    return 'Bot is running!', 200

# --- ЗАПУСК СЕРВЕРА (ОБЯЗАТЕЛЬНО В САМОМ КОНЦЕ) ---
if __name__ == '__main__':
    # Render передает порт через переменную окружения PORT
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
