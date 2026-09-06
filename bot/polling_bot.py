import os
import telebot
from groq import Groq
from duckduckgo_search import DDGS

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN)
client = Groq(api_key=GROQ_KEY)

def search_web(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return "Ничего не найдено."
            return "\n\n".join([f"{r['title']}\n{r['body']}\nИсточник: {r['url']}" for r in results])
    except Exception as e:
        return f"Ошибка поиска: {e}"

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    try:
        user_text = message.text.lower()
        if "найди" in user_text or "поищи" in user_text or "погугли" in user_text:
            search_results = search_web(message.text)
            bot.reply_to(message, f"🔍 Результаты поиска:\n\n{search_results}")
        else:
            completion = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": message.text}],
            )
            bot.reply_to(message, completion.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

print("🚀 Бот с интернетом запущен!")
bot.polling(none_stop=True)
