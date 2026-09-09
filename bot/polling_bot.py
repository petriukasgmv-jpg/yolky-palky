import os
import threading
import time
import traceback

from dotenv import load_dotenv
from groq import Groq
import telebot

import calc
import groq_utils
import memory
import reminders
import scraper
from prompt import SYSTEM_PROMPT

REMINDEURS_ENABLED = os.getenv("REMINDEURS_ENABLED", "1") == "1"


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
MAX_HISTORY = 10

_GOAL_PATTERN_AMOUNT = {x for x in range(0, 100000, 500)}
import re


def _parse_amount(text):
    m = re.search(r"(\d[\d ]*)", text.replace(",", "").replace(".", ""))
    if not m:
        return None
    return int(m.group(1).replace(" ", ""))


@bot.message_handler(commands=["start"])
def start(message):
    memory.ensure_user(message)
    user_histories[message.from_user.id] = []
    bot.send_message(
        message.chat.id,
        "Привет! Я Ёлки-палки — твой ИИ-Бизнес-Стратег.\n\n"
        "Моя задача — помочь тебе двигаться к цели "
        "€5 000 чистой прибыли в месяц.\n\n"
        "Рассказывай, что хочешь сделать.\n\n"
        "Настроить профиль: /profile, цель: /goal, статус: /status"
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
        "• составлять пошаговый план\n\n"
        "Команды:\n"
        "/goal 5000 — установить цель (€)\n"
        "/profile — посмотреть профиль\n"
        "/profile навыки: сварка, мебель; город: Мюнхен; бюджет: 500 — заполнить\n"
        "/calc цена:250 себест:50 — экономика одной продажи\n"
        "/price наручные часы СССР — актуальные цены на барахолках\n"
        "/status — прогресс к цели\n"
        "/clear — очистить историю"
    )


@bot.message_handler(commands=["clear"])
def clear_command(message):
    user_histories.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "История очищена.")


@bot.message_handler(commands=["goal"])
def goal_command(message):
    user_id = message.from_user.id
    memory.ensure_user(message)
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        amount = _parse_amount(args[1])
        if not amount or amount <= 0:
            bot.send_message(
                message.chat.id,
                "Не понял число. Пример: /goal 5000",
            )
            return
        memory.set_goal(user_id, amount)
        bot.send_message(
            message.chat.id,
            f"🎯 Цель установлена: €{amount:,} чистой прибыли в месяц.",
        )
        return
    u = memory.get_user(user_id)
    if u and u.get("goal_euro"):
        bot.send_message(
            message.chat.id,
            f"Текущая цель: €{u['goal_euro']:,} чистыми/мес.\n"
            "Изменить: /goal <сумма>",
        )
    else:
        bot.send_message(
            message.chat.id,
            "Цель ещё не задана. Задай, например: /goal 5000",
        )


@bot.message_handler(commands=["profile"])
def profile_command(message):
    user_id = message.from_user.id
    memory.ensure_user(message)
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        parsed = memory.parse_profile(args[1])
        if parsed.get("skills"):
            memory.set_skills(user_id, parsed["skills"])
        if parsed.get("city"):
            memory.set_city(user_id, parsed["city"])
        if parsed.get("budget_euro"):
            memory.set_budget(user_id, parsed["budget_euro"])
        if parsed.get("goal_euro"):
            memory.set_goal(user_id, parsed["goal_euro"])
        bot.send_message(
            message.chat.id,
            "✅ Профиль обновлён.\n\n" + memory.format_profile(user_id),
        )
        return
    bot.send_message(
        message.chat.id,
        memory.format_profile(user_id)
        + "\n\nЗаполнить можно так:\n"
        "/profile навыки: сварка, мебель; город: Мюнхен; бюджет: 500",
    )


@bot.message_handler(commands=["status"])
def status_command(message):
    user_id = message.from_user.id
    memory.ensure_user(message)
    bot.send_message(message.chat.id, memory.progress_line(user_id))


@bot.message_handler(commands=["calc"])
def calc_command(message):
    user_id = message.from_user.id
    memory.ensure_user(message)

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(message.chat.id, calc.HELP_TEXT)
        return

    parsed = calc.parse_calc_args(args[1])
    if "price" not in parsed or "cost" not in parsed:
        bot.send_message(
            message.chat.id,
            "Нужны минимум: цена и себестоимость. Пример:\n"
            "/calc цена:250 себест:50",
        )
        return

    user = memory.get_user(user_id)
    goal = parsed.get("goal") or (user or {}).get("goal_euro") or 5000

    result = calc.calculate(
        price=parsed["price"],
        cost=parsed["cost"],
        sales=parsed.get("sales", 1),
        fee=parsed.get("fee", 0),
        shipping=parsed.get("shipping", 0),
        goal=goal,
    )
    if not result:
        bot.send_message(message.chat.id, "Цена должна быть больше 0.")
        return

    text = calc.render_calc(result)
    if not parsed.get("goal") and not (user or {}).get("goal_euro"):
        text += "\n\n💡 Задай цель: /goal 5000"
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["price"])
def price_command(message):
    user_id = message.from_user.id

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(
            message.chat.id,
            "Что ищем? Примеры:\n"
            "/price советские наручные часы\n"
            "/price кожаная куртка 90-х\n"
            "/price бинокль СССР",
        )
        return

    query = args[1]
    bot.send_message(
        message.chat.id,
        f"🔎 Ищу актуальные цены: {query}\n\nПодожди пару секунд...",
    )

    text, err = scraper.search_prices(client, query)
    if err or not text:
        msg = scraper.FALLBACK_HELP + "\n"
        if err:
            msg += f"Ошибка: {err}\n"
        msg += "\n" + scraper.manual_search_links(query)
        bot.send_message(message.chat.id, msg)
        return

    prefix = f"🔎 Цены по запросу: {query}\n\n"
    max_length = 4000
    body = prefix + text
    for i in range(0, len(body), max_length):
        bot.send_message(message.chat.id, body[i:i + max_length])

    bot.send_message(message.chat.id, scraper.manual_search_links(query))


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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(
            profile=memory.profile_blurb(user_id)
        )}
    ]
    messages.extend(history)

    try:
        answer = groq_utils.chat_with_search(
            client,
            MODEL,
            messages=messages,
        )

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


if REMINDEURS_ENABLED:
    threading.Thread(
        target=reminders.daily_reminder_loop,
        args=(bot,),
        daemon=True,
        name="reminders",
    ).start()

print("🚀 Бот работает!")
bot.polling(none_stop=True)