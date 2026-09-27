import os
import re
import threading
import time
import traceback

from dotenv import load_dotenv
from flask import Flask, request
from groq import Groq
import telebot
from telebot import types
from duckduckgo_search import DDGS

from prompt import SYSTEM_PROMPT

load_dotenv()

# Инициализация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)

# Память разговоров (в продакшене лучше использовать БД)
user_histories = {}

# --- ИНСТРУМЕНТЫ АГЕНТА (TOOLS) ---

def search_web(query: str) -> str:
    """Инструмент для поиска информации в интернете."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return "Поисковый запрос не дал результатов."
            
            formatted_results = ""
            for r in results:
                formatted_results += f"- Title: {r.get('title')}\n  Snippet: {r.get('body')}\n  Link: {r.get('href')}\n\n"
            return formatted_results
    except Exception as e:
        return f"Ошибка при выполнении поиска: {str(e)}"

# Описание функций для Groq API
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Ищет актуальную информацию в интернете (цены, товары, налоги, спрос, правила). Используй, когда нужны свежие факты.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос на русском, литовском или английском языке"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# --- ЛОГИКА АГЕНТА (AGENT LOOP) ---

def run_agent(chat_id: int, user_message: str) -> str:
    if chat_id not in user_histories:
        user_histories[chat_id] = []
    
    # Форматируем системный промпт
    formatted_system_prompt = SYSTEM_PROMPT.format(profile="", context="")
    
    messages = [
        {"role": "system", "content": formatted_system_prompt}
    ] + user_histories[chat_id] + [
        {"role": "user", "content": user_message}
    ]

    # Шаг 1: Первичный запрос к модели с передачей инструментов
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.2
    )

    response_message = response.choices[0].message

    # Шаг 2: Проверяем, хочет ли агент вызвать инструмент (поиск)
    if response_message.tool_calls:
        # Добавляем решение модели в историю
        messages.append(response_message)

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            
            if function_name == "search_web":
                import json
                args = json.loads(tool_call.function.arguments)
                search_query = args.get("query")
                
                # Уведомляем пользователя или просто выполняем поиск
                search_result = search_web(search_query)

                # Возвращаем результат функции агенту
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": search_result
                })

        # Шаг 3: Повторный запрос к модели уже с полученными из поиска данными
        final_response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.2
        )
        final_text = final_response.choices[0].message.content
    else:
        final_text = response_message.content

    # Обновляем историю диалога
    user_histories[chat_id].append({"role": "user", "content": user_message})
    user_histories[chat_id].append({"role": "assistant", "content": final_text})
    
    # Ограничиваем историю последними 10 сообщениями
    if len(user_histories[chat_id]) > 10:
        user_histories[chat_id] = user_histories[chat_id][-10:]

    return final_text

# --- TELEGRAM & FLASK HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я твой ИИ Бизнес-Стратег и Аудитор Yolky-Palky. Готов проанализировать любую бизнес-идею или рассчитать экономику.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        reply_text = run_agent(message.chat.id, message.text)
        bot.reply_to(message, reply_text)
    except Exception as e:
        traceback.print_exc()
        bot.reply_to(message, f"Произошла ошибка при обработке: {str(e)}")

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Invalid', 400

@app.route('/')
def index():
    return 'Bot is running!'

# Установка вебхука при старте
if __name__ == '__main__':
    if WEBHOOK_URL:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
            print(f"Webhook set to {WEBHOOK_URL}/webhook", flush=True)
        except Exception as e:
            print("Webhook setup error:", repr(e), flush=True)

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
