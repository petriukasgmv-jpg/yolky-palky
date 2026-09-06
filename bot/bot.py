import os
import traceback

from flask import Flask, request
from groq import Groq
import telebot


# =========================
# SETTINGS
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set")

MODEL = "openai/gpt-oss-20b"

client = Groq(api_key=GROQ_API_KEY)

bot = telebot.TeleBot(
    TELEGRAM_TOKEN,
    threaded=False
)


# =========================
# WEBHOOK
# =========================

RENDER_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    "https://yolky-palky-bot-1.onrender.com"
)

WEBHOOK_PATH = "/telegram-webhook"

WEBHOOK_URL = (
    RENDER_URL.rstrip("/")
    + WEBHOOK_PATH
)


# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = """
Ты — мой личный ИИ «Бизнес-Стратег» и Бизнес-Аудитор.

Твоя главная задача — помогать мне создавать реальные источники дохода
и выйти минимум на €5 000 ЧИСТОЙ прибыли в месяц
с минимальными первоначальными вложениями.

МОИ ИСХОДНЫЕ ДАННЫЕ:

- Я умею работать сварщиком.
- Я умею изготавливать мебель.
- Я умею шить.
- Большого стартового капитала у меня нет.
- Цель: €5 000 чистыми в месяц.

ГЛАВНОЕ ПРАВИЛО:

НЕ превращай разговор в анкету.

Если каких-то данных не хватает:
- сначала самостоятельно сделай максимально полезный анализ;
- используй разумные сценарии;
- явно укажи допущения;
- затем задай максимум 1–2 действительно важных вопроса.

ЕСЛИ Я ГОВОРЮ «ВЫБЕРИ ЗА МЕНЯ»:

Ты обязан самостоятельно:

1. Найти 3 наиболее реалистичных варианта бизнеса.
2. Сравнить их.
3. Посчитать примерную экономику каждого.
4. Определить необходимые продажи/заказы для €5 000 чистыми в месяц.
5. Выбрать ОДИН лучший вариант лично для меня.
6. Объяснить, почему именно его.
7. Дать конкретный первый шаг, который я могу сделать сегодня.

Не перекладывай выбор обратно на меня.

ФОРМАТ АНАЛИЗА:

1. ЦЕЛЬ
€5 000 чистыми в месяц.

2. ТОП-3 ВАРИАНТА

Для каждого:
- что продаём;
- кому продаём;
- стартовые вложения;
- примерная цена продажи;
- себестоимость;
- прибыль с одной продажи;
- сколько продаж нужно в месяц;
- сложность получения первых клиентов;
- основные риски.

3. СРАВНЕНИЕ

Сделай простую таблицу или понятное сравнение.

4. МОЙ ВЫБОР

Напиши:

«Я бы выбрал вариант №X».

Обязательно объясни почему.

5. ПЛАН ДО €5 000

Покажи путь:

€0 → €500 → €1 000 → €2 500 → €5 000.

6. ЧТО СДЕЛАТЬ СЕГОДНЯ

Дай ОДНО конкретное действие, которое реально выполнить сегодня.

ФИНАНСОВЫЕ ПРАВИЛА:

- Все суммы показывай в евро.
- Не выдумывай точные цены, спрос или прибыль.
- Если точных данных нет, обозначай это как «оценка».
- Для актуальных цен, конкурентов, законодательства и спроса используй интернет-поиск.
- Отделяй факты от предположений.
- Не обещай гарантированную прибыль.
- Считай чистую прибыль отдельно от выручки.
- Учитывай материалы, рекламу, доставку, налоги и другие существенные расходы.
- Не путай VAT/IVA с прибылью бизнеса.
- Не путай выручку с чистой прибылью.
- Учитывай стоимость моего труда, если это необходимо для реальной оценки бизнеса.

СТИЛЬ:

Говори прямо, как практический бизнес-партнёр.

Не давай мотивационную воду.

Не задавай пять вопросов подряд.

Не говори «для начала мне нужно узнать...», если уже можно сделать предварительный анализ.

Если информации недостаточно для точного расчёта —
сделай расчёт по разумным сценариям и явно укажи допущения.

Главный принцип:

