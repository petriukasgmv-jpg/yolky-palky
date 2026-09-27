import os
import re
import hmac
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, request
from groq import Groq
import telebot
from telebot import types

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
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

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

# Acknowledge webhook requests immediately and process updates in the
# background, so slow AI/search calls do not make Telegram retry updates.
UPDATE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="telegram-update")
_processed_update_ids = set()
_processed_update_order = deque(maxlen=2000)
_processed_update_lock = threading.Lock()


def _mark_update_seen(update_id):
    """Return False for a duplicate Telegram update, True for a new one."""
    if update_id is None:
        return True
    with _processed_update_lock:
        if update_id in _processed_update_ids:
            return False
        if len(_processed_update_order) == _processed_update_order.maxlen:
            _processed_update_ids.discard(_processed_update_order[0])
        _processed_update_order.append(update_id)
        _processed_update_ids.add(update_id)
        return True


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
                        "РўС‹ вЂ” РР Р±РёР·РЅРµСЃ-СЃС‚СЂР°С‚РµРі. РќР°РїРёС€Рё РєРѕСЂРѕС‚РєРёР№ РїРѕР»РµР·РЅС‹Р№ РїРѕСЃС‚ "
                        "РґР»СЏ СЃРѕС†СЃРµС‚Рё РР-Р°РіРµРЅС‚РѕРІ РЅР° СЂСѓСЃСЃРєРѕРј Рё Р°РЅРіР»РёР№СЃРєРѕРј Рѕ С‚РѕРј: "
                        f"{topic}. "
                        "Р”Р°Р№ РѕРґРёРЅ РєРѕРЅРєСЂРµС‚РЅС‹Р№ СЃРѕРІРµС‚ Рё РєРѕСЂРѕС‚РєРёР№ РїСЂРёРјРµСЂ СЂР°СЃС‡С‘С‚Р°. "
                        "Р‘РµР· РІРѕРґС‹, 3-5 РїСЂРµРґР»РѕР¶РµРЅРёР№. Р’ РєРѕРЅС†Рµ РґРѕР±Р°РІСЊ СЃС‚СЂРѕРєСѓ: "
                        "'рџ¤– Р‘РѕР»СЊС€Рµ РёРґРµР№ Рё РїРѕРґСЃС‡С‘С‚РѕРІ: t.me/yolky_palky_bot'"
                    ),
                },
                {"role": "user", "content": "РЎРѕСЃС‚Р°РІСЊ РїРѕСЃС‚."},
            ],
            max_tokens=600,
        )
        if not content:
            return None
        title = "Business Idea Test рџ’Ў вЂ” how to check an idea with minimum money"
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
    "РєР°Рє РїСЂРѕРІРµСЂРёС‚СЊ Р±РёР·РЅРµСЃ-РёРґРµСЋ СЃ РјРёРЅРёРјР°Р»СЊРЅС‹РјРё РІР»РѕР¶РµРЅРёСЏРјРё",
    "Р°СЂР±РёС‚СЂР°Р¶ СЃРѕРІРµС‚СЃРєРёС… С‡Р°СЃРѕРІ Рё РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ: СЃРєРѕР»СЊРєРѕ СЃРґРµР»РѕРє РЅСѓР¶РЅРѕ РґР»СЏ С†РµР»Рё",
    "РєРѕРЅСЃР°Р»С‚РёРЅРі РїРѕ РіСЂР°РЅС‚Р°Рј: РєР°Рє Р·Р°СЂР°Р±РѕС‚Р°С‚СЊ 10-20% РѕС‚ РѕРґРѕР±СЂРµРЅРЅРѕР№ СЃСѓРјРјС‹",
    "СЂР°СЃС‡С‘С‚ С‡РёСЃС‚РѕР№ РїСЂРёР±С‹Р»Рё: РєРѕРјРёСЃСЃРёРё, РґРѕСЃС‚Р°РІРєР°, РЅР°Р»РѕРіРё РїСЂРѕС‚РёРІ РјР°СЂР¶Рё",
    "РїРµСЂРІС‹Рµ РїСЂРѕРґР°Р¶Рё Р±РµР· СЂРµРєР»Р°РјС‹: Р±РµСЃРїР»Р°С‚РЅС‹Рµ РєР°РЅР°Р»С‹ Рё РєР°Рє С‚РµСЃС‚РёСЂРѕРІР°С‚СЊ СЃРїСЂРѕСЃ",
]
_last_moltbook_post_score = [None]


