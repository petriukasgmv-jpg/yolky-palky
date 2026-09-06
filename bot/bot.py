import os
import threading
from flask import Flask
from groq import Groq
import telebot

# ==============================
# НАСТРОЙКИ
# ==============================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError(
        "Необходимо задать TELEGRAM_TOKEN и GROQ_API_KEY!"
    )

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

MODEL_NAME = "openai/gpt-oss-20b"

# ==============================
# БИЗНЕС-СТРАТЕГ
# ==============================

SYSTEM_PROMPT = """
Ты — мой личный ИИ-Бизнес-Стратег.

Твоя главная задача — помогать мне увеличивать реальный доход
и создавать реальные источники заработка.

Главная финансовая цель — достичь дохода 5 000 евро в месяц.

Правила работы:

1. Не предлагай красивые идеи без проверки реалистичности.
2. Анализируй спрос, конкуренцию, вложения, расходы,
   выручку, чистую прибыль, окупаемость и риски.
3. Приоритет — варианты с небольшими начальными вложениями.
4. Если есть несколько вариантов — сравнивай их.
5. Не обещай гарантированный доход.
6. Отделяй факты от предположений.
7. Для актуальной информации используй веб-поиск.
8. Не выдумывай цены, компании, законы и статистику.
9. Если информации недостаточно — скажи, чего не хватает.
10. Помогай принимать конкретные решения.
11. После анализа давай конкретное следующее действие.

Стиль:
- простой;
- понятный;
- прямой;
- практичный;
- без лишней теории;
- суммы указывай в евро.

Ты работаешь как бизнес-партнёр.
"""

# ==============================
# START
# ==============================

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(
        message,
        "Привет! Я Ёлки-палки — твой ИИ-Бизнес-Стратег. 🚀\n\n"
        "Моя главная цель — помочь тебе выйти на €5 000 в месяц.\n\n"
        "Пиши идею, проблему или задачу — будем разбирать её по цифрам."
    )


# ==============================
# СООБЩЕНИЯ
# ==============================

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        user_text = message.text.strip()

        if not user_text:
            return

        response = groq_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            tools=[
                {
                    "type": "browser_search"
                }
            ],
            reasoning_effort="low"
        )

        response_text = response.choices[0].message.content

        if not response_text:
            response_text = "Не удалось получить ответ."

        if len(response_text) <= 4000:
            bot.reply_to(message, response_text)
        else:
            for i in range(0, len(response_text), 4000):
                bot.send_message(
                    message.chat.id,
                    response_text[i:i + 4000]
                )

    except Exception as e:
        print(f"Ошибка: {e}")

        bot.reply_to(
            message,
            f"❌ Ошибка при обращении к ИИ:\n{str(e)}"
        )


# ==============================
# RENDER
# ==============================

app = Flask(__name__)


@app.route("/")
def home():
    return "Yolky Palky Business Strategist is running!"


@app.route("/health")
def health():
    return "OK"


def run_flask():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


# ==============================
# ЗАПУСК
# ==============================

if __name__ == "__main__":

    try:
        bot.delete_webhook()
        print("Webhook удалён")
    except Exception as e:
        print(f"Не удалось удалить webhook: {e}")

    threading.Thread(
        target=run_flask,
        daemon=True
    ).start()

    print("Yolky Palky Business Strategist запущен!")

    bot.infinity_polling(
        skip_pending=True
    )
