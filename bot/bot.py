import os
import re
import hmac
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, jsonify, request
import telebot

import memory
from . import groq_utils
import moltbook
import reminders
from prompt import SYSTEM_PROMPT


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set")

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MODEL_FALLBACK = os.getenv("GROQ_MODEL_FALLBACK", "openai/gpt-oss-20b")

client = Groq(api_key=GROQ_API_KEY)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)


def _repair_mojibake(text):
    if not isinstance(text, str) or not text:
        return text
    if not any(marker in text for marker in ("Р", "С", "Ð", "Ñ")):
        return text
    for encoding in ("cp1251", "cp1252", "latin1"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired != text and "" not in repaired:
            return repaired
    return text


_send_message = bot.send_message

def _safe_send_message(chat_id, text, *args, **kwargs):
    return _send_message(chat_id, _repair_mojibake(text), *args, **kwargs)

bot.send_message = _safe_send_message

UPDATE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="telegram-update")
_user_processing_locks = {}
_user_processing_locks_guard = threading.Lock()


def _get_user_processing_lock(user_id):
    with _user_processing_locks_guard:
        return _user_processing_locks.setdefault(user_id, threading.Lock())


# =========================
# MOLTBOOK SETTINGS
# =========================

MOLTBOOK_ENABLED = os.getenv("MOLTBOOK_ENABLED", "0") == "1"
MOLTBOOK_CHECK_INTERVAL = int(os.getenv("MOLTBOOK_CHECK_INTERVAL", "1800"))
MOLTBOOK_POST_INTERVAL = int(os.getenv("MOLTBOOK_POST_INTERVAL", "14400"))

_last_moltbook_post_at = [0.0]


def _solve_moltbook_challenge(challenge_text):
    if not challenge_text:
        return None
    try:
        completion = client.chat.completions.create(
            model=os.getenv("GROQ_AUDIT_MODEL", "openai/gpt-oss-20b"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You solve obfuscated one-line math word problems. "
                        "Deobfuscate it, work out the arithmetic, and reply "
                        "with ONLY the numeric answer, two decimal places, e.g. 50.00"
                    ),
                },
                {"role": "user", "content": challenge_text},
            ],
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=200,
        )
        answer = (completion.choices[0].message.content or "").strip()
        num = re.search(r"-?\d+(?:\.\d+)?", answer)
        return f"{float(num.group()):.2f}" if num else None
    except Exception:
        traceback.print_exc()
        return None


def _moltbook_post_update():
    global _last_moltbook_post_at
    if time.time() - _last_moltbook_post_at[0] < MOLTBOOK_POST_INTERVAL:
        return None

    try:
        topic = _pick_moltbook_topic()
        content = groq_utils.chat_with_search(
            client,
            MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты — ИИ бизнес-стратег. Напиши короткий полезный пост "
                        "для соцсети ИИ-агентов на русском и английском о том: "
                        f"{topic}. "
                        "Дай один конкретный совет и короткий пример расчёта. "
                        "Без воды, 3-5 предложений. В конце добавь строку: "
                        "'🤖 Больше идей и подсчётов: t.me/yolky_palky_bot'"
                    ),
                },
                {"role": "user", "content": "Составь пост."},
            ],
            max_tokens=600,
        )
        if not content:
            return None
        title = "Business Idea Test 💡 — how to check an idea with minimum money"
        ok, msg = moltbook.post(title, content[:39000], solver=_solve_moltbook_challenge)
        if ok:
            _last_moltbook_post_at[0] = time.time()
            print("=== MOLTBOOK POSTED ===", flush=True)
        return ok
    except Exception:
        print("=== MOLTBOOK POST GEN ERROR ===", flush=True)
        traceback.print_exc()
        return None


_MOLTBOOK_TOPICS = [
    "как проверить бизнес-идею с минимальными вложениями",
    "арбитраж советских часов и инструментов: сколько сделок нужно для цели",
    "консалтинг по грантам: как заработать 10-20% от одобренной суммы",
    "расчёт чистой прибыли: комиссии, доставка, налоги против маржи",
    "первые продажи без рекламы: бесплатные каналы и как тестировать спрос",
]