def _pick_moltbook_topic():
    """Rotate topics predictably; post scores do not identify a topic."""
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


# =========================
# SELF-REFLECTION
# =========================

def _reflect_user(user_id):
    """Summarize a user's recent dialogue into a lasting reflection."""
    since = memory.latest_reflection_rowid(user_id)
    messages, last_rowid = memory.messages_since(user_id, since_rowid=since, limit=80)
    if not messages or not last_rowid:
        return None
    conv = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages
    )[-12000:]
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "РўС‹ вЂ” СЂРµС„Р»РµРєСЃРёРІРЅР°СЏ С‡Р°СЃС‚СЊ РР-Р±РёР·РЅРµСЃ-СЃС‚СЂР°С‚РµРіР°. РџРѕ РґРёР°Р»РѕРіСѓ "
                        "РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ СЃРґРµР»Р°Р№ РєСЂР°С‚РєСѓСЋ РІС‹Р¶РёРјРєСѓ: РєР°РєРёРµ Р±РёР·РЅРµСЃ-РёРґРµРё "
                        "РѕР±СЃСѓР¶РґР°Р»РёСЃСЊ, РєР°РєРёРµ СЂР°СЃС‡С‘С‚С‹ Рё РІС‹РІРѕРґС‹ СЃРґРµР»Р°РЅС‹, РєР°РєРёРµ С€Р°РіРё "
                        "РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ СѓР¶Рµ СЃРґРµР»Р°Р» РёР»Рё РїР»Р°РЅРёСЂСѓРµС‚, РєР°РєРёРµ СЂРµС€РµРЅРёСЏ "
                        "РїСЂРёРЅСЏС‚С‹. 2-4 РїСЂРµРґР»РѕР¶РµРЅРёСЏ РЅР° СЂСѓСЃСЃРєРѕРј, Р±РµР· РІРѕРґС‹ Рё Р±РµР· "
                        "РѕС†РµРЅРѕРє РІСЂРѕРґРµ В«РјРѕР»РѕРґРµС†В»."
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
    """Weekly: distill each active user's dialogue into reflections."""
    last_reflect = [None]
    while True:
        try:
            now = time.localtime()
            today = now.tm_yday
            if now.tm_wday == 6 and last_reflect[0] != today:
                last_reflect[0] = today
                for user_id in memory.all_user_ids():
                    summary = _reflect_user(user_id)
                    if summary:
                        print(f"=== REFLECTED user {user_id}: {summary[:60]} ===", flush=True)
        except Exception:
            print("=== REFLECTION LOOP ERROR ===", flush=True)
            traceback.print_exc()
        time.sleep(3600)


REFLECTIONS_ENABLED = os.getenv("REFLECTIONS_ENABLED", "1") == "1"

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

if REFLECTIONS_ENABLED:
    threading.Thread(
        target=self_reflection_loop,
        daemon=True,
        name="self-reflection",
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

MAX_HISTORY = 10


def clean_telegram_text(text):
    """Convert common model formatting to readable plain Telegram text."""
    if not text:
        return ""

    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = text.replace("```", "")

    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # Remove Markdown table separator rows such as |---|---|.
        if stripped and re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", stripped):
            continue
        if "|" in line:
            line = line.replace("|", " вЂ” ")
            line = re.sub(r"\s+вЂ”\s+", " вЂ” ", line).strip(" вЂ”")
        cleaned_lines.append(line.rstrip())

    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines)).strip()


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
    try:
        if not TELEGRAM_WEBHOOK_SECRET:
            print("=== WEBHOOK ERROR: TELEGRAM_WEBHOOK_SECRET is not set ===", flush=True)
            return "Webhook secret is not configured", 500

        received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not received_secret or not hmac.compare_digest(
            received_secret, TELEGRAM_WEBHOOK_SECRET
        ):
            return "Unauthorized", 403

        raw_data = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(raw_data)

        update_id = getattr(update, "update_id", None)
        if not _mark_update_seen(update_id):
            return "OK", 200

        UPDATE_EXECUTOR.submit(_process_update, update)

        return "OK", 200

    except Exception as e:

        print("=== WEBHOOK ERROR ===", flush=True)
        print(repr(e), flush=True)

        traceback.print_exc()

        return "ERROR", 500


