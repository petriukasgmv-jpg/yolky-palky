import os
import time
import traceback

REMINDEURS_INTERVAL = int(os.getenv("REMINDER_INTERVAL", "86400"))

REMINDER_TEXT = (
    "🧭 Ежедневное напоминание\n\n"
    "Что можно сделать сегодня (выбери одно):\n"
    "1. Проверь одну бизнес-идею /price или обсуди её со мной\n"
    "2. Посчитай экономику продажи: /calc цена:... себест:...\n"
    "3. Размести/сними объявление на Vinted или eBay\n"
    "4. Обнови статус: /status\n\n"
    "Помни цель: €5 000 чистой прибыли в месяц — это ~25 продаж "
    "при прибыли €200 с каждой. Сначала продать → потом масштабировать."
)

WEEKLY_TEXT = (
    "📊 Еженедельный разбор\n\n"
    "5 вопросов для себя:\n"
    "1. Сколько заказов было на этой неделе?\n"
    "2. Сколько прибыли с каждого?\n"
    "3. Что мешало продажам?\n"
    "4. Какая одна цена/товар дали больше всего?\n"
    "5. Что повторишь, что уберёшь?\n\n"
    "Расскажи мне — я помогу посчитать и составить план на неделю."
)

REMINDER_HOUR = int(os.getenv("REMINDER_HOUR", "19"))
WEEKLY_HOUR = int(os.getenv("WEEKLY_REMINDER_HOUR", "18"))


def _send(bot, chat_id, text):
    try:
        bot.send_message(chat_id, text)
    except Exception:
        traceback.print_exc()


def daily_reminder_loop(bot):
    """Send daily and weekly reminders.

    Daily: every day at REMINDER_HOUR.
    Weekly: every Sunday at WEEKLY_HOUR.
    """
    last_daily = None
    last_weekly = None

    while True:
        try:
            now = time.localtime()
            today = now.tm_yday
            hour = now.tm_hour

            if hour == REMINDER_HOUR and last_daily != today:
                last_daily = today
                chat_ids = _active_chat_ids()
                for cid in chat_ids:
                    _send(bot, cid, REMINDER_TEXT)

            if hour == WEEKLY_HOUR and now.tm_wday == 6 and last_weekly != today:
                last_weekly = today
                chat_ids = _active_chat_ids()
                for cid in chat_ids:
                    _send(bot, cid, WEEKLY_TEXT)

        except Exception:
            traceback.print_exc()

        time.sleep(600)


def _active_chat_ids():
    """Chat ids of users who've used the bot at least once."""
    import memory
    conn = memory._conn()
    rows = conn.execute(
        "SELECT DISTINCT chat_id FROM users WHERE chat_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return [r["chat_id"] for r in rows]