def _pick_moltbook_topic():
    idx = int(time.time() // MOLTBOOK_POST_INTERVAL) % len(_MOLTBOOK_TOPICS)
    return _MOLTBOOK_TOPICS[idx]


def moltbook_heartbeat_loop():
    while True:
        try:
            status = moltbook.get_status()
            if isinstance(status, dict) and status.get("status") == "claimed":
                moltbook.heartbeat()
                _moltbook_post_update()
        except Exception:
            print("=== MOLTBOOK HEARTBEAT ERROR ===", flush=True)
            traceback.print_exc()
        time.sleep(MOLTBOOK_CHECK_INTERVAL)


# =========================
# SELF-REFLECTION
# =========================

def _reflect_user(user_id):
    since = memory.latest_reflection_rowid(user_id)
    messages, last_rowid = memory.messages_since(user_id, since_rowid=since, limit=80)
    if not messages or not last_rowid:
        return None
    conv = "\n".join(f"{m['role']}: {m['content']}" for m in messages)[-12000:]
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты — рефлексивная часть ИИ-бизнес-стратега. По диалогу "
                        "сделай краткую выжимку: какие бизнес-идеи обсуждались, "
                        "расчёты и выводы. 2-4 предложения на русском."
                    ),
                },
                {"role": "user", "content": conv},
            ],
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=700,
        )
        summary = (completion.choices[0].message.content or "").strip()
        if summary:
            memory.save_reflection(user_id, summary, last_rowid)
            return summary
    except Exception:
        traceback.print_exc()
    return None


def self_reflection_loop():
    last_reflect = [None]
    while True:
        try:
            now = time.localtime()
            today = now.tm_yday
            if now.tm_wday == 6 and last_reflect[0] != today:
                last_reflect[0] = today
                for user_id in memory.all_user_ids():
                    _reflect_user(user_id)
        except Exception:
            print("=== REFLECTION LOOP ERROR ===", flush=True)
            traceback.print_exc()
        time.sleep(3600)


if MOLTBOOK_ENABLED:
    threading.Thread(target=moltbook_heartbeat_loop, daemon=True, name="moltbook-heartbeat").start()

if os.getenv("REMINDEURS_ENABLED", "1") == "1":
    threading.Thread(target=reminders.daily_reminder_loop, args=(bot,), daemon=True, name="reminders").start()

if os.getenv("REFLECTIONS_ENABLED", "1") == "1":
    threading.Thread(target=self_reflection_loop, daemon=True, name="self-reflection").start()


# =========================
# WEBHOOK & FLASK
# =========================

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://yolky-palky-bot-1.onrender.com")
WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_URL = RENDER_URL.rstrip("/") + WEBHOOK_PATH
MAX_HISTORY = 10


def clean_telegram_text(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"【[^】]{1,80}】", "", text)
    text = re.sub(r"\[[0-9]+†L[0-9]+(?:-L?[0-9]+)?\]", "", text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = text.replace("```", "")

    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", stripped):
            continue
        if "|" in line:
            line = line.replace("|", " — ")
            line = re.sub(r"\s+—\s+", " — ", line).strip(" —")
        cleaned_lines.append(line.rstrip())

    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines)).strip()


def audit_business_answer(user_text, answer):
    if os.getenv("ANSWER_AUDIT_ENABLED", "1") != "1" or not answer or len(answer) > 14000:
        return answer
    try:
        audit_messages = [
            {
                "role": "system",
                "content": (
                    "Ты — аудитор бизнес-ответов. Проверь арифметику и выводы. "
                    "Верни только исправленный готовый текст ответа на русском."
                ),
            },
            {
                "role": "user",
                "content": f"Запрос:\n{user_text[:2000]}\n\nОтвет:\n{answer[:8000]}",
            },
        ]
        completion = None
        for audit_model in dict.fromkeys((MODEL_FALLBACK, MODEL)):
            try:
                completion = client.chat.completions.create(
                    model=audit_model,
                    messages=audit_messages,
                    reasoning_effort="low",
                    include_reasoning=False,
                    max_completion_tokens=2500,
                )
                break
            except Exception:
                continue
        if completion is None:
            return answer
        return (completion.choices[0].message.content or "").strip() or answer
    except Exception:
        return answer


app = Flask(__name__)


def generate_business_answer(messages):
    last_error = None
    for model in dict.fromkeys((MODEL, MODEL_FALLBACK)):
        try:
            return groq_utils.chat_with_search(client, model, messages=messages)
        except Exception as exc:
            last_error = exc
            print(f"=== MODEL FAILED: {model} ===", repr(exc), flush=True)
    raise last_error or RuntimeError("No AI model is available")


@app.route("/")
def home():
    return "Yolky Palky AI Business Strategist is running."


