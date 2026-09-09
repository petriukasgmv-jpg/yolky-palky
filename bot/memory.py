import os
import re
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "userstate.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    chat_id      INTEGER,
    first_name   TEXT,
    username     TEXT,
    goal_euro    INTEGER,
    skills       TEXT,
    city         TEXT,
    budget_euro  INTEGER,
    about        TEXT,
    created_at   INTEGER,
    updated_at   INTEGER
);

CREATE TABLE IF NOT EXISTS messages (
    user_id    INTEGER NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, created_at);
"""


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def ensure_user(message):
    user = message.from_user
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user.id,),
    )
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users "
            "(user_id, chat_id, first_name, username, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user.id, message.chat.id, user.first_name, user.username,
             int(time.time()), int(time.time())),
        )
    else:
        cur.execute(
            "UPDATE users SET chat_id = ?, updated_at = ? WHERE user_id = ?",
            (message.chat.id, int(time.time()), user.id),
        )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _update(user_id, **fields):
    if not fields:
        return
    fields["updated_at"] = int(time.time())
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [user_id]
    conn = _conn()
    conn.execute(f"UPDATE users SET {cols} WHERE user_id = ?", vals)
    conn.commit()
    conn.close()


def set_goal(user_id, amount):
    _update(user_id, goal_euro=int(amount))


def set_budget(user_id, amount):
    _update(user_id, budget_euro=int(amount))


def set_city(user_id, city):
    _update(user_id, city=city)


def set_skills(user_id, skills):
    _update(user_id, skills=skills)


def set_about(user_id, about):
    _update(user_id, about=about)


_FIELD_KEYS = (
    ("навыки", "skills"),
    ("скилы", "skills"),
    ("skills", "skills"),
    ("город", "city"),
    ("городе", "city"),
    ("city", "city"),
    ("бюджет", "budget_euro"),
    ("цель", "goal_euro"),
)


def parse_profile(text):
    """Parse /profile free text into a dict of recognized fields.

    Profile fields are separated by ';' and given as ``ключ: значение``.
    Returns a dict with any of: skills, city, budget_euro, goal_euro.
    """
    out = {}
    for segment in text.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        for key, field in _FIELD_KEYS:
            m = re.match(rf"{key}\s*:\s*(.+)", segment, re.IGNORECASE)
            if not m:
                continue
            val = m.group(1).strip(" ,;")
            if field in ("budget_euro", "goal_euro"):
                num = re.search(r"\d[\d ]*", val)
                if num:
                    out[field] = int(num.group().replace(" ", ""))
            elif val:
                out[field] = val
            break
    return out


def profile_blurb(user_id):
    """A short text about the user, injected into the system prompt."""
    u = get_user(user_id)
    if not u:
        return ""
    parts = []
    if u.get("skills"):
        parts.append(f"Навыки: {u['skills']}")
    if u.get("city"):
        parts.append(f"Город: {u['city']}")
    if u.get("budget_euro"):
        parts.append(f"Стартовый бюджет: €{u['budget_euro']}")
    if u.get("goal_euro"):
        parts.append(f"Цель: €{u['goal_euro']} чистой прибыли в месяц")
    if u.get("about"):
        parts.append(f"О себе: {u['about']}")
    if not parts:
        return ""
    return "ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:\n" + "\n".join("- " + p for p in parts) + "\n"


def format_profile(user_id):
    u = get_user(user_id)
    if not u:
        return "Профиль не настроен."
    lines = []
    goal = u.get("goal_euro")
    lines.append(f"🎯 Цель: €{goal:,} чистыми/мес" if goal
                 else "🎯 Цель: не задана")
    lines.append(f"🧰 Навыки: {u['skills']}" if u.get("skills")
                 else "🧰 Навыки: не указаны")
    lines.append(f"📍 Город: {u['city']}" if u.get("city")
                 else "📍 Город: не указан")
    lines.append(f"💰 Бюджет: €{u['budget_euro']:,}" if u.get("budget_euro")
                 else "💰 Бюджет: не указан")
    if u.get("about"):
        lines.append(f"📝 О себе: {u['about']}")
    return "Профиль:\n" + "\n".join(lines)


MAX_STORED_MESSAGES = 100


def append_message(user_id, role, content):
    """Persist one message. Old messages are pruned to keep the DB bounded."""
    conn = _conn()
    conn.execute(
        "INSERT INTO messages (user_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?)",
        (user_id, role, content, int(time.time())),
    )
    conn.execute(
        "DELETE FROM messages WHERE user_id = ? AND rowid NOT IN "
        "(SELECT rowid FROM messages WHERE user_id = ? "
        " ORDER BY rowid DESC LIMIT ?)",
        (user_id, user_id, MAX_STORED_MESSAGES),
    )
    conn.commit()
    conn.close()


def get_history(user_id, limit=10):
    """Last N messages for a user, oldest first (for the LLM context)."""
    conn = _conn()
    rows = conn.execute(
        "SELECT role, content FROM messages "
        "WHERE user_id = ? ORDER BY rowid ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    history = [{"role": r["role"], "content": r["content"]} for r in rows]
    return history[-limit:]


def clear_history(user_id):
    conn = _conn()
    conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def progress_line(user_id):
    u = get_user(user_id)
    if not u or not u.get("goal_euro"):
        return ("Цель ещё не задана. Стань цель командой, например:\n"
                "/goal 5000")
    goal = u["goal_euro"]
    return (
        f"🎯 Цель: €{goal:,} чистой прибыли в месяц.\n"
        f"Прогресс пока не отмечается — первый шаг:\n"
        f"1. Задай одну бизнес-идею для анализа\n"
        f"2. Протестируй спрос на неё без вложений\n"
        f"3. Получи первый заказ\n"
    )