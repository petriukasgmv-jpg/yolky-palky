import re

MODEL = "openai/gpt-oss-20b"

SEARCH_PROMPT = (
    "Ты — ассистент, который ищет актуальные цены на немецких барахолках "
    "и маркетплейсах для бизнес-арбитража. Пользователь продаёт советские "
    "и винтажные вещи (часы, инструменты, оптику, кожаные куртки) из Германии "
    "в Литву/Польшу/Латвию.\n"
    "Задача: найти РЕАЛЬНЫЕ объявления и цены по запросу на "
    "vinted.de, ebay.de, kleinanzeigen.de.\n"
    "Выведи до 8 конкретных результатов: товар, цена в €, площадка, ссылка. "
    "Только факты из найденного. Если ничего найдено — так и напиши. "
    "Не выдумывай цены и ссылки."
)

FALLBACK_HELP = (
    "Не удалось получить цены через поиск. Проверь вручную:\n"
    "• https://www.vinted.de/catalog?search_text=<запрос>\n"
    "• https://www.ebay.de/sch/i.html?_nkw=<запрос>\n"
    "• https://www.kleinanzeigen.de/s-<запрос>/k0"
)


def search_prices(client, query):
    """Search current market prices via Groq browser_search.

    Returns (text, error)."""
    query = query.strip()
    if not query:
        return None, "empty query"

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SEARCH_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Найди цены по запросу: {query}. "
                        "Сделай несколько поисковых запросов."
                    ),
                },
            ],
            tools=[{"type": "browser_search"}],
            tool_choice="required",
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=1200,
        )
        content = completion.choices[0].message.content
        if not content:
            return None, "empty response"
        return content, None
    except Exception as e:
        return None, str(e)


def sanitize_query(text):
    """Turn free text into a safe URL/keyword string."""
    cleaned = re.sub(r"[^a-zA-ZäöüÄÖÜß0-9 -]", "", text)
    words = [w for w in cleaned.split() if w]
    return "+".join(words)


def manual_search_links(query):
    q = sanitize_query(query)
    return (
        "🔗 Ручной поиск:\n"
        f"• Vinted: https://www.vinted.de/catalog?search_text={q}\n"
        f"• eBay: https://www.ebay.de/sch/i.html?_nkw={q}\n"
        f"• Kleinanzeigen: https://www.kleinanzeigen.de/s-{q}/k0"
    )