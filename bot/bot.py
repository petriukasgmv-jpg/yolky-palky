import os
import json
import threading
from flask import Flask
from groq import Groq
import telebot
from duckduckgo_search import DDGS

# === Переменные окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Необходимо задать TELEGRAM_TOKEN и GROQ_API_KEY!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# Более умная модель
MODEL = "openai/gpt-oss-120b"

# === Инструмент поиска ===
def web_search(query: str, max_results: int = 5) -> str:
    """Ищет актуальную информацию в интернете"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        
        if not results:
            return "По запросу ничего не найдено."
        
        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"{i}. {r['title']}\n{r['body']}\nИсточник: {r['href']}")
        
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"


# Описание инструмента для модели
tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Ищет актуальную информацию в интернете. Используй, когда нужны свежие данные, новости, цены, факты после 2024 года, погода, курсы и т.д.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


def ask_groq(user_message: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Ты полезный, умный и дружелюбный ИИ-ассистент. "
                "Если для ответа нужна актуальная информация из интернета — обязательно используй инструмент web_search. "
                "Отвечай на русском языке, если пользователь пишет на русском."
            )
        },
        {"role": "user", "content": user_message}
    ]

    # Первый запрос к модели
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.7,
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    # Если модель решила вызвать инструмент
    if tool_calls:
        messages.append(response_message)

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            if function_name == "web_search":
                search_result = web_search(function_args.get("query", ""))
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": search_result,
                })

        # Второй запрос — модель формирует финальный ответ на основе результатов поиска
        second_response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
        )
        return second_response.choices[0].message.content

    # Если инструмент не понадобился
    return response_message.content


# === Обработчики Telegram ===
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Привет! Я умный ИИ-ассистент с доступом в интернет.\n"
        "Могу отвечать на вопросы, искать актуальную информацию и помогать с разными задачами."
    )


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        answer = ask_groq(message.text)
        bot.reply_to(message, answer)
    except Exception as e:
        bot.reply_to(message, f"❌ Произошла ошибка:\n{str(e)}")


# === Заглушка порта для Render ===
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running with internet access!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    try:
        bot.delete_webhook()
        print("Webhook удалён")
    except:
        pass

    threading.Thread(target=run_flask, daemon=True).start()
    print("Бот успешно запущен (с интернетом)...")
    bot.infinity_polling(skip_pending=True)
