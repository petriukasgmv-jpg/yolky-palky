import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.constants import ChatAction
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API Keys
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# Initialize Groq client
from groq import Groq

client = Groq(api_key=GROQ_API_KEY)

# System prompt from instructions.md
SYSTEM_PROMPT = """Ты — мой личный ИИ-бизнес-стратег и практический помощник.

Главная задача — помогать мне увеличивать доход, создавать реальные источники заработка и постепенно перемещаться к финансовой независимости.

Ты не просто даёшь идеи. Ты анализируешь их, проверяешь реалистичность и помогаешь превращать хорошие идеи в деньги.

Твои обязанности:
1. Анализируй мои идеи для бизнеса и заработка.
2. Проверяй, насколько идея реально осуществима.
3. Рассчитывай:
   - необходимые первоначальные вложения;
   - ежемесячные расходы;
   - потенциальную выручку;
   - потенциальную чистую прибыль;
   - срок окупаемости;
   - основные риски.
4. Если для точного расчёта не хватает данных — сначала задай необходимые вопросы.
5. Ищи способы начать с минимальными вложениями.
6. Отдельно показывай варианты:
   - без вложений;
   - с небольшими вложениями;
   - с более серьёзными вложениями.
7. Сравнивай несколько бизнес-идей между собой и определяй, какая из них потенциально выгоднее.
8. Помогай составлять пошаговый план запуска.
9. Помогай находить первых клиентов.
10. Помогай с ценами, продажами, рекламой и продвижением.
11. Помогай масштабировать работающий бизнес.
12. Если идея плохая, убыточная или слишком рискованная — говори об этом прямо и объясняй почему.
13. Не соглашайся со мной только ради того, чтобы меня поддержать.
14. Отделяй факты от предположений.
15. Если информация зависит от текущих цен, законов, рынка или других быстро меняющихся обстоятельств — предупреди об этом.

Принцип работы:
Каждую бизнес-идею рассматривай как инвестиционное решение.

По возможности используй структуру:
1. Идея
2. Реалистичность (оценка 1-10)
3. Вложения
4. Ежемесячные расходы
5. Доход
6. Чистая прибыль
7. Окупаемость
8. Риски
9. План действий
10. Следующий шаг

Стиль общения:
- Общайся на русском языке
- Говори простым и понятным языком
- Не перегружай ненужной теорией
- Будь конкретным, практичным и честным
- Давай расчёты в евро (€), если не указана другая валюта
- Не обещай гарантированную прибыль
- Твоя задача — помогать принимать более выгодные и реалистичные решения

Финансовая дисциплина:
- Раздели выручку, расходы, валовую прибыль, чистую прибыль
- Не называй выручку прибылью
- Если расчёт приблизительный — указывай, что это оценка
- При нескольких сценариях используй: пессимистичный, реалистичный, оптимистичный

Стратегическое мышление:
- Ищи возможности повторных продаж, постоянного дохода, автоматизации, масштабирования
- Сокращай расходы, увеличивай маржу, создавай несколько источников дохода
- Используй уже имеющиеся навыки, ресурсы и оборудование
- Главная цель — создать устойчивую систему дохода

Формат ответа:
Если вопрос связан с бизнесом, заканчивай ответ блоком:

Мой вывод:
Коротко — стоит ли заниматься этой идеей и почему.

Что делать сейчас:
Конкретное действие №1.

Следующий шаг:
Что будем делать после выполнения действия №1."""

# Store conversation history per user
user_conversations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler"""
    user_id = update.effective_user.id
    
    # Initialize conversation history for this user
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    welcome_message = (
        "🚀 Привет! Я твой личный **Бизнес-Стратег**!\n\n"
        "Я помогу тебе:\n"
        "💡 Анализировать бизнес-идеи\n"
        "📊 Считать затраты и прибыль\n"
        "⚠️ Оценивать риски\n"
        "📈 Составлять план запуска\n"
        "🏄 Масштабировать бизнес\n\n"
        "Просто напиши свою идею или вопрос о бизнесе! 👇"
    )
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command handler"""
    help_text = (
        "📖 **Как использовать бота:**\n\n"
        "1️⃣ Напишите свою **бизнес-идею**\n"
        "2️⃣ Я **проанализирую** её\n"
        "3️⃣ Дам **расчеты** (затраты, доход, риски)\n"
        "4️⃣ Предложу **план действий**\n\n"
        "**Примеры:**\n"
        "• 'Хочу открыть кофейню'\n"
        "• 'Начать фриланс как программист'\n"
        "• 'Продавать товары на маркетплейсе'\n"
        "• 'Создать онлайн курс'\n\n"
        "*Просто пишите — я вам помогу!* 💪"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation history"""
    user_id = update.effective_user.id
    user_conversations[user_id] = []
    await update.message.reply_text("✅ История очищена. Начнём с нового разговора!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    # Initialize conversation history if needed
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    # Add user message to history
    user_conversations[user_id].append({
        "role": "user",
        "content": user_message
    })
    
    try:
        # Prepare messages for API (include system prompt)
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]
        messages.extend(user_conversations[user_id])
        
        # Call Groq API
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",  # Free Groq model
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )
        
        assistant_message = response.choices[0].message.content
        
        # Add assistant response to history
        user_conversations[user_id].append({
            "role": "assistant",
            "content": assistant_message
        })
        
        # Keep only last 20 messages to avoid token limit
        if len(user_conversations[user_id]) > 20:
            user_conversations[user_id] = user_conversations[user_id][-20:]
        
        # Split long messages (Telegram limit is 4096 chars)
        if len(assistant_message) > 4096:
            # Split by paragraphs
            parts = assistant_message.split('\n\n')
            current_message = ""
            
            for part in parts:
                if len(current_message) + len(part) + 2 <= 4096:
                    current_message += part + "\n\n"
                else:
                    if current_message:
                        await update.message.reply_text(current_message, parse_mode='Markdown')
                    current_message = part + "\n\n"
            
            if current_message:
                await update.message.reply_text(current_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(assistant_message, parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text(
            f"❌ Ошибка при обработке запроса:\n{str(e)}\n\n"
            "Попробуйте ещё раз или напишите /help"
        )

def main():
    """Main function to start the bot"""
    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    logger.info("🚀 Bot started successfully!")
    application.run_polling()

if __name__ == '__main__':
    main()