def _process_update(update):
    """Process a Telegram update after the webhook has been acknowledged."""
    try:
        if update.message and update.message.text == "/start":
            user_id = update.message.from_user.id
            memory.ensure_user(update.message)
            memory.clear_history(user_id)
            bot.send_message(
                update.message.chat.id,
                "РџСЂРёРІРµС‚! РЇ РЃР»РєРё-РїР°Р»РєРё вЂ” С‚РІРѕР№ РР-Р‘РёР·РЅРµСЃ-РЎС‚СЂР°С‚РµРі.\n\n"
                "РњРѕСЏ Р·Р°РґР°С‡Р° вЂ” РїРѕРјРѕС‡СЊ С‚РµР±Рµ РІС‹Р№С‚Рё РЅР° "
                "в‚¬5 000 С‡РёСЃС‚РѕР№ РїСЂРёР±С‹Р»Рё РІ РјРµСЃСЏС†.\n\n"
                "РќР°РїРёС€Рё РјРЅРµ Р»СЋР±СѓСЋ Р±РёР·РЅРµСЃ-РёРґРµСЋ."
            )
            return

        bot.process_new_updates([update])
    except Exception:
        print("=== UPDATE PROCESSING ERROR ===", flush=True)
        traceback.print_exc()


# =========================
# START
# =========================

@bot.message_handler(commands=["start"])
def start(message):

    user_id = message.from_user.id

    memory.ensure_user(message)

    memory.clear_history(user_id)

    bot.send_message(
        message.chat.id,
        "РџСЂРёРІРµС‚! РЇ РЃР»РєРё-РїР°Р»РєРё вЂ” С‚РІРѕР№ РР-Р‘РёР·РЅРµСЃ-РЎС‚СЂР°С‚РµРі.\n\n"
        "РњРѕСЏ Р·Р°РґР°С‡Р° вЂ” РїРѕРјРѕС‡СЊ С‚РµР±Рµ РґРІРёРіР°С‚СЊСЃСЏ Рє С†РµР»Рё "
        "в‚¬5 000 С‡РёСЃС‚РѕР№ РїСЂРёР±С‹Р»Рё РІ РјРµСЃСЏС†.\n\n"
        "РЇ Р±СѓРґСѓ Р°РЅР°Р»РёР·РёСЂРѕРІР°С‚СЊ Р±РёР·РЅРµСЃ, СЃС‡РёС‚Р°С‚СЊ СЂР°СЃС…РѕРґС‹ Рё РїСЂРёР±С‹Р»СЊ, "
        "СЃСЂР°РІРЅРёРІР°С‚СЊ РІР°СЂРёР°РЅС‚С‹ Рё РёСЃРєР°С‚СЊ Р°РєС‚СѓР°Р»СЊРЅСѓСЋ РёРЅС„РѕСЂРјР°С†РёСЋ.\n\n"
        "Р Р°СЃСЃРєР°Р·С‹РІР°Р№, С‡С‚Рѕ С…РѕС‡РµС€СЊ СЃРґРµР»Р°С‚СЊ.\n\n"
        "РќР°СЃС‚СЂРѕРёС‚СЊ РїСЂРѕС„РёР»СЊ: /profile, С†РµР»СЊ: /goal, СЃС‚Р°С‚СѓСЃ: /status"
    )


# =========================
# HELP
# =========================

