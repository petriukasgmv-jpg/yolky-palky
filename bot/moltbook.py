import json
import os
import time

import requests

MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "moltbook_credentials.json")
STATE_FILE = os.path.join(os.path.dirname(__file__), "moltbook_state.json")

AGENT_NAME = os.getenv("MOLTBOOK_AGENT_NAME", "yolky-palky")
AGENT_DESCRIPTION = os.getenv(
    "MOLTBOOK_AGENT_DESCRIPTION",
    "AI Business Strategist. Analyzes business ideas, calculates costs, "
    "profit and payback, plans the path to €5,000 net profit per month.",
)


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _credentials():
    return _load_json(CREDENTIALS_FILE, {})


def _save_credentials(data):
    _save_json(CREDENTIALS_FILE, data)


def _state():
    return _load_json(STATE_FILE, {})


def _save_state(data):
    _save_json(STATE_FILE, data)


def _set_last_seen(**fields):
    state = _state()
    state.setdefault("last_seen", {}).update(fields)
    _save_state(state)


def _last_seen():
    return _state().get("last_seen") or {}


def get_api_key():
    env_key = os.getenv("MOLTBOOK_API_KEY", "").strip()
    if env_key:
        return env_key
    creds = _credentials()
    return creds.get("api_key")


def register():
    """Register the agent once. Returns (success, message)."""
    if get_api_key():
        return True, "Already registered."

    try:
        resp = requests.post(
            f"{MOLTBOOK_BASE}/agents/register",
            json={
                "name": AGENT_NAME,
                "description": AGENT_DESCRIPTION,
            },
            timeout=30,
        )
    except Exception as e:
        return False, f"Register request failed: {e}"

    if not (200 <= resp.status_code < 300):
        return False, f"Register HTTP {resp.status_code}: {resp.text[:300]}"

    data = resp.json()
    agent = data.get("agent") or {}
    api_key = agent.get("api_key")
    claim_url = agent.get("claim_url")

    if not api_key:
        return False, "No api_key in registration response."

    _save_credentials(
        {
            "api_key": api_key,
            "agent_name": agent.get("name") or AGENT_NAME,
            "claim_url": claim_url,
        }
    )
    return True, claim_url or "Registered."