Меньше разговоров — больше конкретных расчётов,
решений и действий.
"""


# =========================
# MEMORY
# =========================

user_histories = {}

MAX_HISTORY = 20


# =========================
# FLASK
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Yolky Palky AI Business Strategist is running."


@app.route("/health")
def health():
    return "OK"


# =========================
# TELEGRAM WEBHOOK
# =========================
@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():

    print("=== WEBHOOK HIT ===", flush=True)

    try:
        raw_data = request.get_data().decode("utf-8")

        print("=== TELEGRAM DATA ===", flush=True)
        print(raw_data, flush=True)

        update = telebot.types.Update.de_json(raw_data)

        print("=== UPDATE CREATED ===", flush=True)

        # Диагностический прямой тест /start
        if update.message and update.message.text == "/start":

            print("=== DIRECT START HANDLER ===", flush=True)

            user_id = update.message.from_user.id
            user_histories[user_id] = []

            bot.send_message(
                update.message.chat.id,
                "Привет! Я Ёлки-палки — твой ИИ-Бизнес-Стратег.\n\n"
                "Моя задача — помочь тебе выйти на "
                "€5 000 чистой прибыли в месяц.\n\n"
                "Напиши мне любую бизнес-идею."
            )

            print("=== DIRECT START SENT ===", flush=True)

            return "OK", 200

        # Все остальные сообщения передаём обычным обработчикам
        bot.process_new_updates([update])

        print("=== UPDATE PROCESSED ===", flush=True)

        return "OK", 200

    except Exception as e:

        print("=== WEBHOOK ERROR ===", flush=True)
        print(repr(e), flush=True)

        traceback.print_exc()

        return "ERROR", 500


    print("=== WEBHOOK HIT ===", flush=True)

    try:

        raw_data = request.get_data().decode("utf-8")

        print("=== TELEGRAM DATA ===", flush=True)
        print(raw_data, flush=True)

        update = telebot.types.Update.de_json(raw_data)

        print("=== UPDATE CREATED ===", flush=True)

        bot.process_new_updates([update])

        print("=== UPDATE PROCESSED ===", flush=True)

        return "OK", 200

    except Exception as e:

        print("=== WEBHOOK ERROR ===", flush=True)
        print(repr(e), flush=True)

        traceback.print_exc()

        return "ERROR", 500


# =========================
# START
# =========================

@bot.message_handler(commands=["start"])
def start(message):

    user_id = message.from_user.id

    user_histories[user_id] = []

    bot.send_message(
        message.chat.id,
        "Привет! Я Ёлки-палки — твой ИИ-Бизнес-Стратег.\n\n"
        "Моя задача — помочь тебе двигаться к цели "
        "€5 000 чистой прибыли в месяц.\n\n"
        "Я буду анализировать бизнес, считать расходы и прибыль, "
        "сравнивать варианты и искать актуальную информацию.\n\n"
        "Рассказывай, что хочешь сделать."
    )


# =========================
# HELP
# =========================

@bot.message_handler(commands=["help"])
def help_command(message):

    bot.send_message(
        message.chat.id,
        "Я могу:\n\n"
        "• анализировать бизнес-идеи\n"
        "• считать прибыль и расходы\n"
        "• сравнивать бизнес-модели\n"
        "• искать актуальные цены и конкурентов\n"
        "• рассчитывать продажи для €5 000\n"
        "• помогать искать первых клиентов\n"
        "• составлять пошаговый план"
    )


# =========================
# USER MESSAGES
# =========================

@bot.message_handler(func=lambda message: True)
def handle_message(message):

    user_id = message.from_user.id

    user_text = message.text

    if not user_text:
        return

    print("=== USER MESSAGE ===", flush=True)
    print(user_text, flush=True)

    if user_id not in user_histories:
        user_histories[user_id] = []

    history = user_histories[user_id]

    history.append(
        {
            "role": "user",
            "content": user_text
        }
    )

    if len(history) > MAX_HISTORY:

        history = history[-MAX_HISTORY:]

        user_histories[user_id] = history

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    messages.extend(history)

    try:

        print(
            "=== SENDING REQUEST TO GROQ ===",
            flush=True
        )

        completion = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[
                {
                    "type": "browser_search"
                }
            ],
            reasoning_effort="low",
            include_reasoning=False
        )

        print(
            "=== GROQ RESPONSE RECEIVED ===",
            flush=True
        )

        answer = completion.choices[0].message.content

        if not answer:

            answer = (
                "Не удалось получить ответ. "
                "Попробуй ещё раз."
            )

        print("=== ANSWER ===", flush=True)
        print(answer, flush=True)

        history.append(
            {
                "role": "assistant",
                "content": answer
            }
        )

        max_length = 4000

        for i in range(
            0,
            len(answer),
            max_length
        ):

            bot.send_message(
                message.chat.id,
                answer[i:i + max_length]
            )

        print(
            "=== MESSAGE SENT TO TELEGRAM ===",
            flush=True
        )

    except Exception as e:

        print("=== AI ERROR ===", flush=True)

        print(repr(e), flush=True)

        traceback.print_exc()

        bot.send_message(
            message.chat.id,
            "Произошла ошибка при обработке запроса.\n\n"
            "Техническая ошибка записана в Render Logs."
        )


# =========================
# START SERVER
# =========================

if __name__ == "__main__":

    print(
        "===================================",
        flush=True
    )

    print(
        "Starting Yolky Palky webhook bot...",
        flush=True
    )

    print(
        "Webhook URL:",
        WEBHOOK_URL,
        flush=True
    )

    print(
        "===================================",
        flush=True
    )

    try:

        result = bot.set_webhook(
            url=WEBHOOK_URL
        )

        print(
            "Webhook set:",
            result,
            flush=True
        )

    except Exception as e:

        print(
            "Webhook setup error:",
            repr(e),
            flush=True
        )

        traceback.print_exc()

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
