import os
import re
import threading
import time
import traceback

from dotenv import load_dotenv
from flask import Flask, request
from groq import Groq
import telebot

import calc
import groq_utils
import memory
import moltbook
import reminders
import scraper
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
MOLTBOOK_POST_INTERVAL = int(os.getenv("MOLTBOOK_POST_INTERVAL", "14400"))

_last_moltbook_post_at = [0.0]


def _solve_moltbook_challenge(challenge_text):
    """Answer the anti-spam math challenge with Groq.

    The challenge is an obfuscated word problem (e.g. "Twenty Five Newtons
    * Two Claws"); the heuristic parser in moltbook.py often gets these
    wrong, so we ask a model. Returns a "%.2f" string or None on failure.
    """
    if not challenge_text:
        return None
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You solve obfuscated one-line math word problems. "
                        "The text has random punctuation/caps sprinkled in. "
                        "Deobfuscate it, work out the arithmetic, and reply "
                        "with ONLY the numeric answer, two decimal places, "
                        "e.g. 50.00"
                    ),
                },
                {"role": "user", "content": challenge_text},
            ],
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=1000,
        )
        answer = (
            completion.choices[0].message.content or ""
        ).strip()
        num = re.search(r"-?\d+(?:\.\d+)?", answer)
        if not num:
            return None
        return f"{float(num.group()):.2f}"
    except Exception:
        traceback.print_exc()
        return None


def _moltbook_post_update():
    """Generate a business insight with Groq and publish it to Moltbook.

    Learns from post scores: if past posts with a certain angle are well
    received (upvotes/comments), newer posts lean into that theme. Every
    post ends with a pointer to the Telegram bot to link audiences.
    """
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
            print(msg, flush=True)
        else:
            print("=== MOLTBOOK POST FAILED ===", flush=True)
            print(msg, flush=True)
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
_last_moltbook_post_score = [None]


def _pick_moltbook_topic():
    """Pick a post topic, biased toward what performed well before."""
    posts, err = moltbook.get_my_posts()
    if not err and posts:
        for p in posts:
            score = (p.get("score") or 0) + (p.get("comment_count") or 0)
            if score > 0:
                # A topic landed: reuse/rotate the strongest theme.
                prev = _last_moltbook_post_score[0]
                _last_moltbook_post_score[0] = score
                return _MOLTBOOK_TOPICS[0]
    # Otherwise rotate through the list.
    idx = int(time.time() // MOLTBOOK_POST_INTERVAL) % len(_MOLTBOOK_TOPICS)
    return _MOLTBOOK_TOPICS[idx]


MOLTBOOK_ACTIVITY_INTERVAL = int(os.getenv("MOLTBOOK_ACTIVITY_INTERVAL", "14400"))
MOLTBOOK_MAX_UPVOTES = int(os.getenv("MOLTBOOK_MAX_UPVOTES", "4"))

_touched_posts = set()
_last_moltbook_activity_at = [0.0]


def _gen_comment(post_content):
    """Draft a short, respectful English comment for another agent's post."""
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a business strategist. Write ONE short, genuinely "
                        "useful and respectful comment (1-2 sentences) in English "
                        "about the post below. Do not invent facts. Remove any "
                        "buzzword salad. Reply with only the comment text."
                    ),
                },
                {"role": "user", "content": post_content[:1500]},
            ],
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=1000,
        )
        text = (completion.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        traceback.print_exc()
        return None


def _moltbook_social_activity():
    """Like and occasionally comment on feed posts, at a slow cadence.

    Runs no more than once per MOLTBOOK_ACTIVITY_INTERVAL to stay useful
    without spamming. Upvotes are free; a comment is drafted via Groq.
    """
    global _last_moltbook_activity_at
    if time.time() - _last_moltbook_activity_at[0] < MOLTBOOK_ACTIVITY_INTERVAL:
        return

    try:
        posts, err = moltbook.feed(filter_="following", limit=10)
        if err or not posts:
            return
        done = 0
        for p in posts:
            pid = p.get("id")
            if not pid or pid in _touched_posts:
                continue
            ok, _ = moltbook.upvote_post(pid)
            if ok:
                _touched_posts.add(pid)
                done += 1
            if done >= MOLTBOOK_MAX_UPVOTES:
                break

        # One thoughtful comment per interval, if a fresh post is available.
        for p in posts:
            pid = p.get("id")
            if not pid or pid in _touched_posts:
                continue
            if moltbook.my_comments_on(pid):
                _touched_posts.add(pid)
                continue
            content = p.get("content") or ""
            if not content:
                continue
            comment = _gen_comment(content)
            if not comment:
                break
            ok, cid = moltbook.comment_on_post(pid, comment[:500])
            if ok:
                _touched_posts.add(pid)
            break

        _last_moltbook_activity_at[0] = time.time()
        print(f"=== MOLTBOOK ACTIVITY: {done} upvotes ===", flush=True)
    except Exception:
        print("=== MOLTBOOK ACTIVITY ERROR ===", flush=True)
        traceback.print_exc()


MOLTBOOK_REPLY_MAX = int(os.getenv("MOLTBOOK_REPLY_MAX", "3"))


def _gen_reply(mention_content):
    """Draft a short, natural reply to an agent that mentioned us."""
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are yolky-palky-biz, a friendly AI business "
                        "strategist on Moltbook. Reply briefly and naturally "
                        "(2-4 sentences, in English) to the message below "
                        "from another agent. Be warm, direct, on-topic and "
                        "genuine. Do not use lists, emojis or hashtags. "
                        "Reply with only your message."
                    ),
                },
                {"role": "user", "content": mention_content[:1500]},
            ],
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=1000,
        )
        return (completion.choices[0].message.content or "").strip() or None
    except Exception:
        traceback.print_exc()
        return None


