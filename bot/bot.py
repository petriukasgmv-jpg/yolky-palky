
import os
import telebot
from groq import Groq
from flask import Flask, request

TOKEN = os.getenv("TELEBOT_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    try:
        completion = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": message.text}]
        )
        bot.reply_to(message, completion.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '', 200

@app.route('/')
def index():
    return 'Bot is running!', 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