@bot.message_handler(commands=["help"])
def help_command(message):

    bot.send_message(
        message.chat.id,
        "РЇ РјРѕРіСѓ:\n\n"
        "вЂў Р°РЅР°Р»РёР·РёСЂРѕРІР°С‚СЊ Р±РёР·РЅРµСЃ-РёРґРµРё\n"
        "вЂў СЃС‡РёС‚Р°С‚СЊ РїСЂРёР±С‹Р»СЊ Рё СЂР°СЃС…РѕРґС‹\n"
        "вЂў СЃСЂР°РІРЅРёРІР°С‚СЊ Р±РёР·РЅРµСЃ-РјРѕРґРµР»Рё\n"
        "вЂў РёСЃРєР°С‚СЊ Р°РєС‚СѓР°Р»СЊРЅС‹Рµ С†РµРЅС‹ Рё РєРѕРЅРєСѓСЂРµРЅС‚РѕРІ\n"
        "вЂў СЂР°СЃСЃС‡РёС‚С‹РІР°С‚СЊ РїСЂРѕРґР°Р¶Рё РґР»СЏ в‚¬5 000\n"
        "вЂў РїРѕРјРѕРіР°С‚СЊ РёСЃРєР°С‚СЊ РїРµСЂРІС‹С… РєР»РёРµРЅС‚РѕРІ\n"
        "вЂў СЃРѕСЃС‚Р°РІР»СЏС‚СЊ РїРѕС€Р°РіРѕРІС‹Р№ РїР»Р°РЅ\n\n"
        "РљРѕРјР°РЅРґС‹:\n"
        "/goal 5000 вЂ” СѓСЃС‚Р°РЅРѕРІРёС‚СЊ С†РµР»СЊ (в‚¬)\n"
        "/profile вЂ” РїРѕСЃРјРѕС‚СЂРµС‚СЊ РїСЂРѕС„РёР»СЊ\n"
        "/profile РЅР°РІС‹РєРё: СЃРІР°СЂРєР°, РјРµР±РµР»СЊ; РіРѕСЂРѕРґ: РњСЋРЅС…РµРЅ; Р±СЋРґР¶РµС‚: 500 вЂ” Р·Р°РїРѕР»РЅРёС‚СЊ\n"
        "/calc С†РµРЅР°:250 СЃРµР±РµСЃС‚:50 вЂ” СЌРєРѕРЅРѕРјРёРєР° РѕРґРЅРѕР№ РїСЂРѕРґР°Р¶Рё\n"
        "/price РЅР°СЂСѓС‡РЅС‹Рµ С‡Р°СЃС‹ РЎРЎРЎР  вЂ” Р°РєС‚СѓР°Р»СЊРЅС‹Рµ С†РµРЅС‹ РЅР° Р±Р°СЂР°С…РѕР»РєР°С…\n"
        "/status вЂ” РїСЂРѕРіСЂРµСЃСЃ Рє С†РµР»Рё\n"
        "/clear вЂ” РѕС‡РёСЃС‚РёС‚СЊ РёСЃС‚РѕСЂРёСЋ"
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
                "РќРµ РїРѕРЅСЏР» С‡РёСЃР»Рѕ. РџСЂРёРјРµСЂ: /goal 5000",
            )

            return

        memory.set_goal(user_id, amount)

        bot.send_message(
            message.chat.id,
            f"рџЋЇ Р¦РµР»СЊ СѓСЃС‚Р°РЅРѕРІР»РµРЅР°: в‚¬{amount:,} С‡РёСЃС‚РѕР№ РїСЂРёР±С‹Р»Рё РІ РјРµСЃСЏС†.",
        )

        return

    u = memory.get_user(user_id)

    if u and u.get("goal_euro"):

        bot.send_message(
            message.chat.id,
            f"РўРµРєСѓС‰Р°СЏ С†РµР»СЊ: в‚¬{u['goal_euro']:,} С‡РёСЃС‚С‹РјРё/РјРµСЃ.\n"
            "РР·РјРµРЅРёС‚СЊ: /goal <СЃСѓРјРјР°>",
        )

    else:

        bot.send_message(
            message.chat.id,
            "Р¦РµР»СЊ РµС‰С‘ РЅРµ Р·Р°РґР°РЅР°. Р—Р°РґР°Р№, РЅР°РїСЂРёРјРµСЂ: /goal 5000",
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
            "вњ… РџСЂРѕС„РёР»СЊ РѕР±РЅРѕРІР»С‘РЅ.\n\n" + memory.format_profile(user_id),
        )

        return

    bot.send_message(
        message.chat.id,
        memory.format_profile(user_id)
        + "\n\nР—Р°РїРѕР»РЅРёС‚СЊ РјРѕР¶РЅРѕ С‚Р°Рє:\n"
        "/profile РЅР°РІС‹РєРё: СЃРІР°СЂРєР°, РјРµР±РµР»СЊ; РіРѕСЂРѕРґ: РњСЋРЅС…РµРЅ; Р±СЋРґР¶РµС‚: 500",
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
            "РќСѓР¶РЅС‹ РјРёРЅРёРјСѓРј: С†РµРЅР° Рё СЃРµР±РµСЃС‚РѕРёРјРѕСЃС‚СЊ. РџСЂРёРјРµСЂ:\n"
            "/calc С†РµРЅР°:250 СЃРµР±РµСЃС‚:50",
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
        advertising=parsed.get("advertising", 0),
        tax=parsed.get("tax", 0),
        hours=parsed.get("hours", 0),
    )

    if not result:

        bot.send_message(message.chat.id, "Р¦РµРЅР° РґРѕР»Р¶РЅР° Р±С‹С‚СЊ Р±РѕР»СЊС€Рµ 0.")

        return

    text = calc.render_calc(result)

    if not parsed.get("goal") and not (user or {}).get("goal_euro"):

        text += "\n\nрџ’Ў Р—Р°РґР°Р№ С†РµР»СЊ: /goal 5000"

    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["price"])
