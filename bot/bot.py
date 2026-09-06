import os
import telebot
from groq import Groq
from flask import Flask, request
import threading

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    try:
        completion = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": message.text}],
        )
        bot.reply_to(message, completion.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@app.route('/')
def index():
    return "Bot is running!", 200

def run_bot():
    bot.polling(none_stop=True)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