@app.route("/health")
def health():
    missing = [
        name for name, value in (
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("GROQ_API_KEY", GROQ_API_KEY),
            ("TELEGRAM_WEBHOOK_SECRET", TELEGRAM_WEBHOOK_SECRET),
        ) if not value
    ]
    payload = {
        "status": "ok" if not missing else "degraded",
        "model": MODEL,
        "fallback_model": MODEL_FALLBACK,
        "missing_environment": missing,
        "memory_path": memory.DB_PATH,
        "memory_writable": os.access(memory.DATA_DIR, os.W_OK),
        "version": os.getenv("RENDER_GIT_COMMIT", "unknown"),
    }
    return jsonify(payload), (200 if not missing else 503)


@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    try:
        if not TELEGRAM_WEBHOOK_SECRET:
            return "Webhook secret missing", 500

        received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not received_secret or not hmac.compare_digest(received_secret, TELEGRAM_WEBHOOK_SECRET):
            return "Unauthorized", 403

        raw_data = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(raw_data)

        update_id = getattr(update, "update_id", None)
        if update_id and memory.is_update_processed(update_id):
            return "OK", 200

        UPDATE_EXECUTOR.submit(_process_update, update)
        return "OK", 200
    except Exception as e:
        print("=== WEBHOOK ERROR ===", repr(e), flush=True)
        return "ERROR", 500


def _process_update(update):
    user_id = update.message.from_user.id if update.message and update.message.from_user else None
    lock = _get_user_processing_lock(user_id) if user_id is not None else None
    try:
        if lock is not None:
            lock.acquire()
        if update.message and update.message.text == "/start":
            memory.ensure_user(update.message)
            memory.clear_history(user_id)
            bot.send_message(
                update.message.chat.id,
                "Привет! Я Ёлки-палки — твой ИИ-Бизнес-Стратег.\n\n"
                "Моя задача — помочь тебе выйти на €5 000 чистой прибыли в месяц.\n\n"
                "Напиши мне любую бизнес-идею."
            )
            return

        bot.process_new_updates([update])
    except Exception:
        print("=== UPDATE PROCESSING ERROR ===", flush=True)
        traceback.print_exc()
    finally:
        if lock is not None and lock.locked():
            lock.release()


# =========================
# BOT HANDLERS
# =========================

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    memory.ensure_user(message)
    memory.clear_history(user_id)
    bot.send_message(
        message.chat.id,
        "Привет! Я Ёлки-палки — твой ИИ-Бизнес-Стратег.\n\n"
        "Напиши бизнес-идею или используй /help."
    )


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user_text = message.text
    if not user_text:
        return

    memory.ensure_user(message)

    intent = memory.parse_natural_memory_intent(user_text)
    if intent:
        action, value = intent
        user = memory.get_user(user_id)
        if action == "set_budget":
            memory.set_budget(user_id, value)
            bot.send_message(message.chat.id, f"✅ Бюджет сохранён: €{value:,}.")
            return
        if action == "get_budget":
            budget = (user or {}).get("budget_euro")
            bot.send_message(
                message.chat.id,
                f"💰 Твой бюджет: €{budget:,}." if budget else "💰 Бюджет не сохранён."
            )
            return

    memory.append_message(user_id, "user", user_text)

    context = (
        memory.format_prior_ideas(memory.remember_ideas(user_id, user_text))
        + memory.feedback_lessons(user_id)
        + memory.format_reflections(memory.get_reflections(user_id))
    )

    history = memory.get_history(user_id, MAX_HISTORY)
    system_prompt = (
        SYSTEM_PROMPT
        .replace("{profile}", memory.profile_blurb(user_id))
        .replace("{context}", context)
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)

    try:
        answer = generate_business_answer(messages)
        answer = audit_business_answer(user_text, answer)
        answer = clean_telegram_text(answer)

        memory.append_message(user_id, "assistant", answer)
        memory.maybe_save_analysis(user_id, user_text, answer)

        for i in range(0, len(answer), 4000):
            bot.send_message(message.chat.id, answer[i:i + 4000])
    except Exception as e:
        print("=== AI ERROR ===", repr(e), flush=True)
        bot.send_message(
            message.chat.id,
            "Временная ошибка сервера. Попробуй ещё раз через пару секунд."
        )


def configure_webhook():
    if not TELEGRAM_WEBHOOK_SECRET:
        return False
    return bot.set_webhook(url=WEBHOOK_URL, secret_token=TELEGRAM_WEBHOOK_SECRET)


if __name__ == "__main__":
    try:
        configure_webhook()
    except Exception as e:
        print("Webhook error:", repr(e))
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