def price_command(message):

    user_id = message.from_user.id

    args = message.text.split(maxsplit=1)

    if len(args) < 2:

        bot.send_message(
            message.chat.id,
            "Р§С‚Рѕ РёС‰РµРј? РџСЂРёРјРµСЂС‹:\n"
            "/price СЃРѕРІРµС‚СЃРєРёРµ РЅР°СЂСѓС‡РЅС‹Рµ С‡Р°СЃС‹\n"
            "/price РєРѕР¶Р°РЅР°СЏ РєСѓСЂС‚РєР° 90-С…\n"
            "/price Р±РёРЅРѕРєР»СЊ РЎРЎРЎР ",
        )

        return

    query = args[1]

    bot.send_message(
        message.chat.id,
        f"рџ”Ћ РС‰Сѓ Р°РєС‚СѓР°Р»СЊРЅС‹Рµ С†РµРЅС‹: {query}\n\nРџРѕРґРѕР¶РґРё РїР°СЂСѓ СЃРµРєСѓРЅРґ...",
    )

    text, err = scraper.search_prices(client, query)

    if err or not text:

        msg = scraper.FALLBACK_HELP + "\n"

        if err:
            msg += f"РћС€РёР±РєР°: {err}\n"

        msg += "\n" + scraper.manual_search_links(query)

        bot.send_message(message.chat.id, msg)

        return

    prefix = f"рџ”Ћ Р¦РµРЅС‹ РїРѕ Р·Р°РїСЂРѕСЃСѓ: {query}\n\n"

    max_length = 4000

    body = prefix + text

    for i in range(0, len(body), max_length):

        bot.send_message(message.chat.id, body[i:i + max_length])

    bot.send_message(message.chat.id, scraper.manual_search_links(query))


# =========================
# FEEDBACK
# =========================

def _feedback_keyboard(analysis_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("рџ‘Ќ РЎСЂР°Р±РѕС‚Р°Р»Рѕ", callback_data=f"fb:{analysis_id}:1"),
        types.InlineKeyboardButton("рџ‘Ћ РќРµС‚", callback_data=f"fb:{analysis_id}:-1"),
        types.InlineKeyboardButton("РќРµ РїСЂРѕР±РѕРІР°Р»", callback_data=f"fb:{analysis_id}:0"),
    )
    return kb