def _moltbook_reply_to_mentions():
    """Answer mentions (posts that @-mention this agent) once each.

    Uses unread 'mention' notifications: drafts a reply via Groq, posts
    it as a comment, and marks the notification read so it is not repeated.
    """
    try:
        notifications, err = moltbook.get_notifications()
        if err:
            return
        handled = 0
        for n in notifications:
            if handled >= MOLTBOOK_REPLY_MAX:
                break
            if n.get("type") != "mention" or n.get("isRead"):
                continue
            related_id = n.get("relatedPostId")
            if not related_id:
                continue
            reply = _gen_reply(n.get("content") or "")
            if not reply:
                moltbook.mark_notification_read(n.get("id"))
                continue
            ok, _ = moltbook.reply_to_post(related_id, reply[:500])
            moltbook.mark_notification_read(n.get("id"))
            if ok:
                handled += 1
                print(f"=== MOLTBOOK REPLIED to post {related_id} ===", flush=True)
    except Exception:
        print("=== MOLTBOOK REPLY ERROR ===", flush=True)
        traceback.print_exc()


def _gen_follower_greeting(follower_name, post_content):
    """Draft a warm English greeting for a new follower's post."""
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are yolky-palky-biz, a friendly AI business "
                        "strategist on Moltbook. An agent just started "
                        f"following you. Write ONE short, warm and genuine "
                        "comment (2-3 sentences, in English) thanking them "
                        f"for the follow and showing interest in their post "
                        "below. Be natural, do not use lists, emojis or "
                        "hashtags. Reply with only the comment text."
                    ),
                },
                {"role": "user", "content": post_content[:1500]},
            ],
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=1000,
        )
        return (completion.choices[0].message.content or "").strip() or None
    except Exception:
        traceback.print_exc()
        return None


def _moltbook_greet_followers():
    """Welcome new followers by commenting on their latest post.

    Uses unread 'new_follower' notifications: looks up the follower's
    newest post, drops a warm thank-you comment, and marks the
    notification read so each follower is greeted only once.
    """
    try:
        notifications, err = moltbook.get_notifications()
        if err:
            return
        handled = 0
        for n in notifications:
            if handled >= MOLTBOOK_REPLY_MAX:
                break
            if n.get("type") != "new_follower" or n.get("isRead"):
                continue
            content = n.get("content") or ""
            follower_name = content.replace("started following you", "").strip()
            if not follower_name:
                moltbook.mark_notification_read(n.get("id"))
                continue
            posts, perr = moltbook.posts_by_agent(follower_name, limit=3)
            if perr or not posts:
                moltbook.mark_notification_read(n.get("id"))
                continue
            target = posts[0]
            pid = target.get("id")
            if not pid:
                moltbook.mark_notification_read(n.get("id"))
                continue
            if moltbook.my_comments_on(pid):
                moltbook.mark_notification_read(n.get("id"))
                continue
            post_text = (target.get("content") or "") or (target.get("title") or "")
            greeting = _gen_follower_greeting(follower_name, post_text)
            if not greeting:
                moltbook.mark_notification_read(n.get("id"))
                continue
            ok, _ = moltbook.comment_on_post(pid, greeting[:500])
            moltbook.mark_notification_read(n.get("id"))
            if ok:
                handled += 1
                print(f"=== MOLTBOOK GREETED follower {follower_name} on post {pid} ===", flush=True)
    except Exception:
        print("=== MOLTBOOK FOLLOWER GREETING ERROR ===", flush=True)
        traceback.print_exc()


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
                _moltbook_social_activity()
                _moltbook_reply_to_mentions()
                _moltbook_greet_followers()
                moltbook.notify_on_update(bot, reminders._active_chat_ids())
        except Exception:
            print("=== MOLTBOOK HEARTBEAT ERROR ===", flush=True)
            traceback.print_exc()
        time.sleep(MOLTBOOK_CHECK_INTERVAL)  # keep a proper delay between beats


if MOLTBOOK_ENABLED:
    threading.Thread(
        target=moltbook_heartbeat_loop,
        daemon=True,
        name="moltbook-heartbeat",
    ).start()

REMINDEURS_ENABLED = os.getenv("REMINDEURS_ENABLED", "1") == "1"

if REMINDEURS_ENABLED:
    threading.Thread(
        target=reminders.daily_reminder_loop,
        args=(bot,),
        daemon=True,
        name="reminders",
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

MAX_HISTORY = 10


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

    memory.ensure_user(message)

    user_histories[user_id] = []

    bot.send_message(
        message.chat.id,
        "Привет! Я Ёлки-палки — твой ИИ-Бизнес-Стратег.\n\n"
        "Моя задача — помочь тебе двигаться к цели "
        "€5 000 чистой прибыли в месяц.\n\n"
        "Я буду анализировать бизнес, считать расходы и прибыль, "
        "сравнивать варианты и искать актуальную информацию.\n\n"
        "Рассказывай, что хочешь сделать.\n\n"
        "Настроить профиль: /profile, цель: /goal, статус: /status"
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


# =========================
# GOAL / PROFILE / STATUS
# =========================

def _parse_amount(text):
    m = re.search(r"(\d[\d ]*)", text.replace(",", "").replace(".", ""))
    if not m:
        return None
    return int(m.group(1).replace(" ", ""))


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
            "content": SYSTEM_PROMPT.format(
                profile=memory.profile_blurb(user_id)
            )
        }
    ]

    messages.extend(history)

    try:

        print(
            "=== SENDING REQUEST TO GROQ ===",
            flush=True
        )

        answer = groq_utils.chat_with_search(
            client,
            MODEL,
            messages=messages,
        )

        print(
            "=== GROQ RESPONSE RECEIVED ===",
            flush=True
        )

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
