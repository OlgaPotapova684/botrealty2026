# Бот для агентства недвижимости (24/7)

Telegram-бот по сценарию из JSON. Работает с новым токеном из переменной окружения.

## Пошаговая реализация запуска 24/7

### Шаг 1. Получить токен бота

1. Откройте Telegram, найдите [@BotFather](https://t.me/BotFather).
2. Отправьте `/newbot` (или `/token` у существующего бота и выберите «Revoke» для нового).
3. Введите имя бота и username (например, `realty_agency_bot`).
4. Скопируйте выданный токен вида `123456789:ABCdefGHI...`.

### Шаг 2. Установить зависимости

В папке проекта:

```bash
cd /Users/olgapotapova/Programming/botrealty2026
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Шаг 3. Задать токен и запустить локально

**Вариант A — переменная окружения в терминале:**

```bash
export BOT_TOKEN=ВАШ_НОВЫЙ_ТОКЕН
python bot.py
```

**Вариант B — файл `.env` (не коммитить в git):**

```bash
cp .env.example .env
# Откройте .env и вставьте: BOT_TOKEN=ваш_токен
```

Затем установите `python-dotenv` и в начале `bot.py` добавьте загрузку `.env`:

```bash
pip install python-dotenv
```

В `bot.py` после импортов:

```python
from dotenv import load_dotenv
load_dotenv()
```

После этого можно запускать просто:

```bash
python bot.py
```

Остановка: `Ctrl+C`.

### Шаг 4. Запуск 24/7 на сервере (VPS)

Чтобы бот крутился постоянно, его нужно запускать на машине, которая не выключается.

#### 4.1. Арендовать VPS

- [Timeweb](https://timeweb.com), [Selectel](https://selectel.ru), [Reg.ru](https://www.reg.ru) и т.п.
- Достаточно минимального тарифа (1 CPU, 512 MB RAM).

#### 4.2. Подключиться по SSH и поставить окружение

```bash
ssh user@ваш-сервер-ip
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
```

#### 4.3. Загрузить проект на сервер

- Через `git clone` (если репозиторий в Git), или
- Скопировать папку через `scp`:

```bash
scp -r /Users/olgapotapova/Programming/botrealty2026 user@ваш-сервер-ip:~/
```

#### 4.4. На сервере: venv, зависимости, токен

```bash
cd ~/botrealty2026
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export BOT_TOKEN=ВАШ_НОВЫЙ_ТОКЕН
```

#### 4.5. Запуск через systemd (автозапуск и перезапуск 24/7)

Создайте unit-файл:

```bash
sudo nano /etc/systemd/system/realty-bot.service
```

Вставьте (подставьте свой путь и пользователя):

```ini
[Unit]
Description=Telegram Realty Bot
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/botrealty2026
Environment="BOT_TOKEN=ВАШ_НОВЫЙ_ТОКЕН"
ExecStart=/home/YOUR_USER/botrealty2026/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Включите и запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable realty-bot
sudo systemctl start realty-bot
sudo systemctl status realty-bot
```

Дальше бот будет:
- стартовать при загрузке сервера;
- перезапускаться при падении (`Restart=always`).

Полезные команды:

- Логи: `journalctl -u realty-bot -f`
- Остановка: `sudo systemctl stop realty-bot`
- Перезапуск: `sudo systemctl restart realty-bot`

### Шаг 5. Альтернатива — облачный запуск без своего VPS

Если не хотите настраивать сервер:

- **Vercel** — см. раздел [Деплой на Vercel](#деплой-на-vercel) ниже (webhook, без polling).
- **Railway** ([railway.app](https://railway.app)) — загружаете проект, в настройках добавляете переменную `BOT_TOKEN`, деплой по Git или ZIP.
- **Render** ([render.com](https://render.com)) — Background Worker, переменная `BOT_TOKEN`, репозиторий из GitHub.
- **PythonAnywhere** — бесплатный тариф может ограничивать исходящие соединения; для бота часто подходит платный.

Везде важно: задать переменную окружения `BOT_TOKEN` и указать команду запуска `python bot.py` (или `venv/bin/python bot.py`). На Vercel бот работает по webhook, а не по polling.

---

## Деплой на Vercel

Бот может работать на [Vercel](https://vercel.com) как serverless-функция (webhook). Компьютер можно выключать — бот остаётся в облаке.

1. **Репозиторий**  
   Залейте проект в GitHub (или подключите существующий репозиторий к Vercel).

2. **Деплой**  
   На [vercel.com](https://vercel.com): New Project → Import репозитория → Deploy.  
   В настройках проекта (Settings → Environment Variables) добавьте переменную:
   - **Name:** `BOT_TOKEN`  
   - **Value:** ваш токен от @BotFather  

   После сохранения сделайте повторный деплой (Redeploy), чтобы переменная подхватилась.

3. **Включить webhook**  
   После деплоя у вас будет URL вида `https://ваш-проект.vercel.app`. Один раз укажите Telegram этот адрес как webhook (подставьте свой токен и URL):

   ```bash
   curl "https://api.telegram.org/bot<ВАШ_ТОКЕН>/setWebhook?url=https://ваш-проект.vercel.app/api/webhook"
   ```

   Или из браузера откройте ссылку:
   `https://api.telegram.org/bot<ВАШ_ТОКЕН>/setWebhook?url=https://ваш-проект.vercel.app/api/webhook`

   В ответе должно быть `"ok":true`.

4. **Проверка**  
   Напишите боту в Telegram `/start` — ответ должен приходить с Vercel.

**Важно:** после установки webhook локальный запуск `python bot.py` (polling) с тем же токеном конфликтует с webhook. Либо используйте только Vercel, либо отключите webhook перед локальным запуском:

```bash
curl "https://api.telegram.org/bot<ВАШ_ТОКЕН>/deleteWebhook"
```

---

## Смена токена

1. Получите новый токен у @BotFather (при необходимости отзовите старый).
2. Обновите значение:
   - локально: снова `export BOT_TOKEN=новый_токен` и перезапустите `python bot.py`;
   - на systemd: отредактируйте `Environment="BOT_TOKEN=..."` в `/etc/systemd/system/realty-bot.service`, затем:
     ```bash
     sudo systemctl daemon-reload
     sudo systemctl restart realty-bot
     ```
   - в облаке: измените переменную `BOT_TOKEN` в настройках сервиса и перезапустите деплой/воркер.

После смены токена старый перестаёт работать; все запросы должны идти к боту с новым токеном.
