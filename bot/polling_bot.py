import os
import traceback

from dotenv import load_dotenv
from groq import Groq
import telebot

from prompt import SYSTEM_PROMPT


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set")

MODEL = "openai/gpt-oss-20b"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

user_histories = {}
MAX_HISTORY = 20


@bot.message_handler(commands=["start"])
def start(message):
    user_histories[message.from_user.id] = []
    bot.send_message(
        message.chat.id,
        "Привет! Я Ёлки-палки — твой ИИ-Бизнес-Стратег.\n\n"
        "Моя задача — помочь тебе двигаться к цели "
        "€5 000 чистой прибыли в месяц.\n\n"
        "Рассказывай, что хочешь сделать."
    )


@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "Я могу:\n\n"
        "• анализировать бизнес-идеи\n"
        "• считать прибыль и расходы\n"
        "• сравнивать бизнес-модели\n"
        "• искать актуальные цены и конкурентов в интернете\n"
        "• рассчитывать продажи для €5 000\n"
        "• помогать искать первых клиентов\n"
        "• составлять пошаговый план"
    )


@bot.message_handler(commands=["clear"])
def clear_command(message):
    user_histories.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "История очищена.")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user_text = message.text

    if not user_text:
        return

    if user_id not in user_histories:
        user_histories[user_id] = []

    history = user_histories[user_id]

    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        user_histories[user_id] = history

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[{"type": "browser_search"}],
            tool_choice="required",
            reasoning_effort="low",
            include_reasoning=False,
        )

        answer = completion.choices[0].message.content

        if not answer:
            answer = "Не удалось получить ответ. Попробуй ещё раз."

        history.append({"role": "assistant", "content": answer})

        max_length = 4000
        for i in range(0, len(answer), max_length):
            bot.send_message(message.chat.id, answer[i:i + max_length])

    except Exception:
        traceback.print_exc()
        bot.send_message(
            message.chat.id,
            "Произошла ошибка при обработке запроса.\n\n"
            "Подробности в логах бота."
        )


print("🚀 Бот работает!")
bot.polling(none_stop=True)