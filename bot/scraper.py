from urllib.parse import quote

import groq_utils

MODEL = "openai/gpt-oss-20b"

SEARCH_PROMPT = (
    "Ты — ассистент, который ищет актуальные цены на немецких барахолках "
    "и маркетплейсах для бизнес-арбитража. Пользователь продаёт советские "
    "и винтажные вещи (часы, инструменты, оптику, кожаные куртки) из Германии "
    "в Литву/Польшу/Латвию.\n"
    "Задача: найти РЕАЛЬНЫЕ объявления и цены по запросу на "
    "vinted.de, ebay.de, kleinanzeigen.de.\n"
    "Выведи до 8 конкретных результатов: товар, цена в €, площадка, ссылка.\n"
    "СРОГО: используй ТОЛЬКО ссылки, которые реально есть в результатах "
    "поиска browser_search. НИКОГДА не выдумывай и не составляй ссылки по "
    "шаблонам. Если ссылка найдена — вставь её дословно как есть.\n"
    "Если результатов нет или цены не подтверждены — напиши честно "
    "'Не удалось найти реальные объявления' и не придумывай ничего."
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
        content = groq_utils.chat_with_search(
            client,
            MODEL,
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
            max_tokens=1200,
        )
        if not content:
            return None, "empty response"
        return content, None
    except Exception as e:
        return None, str(e)


def sanitize_query(text):
    """Turn free text into a safe URL-encoded keyword string."""
    words = text.split()
    if not words:
        return ""
    return quote(" ".join(words), safe="")


def manual_search_links(query):
    q = sanitize_query(query)
    return (
        "🔗 Ручной поиск:\n"
        f"• Vinted: https://www.vinted.de/catalog?search_text={q}\n"
        f"• eBay: https://www.ebay.de/sch/i.html?_nkw={q}\n"
        f"• Kleinanzeigen: https://www.kleinanzeigen.de/s-{q}/k0"
    )