def get_status():
    """Check claim status. Returns dict or error string."""
    api_key = get_api_key()
    if not api_key:
        return {"error": "not_registered"}

    try:
        resp = requests.get(
            f"{MOLTBOOK_BASE}/agents/status",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except Exception as e:
        return {"error": f"status request failed: {e}"}

    if not (200 <= resp.status_code < 300):
        return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    return resp.json()


def get_profile():
    """Full profile of the registered agent (karma, followers, posts...)."""
    api_key = get_api_key()
    if not api_key:
        return None, "not_registered"
    try:
        resp = requests.get(
            f"{MOLTBOOK_BASE}/agents/me",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except Exception as e:
        return None, str(e)
    if not (200 <= resp.status_code < 300):
        return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
    return resp.json(), None


def get_notifications():
    """List notifications. Returns (list, error)."""
    api_key = get_api_key()
    if not api_key:
        return [], "not_registered"
    try:
        resp = requests.get(
            f"{MOLTBOOK_BASE}/notifications",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except Exception as e:
        return [], str(e)
    if not (200 <= resp.status_code < 300):
        return [], f"HTTP {resp.status_code}: {resp.text[:300]}"
    return (resp.json().get("notifications") or []), None


def mark_notification_read(notification_id):
    """Mark a notification as read so the agent does not reply twice."""
    api_key = get_api_key()
    if not api_key:
        return False
    try:
        resp = requests.post(
            f"{MOLTBOOK_BASE}/notifications/{notification_id}/read",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def reply_to_post(post_id, content):
    """Reply to a post (comment). Returns (ok, message)."""
    return comment_on_post(post_id, content)


def follow(agent_name):
    """Follow another molty. Returns (ok, message)."""
    api_key = get_api_key()
    if not api_key:
        return False, "not_registered"
    try:
        resp = requests.post(
            f"{MOLTBOOK_BASE}/agents/{agent_name}/follow",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except Exception as e:
        return False, str(e)
    if not (200 <= resp.status_code < 300):
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    return True, resp.json()


def get_my_posts():
    """Fetch posts authored by this agent with their scores.

    Returns (list_of_posts, error). Used to learn which topics land well.
    """
    api_key = get_api_key()
    if not api_key:
        return [], "not_registered"
    profile, err = get_profile()
    if err:
        return [], err
    agent_id = (profile.get("agent") or {}).get("id")
    try:
        resp = requests.get(
            f"{MOLTBOOK_BASE}/posts",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"author_agent_id": agent_id},
            timeout=30,
        )
    except Exception as e:
        return [], str(e)
    if not (200 <= resp.status_code < 300):
        return [], f"HTTP {resp.status_code}: {resp.text[:300]}"
    posts = resp.json().get("posts") or []
    mine = [
        p for p in posts
        if (p.get("author_id") == agent_id)
        or ((p.get("author") or {}).get("id") == agent_id)
    ]
    return mine, None


def home():
    """Fetch the /home dashboard (heartbeat entry point)."""
    api_key = get_api_key()
    if not api_key:
        return None, "not_registered"

    try:
        resp = requests.get(
            f"{MOLTBOOK_BASE}/home",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except Exception as e:
        return None, str(e)

    if not (200 <= resp.status_code < 300):
        return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
    return resp.json(), None


_ONES = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
    19: "nineteen",
}
_TENS = {
    20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
    60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety",
}
_WORD_TO_NUM = {}
for _k, _v in list(_ONES.items()) + list(_TENS.items()):
    _WORD_TO_NUM[_v] = _k


def _word_value(token):
    """Fuzzy match a number word inside an obfuscated token."""
    clean = "".join(c for c in token.lower() if c.isalpha() or c.isdigit())
    if clean.isdigit():
        return int(clean)
    if clean in _WORD_TO_NUM:
        return _WORD_TO_NUM[clean]
    # Obfuscation doubles letters ("een" -> "n"): collapse repeats, retry
    collapsed = ""
    for ch in clean:
        if ch != collapsed[-1:]:
            collapsed += ch
    if collapsed in _WORD_TO_NUM:
        return _WORD_TO_NUM[collapsed]
    # More general: the number word may appear as a contaminated substring
    for word, num in sorted(_WORD_TO_NUM.items(), key=lambda kv: -len(kv[0])):
        if word in clean and len(clean) <= len(word) + 3:
            return num
    return None


_OP_WORDS = {
    "and": "+", "plus": "+", "add": "+", "added": "+",
    "sum": "+", "total": "+", "combined": "+", "altogether": "+",
    "increases": "+", "increase": "+", "gains": "+",
    "faster": "+", "fast": "+", "higher": "+", "more": "+",
    "minus": "-", "subtract": "-", "subtracted": "-",
    "slows": "-", "slow": "-", "slowed": "-", "decreases": "-",
    "decrease": "-", "reduced": "-", "reduce": "-", "drops": "-",
    "drop": "-", "loses": "-", "loss": "-", "less": "-", "lower": "-",
    "times": "*", "multiply": "*", "multiplied": "*", "multiplication": "*",
    "twice": "*", "half": "*",
    "divided": "/", "divide": "/", "division": "/", "over": "/", "per": "/",
}
# Articles can be misread as "add" — only used as a last resort.
_WEAK_OP_WORDS = {"a": "+", "an": "+"}
_OP_SYMBOL = {"+": "+", "-": "-", "*": "*", "x": "*", "×": "*", "/": "/", "÷": "/"}


def _solve_verification(verification):
    """Parse the obfuscated math word problem and return the answer."""
    challenge = (verification or {}).get("challenge_text") or ""
    text = challenge.lower()
    tokens = text.replace(",", " ").split()

    number_positions = []
    current = None
    current_start = None
    for idx, t in enumerate(tokens):
        clean = "".join(c for c in t if c.isalpha() or c.isdigit())
        n = _word_value(clean)
        if n is None and clean.isdigit():
            n = int(clean)
        if n is not None:
            if current is None:
                current = 0
                current_start = idx
            current += n
        else:
            if current is not None:
                number_positions.append((current_start, idx - 1, current))
                current = None
                current_start = None
    if current is not None:
        number_positions.append((current_start, len(tokens) - 1, current))

    if len(number_positions) < 2:
        return None

    a_start, _, a = number_positions[0]
    _, b_end, b = number_positions[-1]

    op_tokens = []
    for idx, t in enumerate(tokens):
        sym = t.strip()
        if sym in _OP_SYMBOL:
            op_tokens.append((idx, _OP_SYMBOL[sym]))
            continue
        clean = "".join(c for c in t if c.isalpha())
        if clean in _OP_WORDS:
            op_tokens.append((idx, _OP_WORDS[clean]))
        elif clean in _WEAK_OP_WORDS:
            op_tokens.append((idx, _WEAK_OP_WORDS[clean]))

    candidates = [op for op in op_tokens if a_start < op[0] < b_end]
    if not candidates:
        for pattern, op in (("slow", "-"), ("minus", "-"), ("subtract", "-")):
            if pattern in text:
                op_tokens.append((len(tokens), op))
                break
    if op_tokens:
        operation = candidates[-1][1] if candidates else op_tokens[-1][1]
    else:
        operation = "+"

    if operation == "+":
        result = a + b
    elif operation == "-":
        result = a - b
    elif operation == "*":
        result = a * b
    elif operation == "/":
        result = a / b
    else:
        return None
    return f"{result:.2f}"


def _verify(content_type, content_id, verification, solver=None):
    if solver is not None:
        answer = solver((verification or {}).get("challenge_text") or "")
    else:
        answer = _solve_verification(verification)
    if answer is None:
        return False
    try:
        resp = requests.post(
            f"{MOLTBOOK_BASE}/verify",
            headers={
                "Authorization": f"Bearer {get_api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "verification_code": (verification or {}).get("verification_code"),
                "answer": answer,
            },
            timeout=30,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def post(title, content, solver=None):
    """Create a post in the general submolt. Returns (success, message).

    If a ``solver`` callable is provided it is used to answer the
    anti-spam math challenge (``challenge_text`` -> answer string),
    falling back to the built-in parser otherwise.
    """
    api_key = get_api_key()
    if not api_key:
        return False, "not_registered"

    try:
        resp = requests.post(
            f"{MOLTBOOK_BASE}/posts",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "submolt_name": "general",
                "title": title,
                "content": content,
            },
            timeout=30,
        )
    except Exception as e:
        return False, f"post request failed: {e}"

    if not (200 <= resp.status_code < 300):
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"

    data = resp.json()
    post_data = data.get("post") or {}
    verification = post_data.get("verification")

    if verification:
        ok = _verify("post", post_data.get("id"), verification, solver=solver)
        if ok:
            return True, "Post created and verified."
        return False, "Post needs verification but solving failed."

    return True, "Post created."


def delete_post(post_id):
    api_key = get_api_key()
    if not api_key:
        return False
    try:
        resp = requests.delete(
            f"{MOLTBOOK_BASE}/posts/{post_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def upvote_post(post_id):
    """Upvote a post. Returns (ok, message)."""
    api_key = get_api_key()
    if not api_key:
        return False, "not_registered"
    try:
        resp = requests.post(
            f"{MOLTBOOK_BASE}/posts/{post_id}/upvote",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except Exception as e:
        return False, str(e)
    if not (200 <= resp.status_code < 300):
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    return True, resp.json()


def comment_on_post(post_id, content):
    """Leave a comment on a post. Returns (ok, comment_id or message)."""
    api_key = get_api_key()
    if not api_key:
        return False, "not_registered"
    try:
        resp = requests.post(
            f"{MOLTBOOK_BASE}/posts/{post_id}/comments",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"content": content},
            timeout=30,
        )
    except Exception as e:
        return False, str(e)
    if not (200 <= resp.status_code < 300):
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    comment = (resp.json().get("comment") or {}).get("id")
    return True, comment


def delete_comment(comment_id):
    api_key = get_api_key()
    if not api_key:
        return False
    try:
        resp = requests.delete(
            f"{MOLTBOOK_BASE}/comments/{comment_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def my_comments_on(post_id):
    """Return True if this agent already commented on the post.

    Used to avoid duplicate comments across process restarts."""
    api_key = get_api_key()
    if not api_key:
        return False
    try:
        resp = requests.get(
            f"{MOLTBOOK_BASE}/posts/{post_id}/comments",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except Exception:
        return False
    if not (200 <= resp.status_code < 300):
        return False
    profile, p_err = get_profile()
    my_id = ((profile or {}).get("agent") or {}).get("id")
    for c in (resp.json().get("comments") or []):
        if c.get("content") == "Deleted comment":
            continue
        a = c.get("author") or {}
        if my_id and a.get("id") == my_id:
            return True
    return False


def posts_by_agent(agent_name, limit=5):
    """Fetch posts authored by a specific agent name, newest first.

    Returns (list_of_posts, error). Used to find a post where a new
    follower can be welcomed in a comment.
    """
    api_key = get_api_key()
    if not api_key:
        return [], "not_registered"
    try:
        resp = requests.get(
            f"{MOLTBOOK_BASE}/posts",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"author": agent_name},
            timeout=30,
        )
    except Exception as e:
        return [], str(e)
    if not (200 <= resp.status_code < 300):
        return [], f"HTTP {resp.status_code}: {resp.text[:300]}"
    posts = resp.json().get("posts") or []
    posts.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return posts[:limit], None


def feed(filter_="following", limit=10):
    """Fetch posts. Returns (list_of_posts, error)."""
    api_key = get_api_key()
    if not api_key:
        return [], "not_registered"
    try:
        resp = requests.get(
            f"{MOLTBOOK_BASE}/feed",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"filter": filter_},
            timeout=30,
        )
    except Exception as e:
        return [], str(e)
    if not (200 <= resp.status_code < 300):
        return [], f"HTTP {resp.status_code}: {resp.text[:300]}"
    return (resp.json().get("posts") or [])[:limit], None


def heartbeat():
    """Run once: fetch home, handle anything actionable, return summary."""
    claimed = get_status()
    if isinstance(claimed, dict) and claimed.get("error"):
        return claimed

    home_data, err = home()
    if err:
        return {"error": err}
    if not home_data:
        return {"error": "empty home response"}

    return {
        "your_account": home_data.get("your_account"),
        "activity_count": len(home_data.get("activity_on_your_posts") or []),
        "what_to_do_next": home_data.get("what_to_do_next"),
    }


def notify_on_update(bot, owner_chat_ids):
    """Compare Moltbook metrics against last known ones and notify the owner
    in Telegram about new followers / karma / unread notifications.

    Returns a list of messages that were sent."""
    profile, err = get_profile()
    if err:
        return []
    agent = (profile or {}).get("agent") or {}
    agent_id = agent.get("id")

    followers = agent.get("follower_count") or 0
    karma = agent.get("karma") or 0
    name = agent.get("display_name") or agent.get("name") or "moltbook agent"

    last = _last_seen()
    msgs = []

    prev_followers = last.get("followers", 0)
    prev_karma = last.get("karma", 0)
    prev_posts = last.get("posts", 0)

    posts_now = agent.get("posts_count") or 0

    # New follower(s)
    if followers > prev_followers:
        diff = followers - prev_followers
        msgs.append(
            f"🤝 Нов{('' if diff == 1 else 'ые')} подписчик(и) на Moltbook: "
            f"+{diff} (теперь {followers}) у {name}."
        )

    # Karma movement
    if karma != prev_karma:
        msgs.append(
            f"⭐ Карма Moltbook изменилась: {prev_karma} → {karma} (агент {name})."
        )

    # Unread notifications
    notifications, nerr = get_notifications()
    if not nerr and notifications:
        new_on = []
        for n in notifications:
            if not n.get("isRead"):
                new_on.append(n.get("content") or "")
        if new_on:
            msgs.append("📬 Новые уведомления Moltbook:\n• " + "\n• ".join(new_on[:5]))

    # Milestone: first post published
    if posts_now > prev_posts:
        msgs.append(
            f"📝 Агент {name} опубликовал {posts_now} пост(а/ов) на Moltbook."
        )

    if msgs:
        _set_last_seen(followers=followers, karma=karma, posts=posts_now)
        for chat_id in owner_chat_ids:
            try:
                for m in msgs:
                    bot.send_message(chat_id, m, disable_web_page_preview=True)
            except Exception:
                pass
    return msgs