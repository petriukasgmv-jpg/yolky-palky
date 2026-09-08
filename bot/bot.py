import os
import threading
import time
import traceback

from dotenv import load_dotenv
from flask import Flask, request
from groq import Groq
import telebot

import moltbook
from prompt import SYSTEM_PROMPT


# =========================
# SETTINGS
# =========================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set")

MODEL = "openai/gpt-oss-20b"

client = Groq(api_key=GROQ_API_KEY)

bot = telebot.TeleBot(
    TELEGRAM_BOT_TOKEN,
    threaded=False
)


# =========================
# MOLTBOOK SETTINGS
# =========================

MOLTBOOK_ENABLED = os.getenv("MOLTBOOK_ENABLED", "1") == "1"
MOLTBOOK_AGENT_NAME = os.getenv("MOLTBOOK_AGENT_NAME", "yolky-palky-biz")
MOLTBOOK_CHECK_INTERVAL = int(os.getenv("MOLTBOOK_CHECK_INTERVAL", "1800"))
MOLTBOOK_POST_INTERVAL = int(os.getenv("MOLTBOOK_POST_INTERVAL", "7200"))

_last_moltbook_post_at = [0.0]


def _moltbook_post_update():
    """Generate a business insight with Groq and publish it to Moltbook."""
    global _last_moltbook_post_at
    if time.time() - _last_moltbook_post_at[0] < MOLTBOOK_POST_INTERVAL:
        return None

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты — ИИ бизнес-стратег. Напиши короткий полезный пост "
                        "для соцсети ИИ-агентов на русском и английском о том, "
                        "как проверить бизнес-идею с минимальными вложениями. "
                        "Дай один конкретный совет и короткий пример расчёта. "
                        "Без воды, 3-5 предложений."
                    ),
                },
                {"role": "user", "content": "Составь пост."},
            ],
            tools=[{"type": "browser_search"}],
            tool_choice="required",
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=600,
        )
        content = completion.choices[0].message.content
        if not content:
            return None
        title = "Business Idea Test 💡 — how to check an idea with minimum money"
        ok, msg = moltbook.post(title, content[:39000])
        if ok:
            _last_moltbook_post_at[0] = time.time()
            print("=== MOLTBOOK POSTED ===", flush=True)
            print(msg, flush=True)
        else:
            print("=== MOLTBOOK POST FAILED ===", flush=True)
            print(msg, flush=True)
        return ok
    except Exception:
        print("=== MOLTBOOK POST GEN ERROR ===", flush=True)
        traceback.print_exc()
        return None


def moltbook_heartbeat_loop():
    """Registered agent checks in and posts periodically to Moltbook."""
    while True:
        try:
            status = moltbook.get_status()
            if isinstance(status, dict) and status.get("status") == "claimed":
                summary = moltbook.heartbeat()
                print("=== MOLTBOOK HEARTBEAT ===", flush=True)
                print(summary, flush=True)
                _moltbook_post_update()
        except Exception:
            print("=== MOLTBOOK HEARTBEAT ERROR ===", flush=True)
            traceback.print_exc()
        time.sleep(MOLTBOOK_CHECK_INTERVAL)


if MOLTBOOK_ENABLED:
    threading.Thread(
        target=moltbook_heartbeat_loop,
        daemon=True,
        name="moltbook-heartbeat",
    ).start()


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
            tool_choice="required",
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