@bot.callback_query_handler(func=lambda c: c.data.startswith("fb:"))
def on_feedback_callback(callback):
    try:
        _, analysis_id_s, rating_s = callback.data.split(":")
        analysis_id = int(analysis_id_s)
        rating = int(rating_s)
        memory.rate_analysis(callback.from_user.id, analysis_id, rating)
        labels = {1: "рџ‘Ќ Р—Р°РїРёСЃР°Р»: СЃРѕРІРµС‚ СЃСЂР°Р±РѕС‚Р°Р»!", -1: "рџ‘Ћ Р—Р°РїРёСЃР°Р»: РЅРµ СЃСЂР°Р±РѕС‚Р°Р»Рѕ", 0: "рџ“­ Р—Р°РїРёСЃР°Р»: РЅРµ РїСЂРѕР±РѕРІР°Р»"}
        try:
            bot.answer_callback_query(callback.id, labels.get(rating, "РЎРїР°СЃРёР±Рѕ!"))
            bot.edit_message_text(
                "вњ… РћС†РµРЅРєР° Р·Р°РїРёСЃР°РЅР°. РЈС‡С‚Сѓ РІ Р±СѓРґСѓС‰РёС… СЃРѕРІРµС‚Р°С….",
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            )
        except Exception:
            pass
    except Exception:
        traceback.print_exc()


# =========================
# USER MESSAGES
# =========================

@bot.message_handler(func=lambda message: True)
def handle_message(message):

    user_id = message.from_user.id

    user_text = message.text

    if not user_text:
        return

    print(f"=== USER MESSAGE from {user_id} ===", flush=True)

    memory.append_message(user_id, "user", user_text)

    context = (
        memory.format_prior_ideas(memory.remember_ideas(user_id, user_text))
        + memory.feedback_lessons(user_id)
        + memory.format_reflections(memory.get_reflections(user_id))
    )

    history = memory.get_history(user_id, MAX_HISTORY)

    # Replace only supported placeholders. str.format() would fail if the
    # prompt contains ordinary braces in examples or formulas.
    system_prompt = (
        SYSTEM_PROMPT
        .replace("{profile}", memory.profile_blurb(user_id))
        .replace("{context}", context)
    )

    messages = [
        {
            "role": "system",
            "content": system_prompt,
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
                "РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ РѕС‚РІРµС‚. "
                "РџРѕРїСЂРѕР±СѓР№ РµС‰С‘ СЂР°Р·."
            )

        answer = clean_telegram_text(answer)

        print(f"=== ANSWER READY for {user_id} ({len(answer)} chars) ===", flush=True)

        memory.append_message(user_id, "assistant", answer)
        analysis_id = memory.maybe_save_analysis(user_id, user_text, answer)

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

        if analysis_id:

            try:

                keyboard = _feedback_keyboard(analysis_id)

                bot.send_message(
                    message.chat.id,
                    "РћС†РµРЅРё РјРѕР№ СЃРѕРІРµС‚ вЂ” С‚Р°Рє СЏ Р±СѓРґСѓ СѓС‡РёС‚СЊСЃСЏ:",
                    reply_markup=keyboard,
                )

            except Exception:

                pass

    except Exception as e:

        print("=== AI ERROR ===", flush=True)

        print(repr(e), flush=True)

        traceback.print_exc()

        bot.send_message(
            message.chat.id,
            "РќРµ СѓРґР°Р»РѕСЃСЊ РѕР±СЂР°Р±РѕС‚Р°С‚СЊ Р·Р°РїСЂРѕСЃ РёР·-Р·Р° РІСЂРµРјРµРЅРЅРѕР№ С‚РµС…РЅРёС‡РµСЃРєРѕР№ РѕС€РёР±РєРё.\n\n"
            "РџРѕРїСЂРѕР±СѓР№ РµС‰С‘ СЂР°Р· С‡РµСЂРµР· РЅРµСЃРєРѕР»СЊРєРѕ СЃРµРєСѓРЅРґ."
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

        if not TELEGRAM_WEBHOOK_SECRET:
            raise RuntimeError(
                "TELEGRAM_WEBHOOK_SECRET is required for a secure webhook"
            )

        result = bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=TELEGRAM_WEBHOOK_SECRET,
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
