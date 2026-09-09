# 🚀 Развертывание Telegram бота

## Вариант 1: Локальный запуск (для тестирования)

### Шаг 1: Клонируйте репо
```bash
git clone https://github.com/petriukasgmv-jpg/yolky-palky.git
cd yolky-palky
git checkout telegram-bot
```

### Шаг 2: Установите зависимости
```bash
cd bot
pip install -r requirements.txt
```

### Шаг 3: Создайте .env файл
```bash
cp .env.example .env
```

Отредактируйте `.env`:
```env
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
GROQ_API_KEY=ваш_groq_ключ
```

### Шаг 4: Получите Groq API Key
1. Перейдите на https://console.groq.com/keys
2. Войдите или зарегистрируйтесь
3. Нажмите "Create API Key"
4. Скопируйте ключ
5. Вставьте в `.env`

### Шаг 5: Запустите бота
```bash
python polling_bot.py
```

Вы должны увидеть:
```
🚀 Bot started successfully!
```

### Шаг 6: Тестируйте в Telegram
1. Откройте Telegram
2. Найдите вашего бота по username (который вы создали в BotFather)
3. Напишите `/start`
4. Попробуйте: "Хочу открыть кофейню"

---

## Вариант 2: Развертывание на Railway.app (РЕКОМЕНДУЕТСЯ - 24/7)

### Шаг 1: Создайте аккаунт на Railway
1. Перейдите на https://railway.app
2. Нажмите "Sign up"
3. Войдите через GitHub (проще всего)

### Шаг 2: Создайте новый проект
1. Нажмите "New Project"
2. Выберите "Deploy from GitHub repo"
3. Выберите ваш репо `yolky-palky`
4. Выберите ветку `telegram-bot`

### Шаг 3: Добавьте переменные окружения
1. В Railway откройте проект
2. Нажмите "Variables" (в левой панели)
3. Нажмите "New Variable"
4. Добавьте:

```
Key: TELEGRAM_BOT_TOKEN
Value: ваш_токен_от_BotFather
```

5. Добавьте ещё одну переменную:

```
Key: GROQ_API_KEY
Value: ваш_groq_ключ
```

### Шаг 4: Убедитесь, что есть Procfile
Проверьте, что в репо есть файл `bot/Procfile` с содержимым:
```
worker: cd bot && python polling_bot.py
```

### Шаг 5: Деплой
1. Railway автоматически начнет деплой после push в GitHub
2. Или нажмите "Deploy" вручную
3. Подождите 1-2 минуты
4. Вы должны увидеть статус "Running" ✅

### Шаг 6: Проверьте логи
1. Нажмите на проект
2. Перейдите на вкладку "Logs"
3. Должны видеть: `🚀 Bot started successfully!`

### Шаг 7: Тестируйте в Telegram
Теперь бот работает 24/7! 🎉

---

## Вариант 3: Развертывание на Render.com (Альтернатива)

### Шаг 1: Создайте аккаунт
https://render.com

### Шаг 2: Создайте новый Background Worker
1. Нажмите "New +"
2. Выберите "Background Worker"
3. Подключите GitHub репо
4. Выберите ветку `telegram-bot`

### Шаг 3: Конфигурация
- **Name:** yolky-palky-bot
- **Runtime:** Python 3.11
- **Build Command:** `pip install -r bot/requirements.txt`
- **Start Command:** `cd bot && python polling_bot.py`

### Шаг 4: Добавьте переменные
Нажмите "Environment" и добавьте:
- `TELEGRAM_BOT_TOKEN`
- `GROQ_API_KEY`

### Шаг 5: Деплой
Нажмите "Create Background Worker"

---

## ✅ Проверка работоспособности

1. Бот должен ответить на `/start`
2. Бот должен получать сообщения
3. Бот должен отвечать через 5-30 секунд (зависит от Groq)
4. Проверьте логи на ошибки

## 🔧 Решение проблем

### Бот не отвечает:
- Проверьте TELEGRAM_BOT_TOKEN
- Проверьте логи в Railway/Render
- Убедитесь, что программа запустилась (`🚀 Bot started successfully!`)

### Ошибка с Groq API:
- Проверьте GROQ_API_KEY
- Убедитесь, что у вас есть лимит на Groq
- Попробуйте обновить ключ на https://console.groq.com/keys

### Высокий пинг (долгое ожидание):
- Это нормально - Groq немного медленнее OpenAI
- Обычно 5-15 секунд
- Если больше минуты - проблема с интернетом

---

## 💰 Стоимость

- **Telegram Bot API:** Бесплатно ✅
- **Groq API:** Бесплатно (щедрый лимит) ✅
- **Railway.app:** $5/месяц (есть бесплатный кредит $5) ✅
- **Render.com:** Бесплатно (1 worker) ✅

**ИТОГО: Полностью БЕСПЛАТНО на первые месяцы!**

---

## 🎉 Готово!

Ваш бот работает 24/7 в интернете! 🚀

Теперь вы можете:
- Анализировать бизнес-идеи в Telegram
- Делиться ссылкой на бота с друзьями
- Масштабировать без платежей

## 📊 Следующие шаги:

1. Добавить сохранение истории в БД
2. Добавить экспорт анализа в PDF
3. Добавить аналитику популярных идей
4. Монетизировать (платная подписка)
5. Добавить веб-интерфейс
